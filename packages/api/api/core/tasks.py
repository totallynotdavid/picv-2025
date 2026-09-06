"""Queue tasks for simulation runs and worker maintenance.

Abandoned attempts, and how their writes are fenced
---------------------------------------------------
The simulation kernel is synchronous and runs on a thread via
`asyncio.to_thread`. rqueue cancels a handler's *coroutine* when the heartbeat
discovers the lease is gone (`Worker._heartbeat_loop` -> `handler_task.cancel()`),
but Python cannot kill the thread underneath it. That thread keeps running and
holds a live reference to the event loop through `on_progress`, so it can still
try to write `compute.jobs` for a job another worker has taken over -- or for a
job `reconcile_terminal_jobs` has already, correctly, marked failed.

Procrastinate did not have this exposure: its task was synchronous, with no
background thread able to outlive a cancelled coroutine. It is new here.

The fence is in the database, not in this process. `mark_started` claims the row
for `context.attempt` by writing `compute.jobs.owner_attempt`, and every write
an attempt makes afterwards carries its own attempt number in the *same*
statement as the write (`WHERE id = $1 AND owner_attempt = $n ...`). A write
from a superseded attempt therefore matches zero rows. `record_progress` adds
`AND status <> ALL(TERMINAL_STATUSES)`, because the abandoned attempt is often
still the row's owner -- the case that matters is a stale write flipping a
reconciled `failed` job back to `running`, undoing the repair reconciliation
just made, and only the status predicate catches that.

A refused write is not an error; it is the fence working. `on_progress` treats
one as the signal to stop, raising `AbandonedAttempt` so the kernel unwinds and
the thread ends rather than burning a core on work nobody will read.

That exception surfaces in two different places, and the difference matters:

- **Refused write.** The coroutine is still live and awaiting the thread, so
  `AbandonedAttempt` propagates into `run_simulation_task` as a real exception.
  It is caught there and re-raised as `rqueue.CancelJob`, because standing down
  is not a failure: letting it reach rqueue's generic exception path would
  record a `rqueue.job.failed`, finalize the job as failed, and log two
  tracebacks for a fence working correctly -- and an on-call engineer would
  have no way to tell that from a simulation that actually broke.
- **Cancellation.** rqueue has already cancelled the coroutine, so there is
  nothing left to propagate into and the thread just ends. The same `abandoned`
  flag is set directly there, which usually stops the thread a step *earlier*
  than a refused write would.

The workspace is fenced separately, and has to be
-------------------------------------------------
The database fence protects `compute.jobs`. It does nothing for the *files*:
the workspace is keyed by simulation id, not by attempt, and an abandoned
thread mid-step keeps writing checkpoints into it. A replacement attempt that
resumed from a half-written checkpoint would produce a wrong scientific result
rather than an error, which is worse than any status confusion.

`claim_workspace` therefore takes an exclusive `flock` on a lock file beside the
workspace. A second attempt is refused while a live owner holds it -- including
from another thread of the same process -- and gets `TransientInfraError`, so
rqueue's backoff waits for the abandoned thread to unwind rather than racing it.
When the holding *process* dies the kernel drops the lock, so an ordinary worker
crash still leaves the workspace resumable.

The claim spans more than the kernel. `complete_job` reads the result files back
out of the same directory to upload them, after the kernel thread has returned,
so a claim that ended with the kernel would leave that upload unprotected --
the identical corruption a few lines later. The claim therefore carries two
shares, one given back by the kernel thread and one by this coroutine after the
upload, and the descriptor closes only when both have. Neither holder can be
cancelled, and a cancelled coroutine ends while the thread is still writing, so
"whoever finishes last closes it" is the only rule that works.

`remove_workspace` takes the lock before it removes anything, for the same
reason in reverse: `unlink` on a locked file drops the directory entry while the
holder keeps its lock on the orphaned inode, so the next `O_CREAT` at that path
creates a *new* inode that locks uncontended. It refuses rather than forces, and
the next sweep retries.

Two limits are worth knowing. A thread that never reaches another progress
callback holds the workspace until it finishes on its own, and the replacement
can exhaust its attempts waiting -- a visible, bounded failure rather than
silent corruption, which is the trade being made. And `flock` is a
single-machine primitive: two workers on different hosts sharing one network
volume are not protected by it. Neither the compose deployment (one worker, a
local volume) nor any current configuration is exposed to the second.
"""

import asyncio
import contextlib
import fcntl
import logging
import os
import shutil
import threading
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg
from rqueue import CancelJob, Job, PermanentFailure, Queue, RetryPolicy, TaskContext

from api.core import db, repository
from api.core.errors import TransientInfraError
from api.core.queue import get_queue
from api.core.settings import JOBS_DIR
from tsdhn.domain import EarthquakeInput, JobStatus
from tsdhn.engine import run_simulation

__all__ = [
    "MAX_ATTEMPTS",
    "RUN_SIMULATION",
    "TRANSIENT_RETRY",
    "AbandonedAttempt",
    "decode_payload",
    "enqueue_simulation",
    "reconcile_terminal_jobs",
    "register_tasks",
    "run_periodic_reconcile",
    "run_periodic_sweep",
    "run_simulation_task",
    "sweep_abandoned_work_dirs",
]

logger = logging.getLogger(__name__)

RUN_SIMULATION = "api.run_simulation"


class AbandonedAttempt(Exception):
    """Raised into the kernel thread when its attempt no longer owns the job.

    Reaches `run_simulation_task` only on the refused-write path, where the
    coroutine is still live and awaiting the thread. It is caught there and
    turned into `rqueue.CancelJob`, so standing down never counts as a task
    failure. On the cancellation path the coroutine is already gone, so nothing
    propagates it and the thread simply ends.
    """


# Retry only infrastructure failures. Domain and pipeline errors are terminal.
# `retry_on` is rqueue's exception allowlist, the direct counterpart of
# Procrastinate's `retry_exceptions`.
MAX_ATTEMPTS = 3
TRANSIENT_RETRY = RetryPolicy(
    max_attempts=MAX_ATTEMPTS,
    initial_backoff=15.0,
    multiplier=2.0,
    retry_on=(TransientInfraError,),
)

# A simulation runs for tens of minutes and has no meaningful upper bound, so
# it is left untimed; rqueue's lease recovery, not a timeout, is what reclaims
# a run whose worker died.
RUN_TIMEOUT_SECONDS: float | None = None

# The workspace ownership lock, kept beside the workspace rather than inside
# it: `prepare_simulation_workspace` removes the whole directory when a run
# starts without resuming, which would take the lock with it.
WORKSPACE_LOCK_SUFFIX = ".lock"

# Keep terminal workspaces for local inspection and manual recovery.
WORK_DIR_TTL = timedelta(hours=24)
SWEEP_INTERVAL_SECONDS = 3600.0

# How long a queue job must have been terminal before reconciliation claims it.
# The queue row being terminal already implies no worker holds its lease, so in
# principle nothing else can be writing compute.jobs by then. The grace covers
# the one case where that reasoning is not airtight: a worker wedged long
# enough to lose its lease, whose recovery -- and whose own write of the
# outcome -- can still land after rqueue has failed the row underneath it.
# Five minutes is comfortably longer than any such write, and the delay costs
# nothing: this only ever runs on jobs that are already over.
RECONCILE_GRACE = timedelta(minutes=5)

# A minute, against the sweep's hour, because the two clean up different
# things. The sweep reclaims disk from jobs that are already reported failed,
# where an hour of delay is invisible. This pass is what ends a *user-visible*
# stuck status: until it runs, a researcher watching /events sees "running"
# for a simulation that no longer exists anywhere. The whole pass is one
# indexed statement over jobs the queue has already finished, so polling it
# this often is cheap; the stuck window is then bounded by the lease duration
# plus the grace, not by the interval.
RECONCILE_INTERVAL_SECONDS = 60.0

# Keep cancellation cleanup tasks strongly reachable until they have released
# the claim returned by their background thread.
_CLAIM_DRAIN_TASKS: set[asyncio.Task[None]] = set()


def decode_payload(payload: Any) -> uuid.UUID:
    """Turn a queued payload into the compute job id it names.

    A payload that cannot be decoded fails the job durably without spending
    the retry budget: the same bytes will not decode on a later attempt.
    """
    if not isinstance(payload, dict):
        raise ValueError("simulation payload must be a JSON object")
    return repository.as_uuid(str(payload["compute_job_id"]))


async def enqueue_simulation(
    connection: asyncpg.Connection, compute_job_id: uuid.UUID
) -> Job:
    """Queue the task on `connection` so it commits with the job row.

    `dedupe_key` replaces Procrastinate's `queueing_lock` (one queued job per
    compute job) and `concurrency_key` replaces its `lock` (one simulation
    running at a time for a compute job). rqueue keeps those two as separate
    primitives, so both survive the swap unchanged in meaning.
    """
    return await get_queue().enqueue(
        connection,
        task=RUN_SIMULATION,
        payload={"compute_job_id": str(compute_job_id)},
        dedupe_key=f"simulation:{compute_job_id}",
        on_conflict="return_existing",
        concurrency_key=f"compute-job:{compute_job_id}",
    )


class WorkspaceClaim:
    """One exclusive `flock` on a workspace, released by whoever finishes last.

    Two things write to, or read out of, the workspace during an attempt, and
    neither can be cancelled once started: the kernel thread, and the upload
    `complete_job` makes on another thread. They do not overlap, but they can
    *end* in either order -- a cancelled coroutine ends while the kernel thread
    is still going -- so a single owner cannot close the descriptor at the right
    moment. Each side takes a share and gives it back at its own end; the
    descriptor closes, and the lock with it, only when both have.
    """

    def __init__(self, fd: int, shares: int = 2) -> None:
        self._fd = fd
        self._shares = shares
        self._guard = threading.Lock()

    def release(self) -> None:
        """Give back one share. Closing is the last releaser's job."""
        with self._guard:
            self._shares -= 1
            if self._shares > 0:
                return
            fd, self._fd = self._fd, -1
        if fd >= 0:
            os.close(fd)


def _lock_path(work_dir: Path) -> Path:
    return work_dir.with_name(work_dir.name + WORKSPACE_LOCK_SUFFIX)


def claim_workspace(work_dir: Path, attempt: int) -> tuple[WorkspaceClaim, bool]:
    """Take this attempt's exclusive claim on `work_dir`, and say whether to resume.

    The database fence stops a superseded attempt writing to `compute.jobs`. It
    does nothing about the *filesystem*: the workspace is keyed by simulation
    id, not by attempt, and a kernel thread abandoned mid-step keeps writing
    into it. A replacement attempt resuming from those checkpoints could read a
    half-written one -- which is worse than a confusing status, because a
    corrupted checkpoint yields a wrong scientific result rather than an error.

    `flock` is the right primitive because of how it is released. It is held
    against the open file description, so a second attempt is refused even from
    another thread of the same process (which is exactly the zombie case, and
    what a concurrency above one makes possible) -- and the kernel drops it when
    the holding **process** dies, SIGKILL included. So an ordinary worker crash
    still leaves the workspace resumable, which is the behaviour
    `crash_recovery_e2e.sh` scenario 1 depends on, while a live zombie does not.

    The returned claim carries two shares, because the claim has to outlast the
    kernel: `complete_job` reads the result files out of this same directory
    after the kernel thread has returned, and a lease lost in between would
    otherwise let a redelivered attempt start writing there mid-upload.
    """
    lock_path = _lock_path(work_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            # Transient on purpose: the previous attempt's thread unwinds at
            # its next progress write, which the database fence refuses, so
            # the workspace frees itself. rqueue's backoff is the wait.
            raise TransientInfraError(
                f"simulation workspace {work_dir.name} is still held by an "
                "earlier attempt"
            ) from e
        os.ftruncate(fd, 0)
        os.write(fd, f"attempt {attempt}\n".encode())
        # Evaluated under the lock: without it, "are there checkpoints to
        # resume from" is a question about a directory someone else may be
        # halfway through writing.
        return WorkspaceClaim(fd), work_dir.exists()
    except BaseException:
        # Once the descriptor exists, this function owns closing it until the
        # claim has been handed to the caller. This also covers failures after
        # flock succeeds, such as ftruncate/write, and constructor failures.
        with contextlib.suppress(OSError):
            os.close(fd)
        raise


async def _release_unreceived_claim(
    claim_future: asyncio.Future[tuple[WorkspaceClaim, bool]],
) -> None:
    """Release a claim whose thread completed after its waiter was cancelled."""
    try:
        claim, _resume = await claim_future
    except BaseException:
        return
    claim.release()
    claim.release()


async def _claim_workspace_safely(
    work_dir: Path, attempt: int
) -> tuple[WorkspaceClaim, bool]:
    """Claim a workspace without losing a result to cancellation.

    `asyncio.to_thread` cannot stop the thread that has already acquired the
    lock. Shielding its task lets that thread finish, while the detached drain
    takes ownership of a returned claim if cancellation wins the handoff
    before this coroutine receives it.
    """
    claim_future = asyncio.create_task(
        asyncio.to_thread(claim_workspace, work_dir, attempt)
    )
    try:
        return await asyncio.shield(claim_future)
    except asyncio.CancelledError:
        drain = asyncio.create_task(_release_unreceived_claim(claim_future))
        _CLAIM_DRAIN_TASKS.add(drain)
        drain.add_done_callback(_CLAIM_DRAIN_TASKS.discard)
        raise


def remove_workspace(work_dir: Path) -> bool:
    """Remove a workspace and its lock, if nothing still holds the lock.

    Taking the lock before unlinking it is what makes removal safe, and the
    ordering is not fussiness. `unlink` on a locked file is the classic `flock`
    footgun: it removes the directory entry while the holder keeps its lock on
    the now-orphaned inode, so the next `O_CREAT` at that path makes a *new*
    inode and locks it uncontended -- leaving two threads each believing they
    own the workspace exclusively. The sweep can reach a job whose row is
    terminal while its kernel thread is still alive, so this is reachable.

    Returns whether the workspace was removed. A refusal is not an error: the
    next sweep tries again, and until then the directory is exactly where its
    owner expects it.
    """
    lock_path = _lock_path(work_dir)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        # No lock file and none creatable -- nothing has ever claimed this.
        shutil.rmtree(work_dir, ignore_errors=True)
        return True
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            logger.info(
                "Workspace %s is still held; leaving it for the next sweep",
                work_dir.name,
            )
            return False
        shutil.rmtree(work_dir, ignore_errors=True)
        with contextlib.suppress(OSError):
            lock_path.unlink()
    finally:
        os.close(fd)
    return True


async def run_simulation_task(compute_job_id: uuid.UUID, context: TaskContext) -> None:
    """Run one simulation end to end, streaming progress into compute.jobs."""
    async with db.acquire() as conn:
        row = await repository.fetch_by_id(conn, compute_job_id)
    if row is None:
        # There is no attempt at which this job could succeed.
        raise PermanentFailure(f"Unknown compute job {compute_job_id}")

    simulation_id: uuid.UUID = row["simulation_id"]
    work_dir = JOBS_DIR / str(simulation_id)
    data = EarthquakeInput(**row["input_params"])

    # The claim is the decision. Reading `row["status"]` above and branching on
    # it would be the same check-then-write gap the owner_attempt fence exists
    # to close: an attempt completing between that SELECT and this UPDATE could
    # still have its `completed` overwritten with `running`.
    async with db.acquire() as conn:
        claimed = await repository.mark_started(
            conn, compute_job_id, simulation_id, context.attempt
        )
    if not claimed:
        await _stand_down(compute_job_id, work_dir, context.attempt)
        return

    # Captured before the hop into the thread: the callback below runs on a
    # worker thread and has to get back to the loop that owns the pool.
    loop = asyncio.get_running_loop()
    # Set when this attempt's coroutine is cancelled out from under the thread
    # still running the kernel. See "Abandoned attempts" in the module docstring.
    abandoned = threading.Event()

    def on_progress(message: str, details: dict[str, Any]) -> None:
        if abandoned.is_set():
            # Raising, rather than returning quietly, is the point: it unwinds
            # `run_simulation` and ends the thread at this step boundary
            # instead of letting it burn a core on work nobody will read.
            raise AbandonedAttempt(
                f"attempt {context.attempt} of compute job {compute_job_id} "
                "no longer owns this job"
            )
        # Blocking on the result keeps the old synchronous contract: progress
        # is durable before the simulation moves on, and a write that fails
        # surfaces in the simulation rather than in a dropped background task.
        written = asyncio.run_coroutine_threadsafe(
            _write_progress(
                compute_job_id, simulation_id, message, details, context.attempt
            ),
            loop,
        ).result()
        if not written:
            # The database refused it: this attempt no longer owns the row, or
            # the row is already finished. Stop the same way as above -- the
            # write was already fenced, so nothing was corrupted; there is just
            # no reason to keep running.
            abandoned.set()
            raise AbandonedAttempt(
                f"attempt {context.attempt} of compute job {compute_job_id} "
                "no longer owns this job"
            )

    def run_kernel(claim: WorkspaceClaim, resume: bool) -> Any:
        try:
            # Keep outputs and checkpoints when a retry has a work directory.
            return run_simulation(
                data, work_dir, resume=resume, on_progress=on_progress
            )
        finally:
            # On this thread, so the claim is given back when the *thread*
            # stops writing -- which is not when the coroutine stops waiting.
            claim.release()

    claim: WorkspaceClaim | None = None
    try:
        # rqueue installs a ThreadPoolExecutor sized from the worker's
        # concurrency as the loop's default executor, so these hops are capacity
        # bounded without building an executor here.
        held, resume = await _claim_workspace_safely(work_dir, context.attempt)
        claim = held
        result = await asyncio.to_thread(run_kernel, held, resume)
        async with db.acquire() as conn:
            # Still under this attempt's claim: complete_job reads the result
            # files back out of the workspace to upload them, and a lease lost
            # in the moment between the kernel returning and the upload
            # finishing would otherwise let a redelivered attempt take the
            # freed lock and start writing into the directory being read.
            recorded = await repository.complete_job(conn, row, result, context.attempt)
    except asyncio.CancelledError:
        # rqueue cancels this coroutine when the heartbeat finds the lease gone.
        # The coroutine ends here; the OS thread underneath it does not, because
        # Python cannot kill a thread. Tell it to stop.
        abandoned.set()
        raise
    except AbandonedAttempt as e:
        # A refused write, not a broken run. This is the one path where the
        # coroutine is still live when the guard fires, so the exception really
        # does arrive here -- and letting it fall through to `except Exception`
        # would spend a `rqueue.job.failed`, a `_fail_terminal`, and two
        # exception tracebacks on the fence doing exactly its job. rqueue's
        # failure accounting has to mean genuine failures, or it means nothing.
        #
        # `CancelJob` is the honest signal: stop, do not retry. Reaching here
        # means a newer attempt owns the row or the job is already terminal,
        # both of which imply this attempt's lease is gone, so rqueue's
        # finalization will hit `LeaseLost` and log that instead. If the lease
        # somehow survived, the job becomes `cancelled` -- which reconciliation
        # already treats as the queue giving up, so `compute.jobs` is repaired
        # rather than left running forever.
        logger.warning("Standing down attempt %d: %s", context.attempt, e)
        raise CancelJob(str(e)) from e
    except Exception as e:
        # Finalization is as retryable as the run: a MinIO outage raises
        # TransientInfraError from complete_job, and without this the retry
        # happened but nobody watching compute.jobs was ever told.
        # record_failure refuses to touch a row that is already terminal, so an
        # UPDATE that committed before the connection dropped is not reported
        # as a failure.
        await _record_failure(compute_job_id, simulation_id, e, context.attempt)
        raise
    finally:
        if claim is not None:
            claim.release()

    if not recorded:
        # Superseded between the last progress write and here. `complete_job`
        # has already logged the orphaned upload. Stand down the same way a
        # refused progress write does -- and in particular do not remove the
        # work directory, which the attempt that took over is resuming from.
        raise CancelJob(
            f"attempt {context.attempt} of compute job {compute_job_id} "
            "no longer owns this job"
        )

    # The claim is given back above, and remove_workspace re-takes it itself:
    # unlinking a lock file somebody still holds is what creates two owners.
    await asyncio.to_thread(remove_workspace, work_dir)


async def _stand_down(compute_job_id: uuid.UUID, work_dir: Path, attempt: int) -> None:
    """Handle a claim this attempt did not win.

    The claim already told us we lost; this only decides which of the two ways
    to lose it was, so a stale read here is harmless.
    """
    async with db.acquire() as conn:
        current = await repository.fetch_by_id(conn, compute_job_id)

    if current is not None and current["status"] == JobStatus.COMPLETED.value:
        # rqueue is at-least-once by design (REQUIREMENTS.md ss3): a worker that
        # died between complete_job's commit and rqueue's own finalization gets
        # this job delivered again. The result is already durable, so let this
        # delivery succeed, and finish the one step the dead attempt may not
        # have reached.
        logger.info(
            "Compute job %s is already completed; skipping redelivered attempt %d",
            compute_job_id,
            attempt,
        )
        await asyncio.to_thread(remove_workspace, work_dir)
        return

    logger.warning(
        "Compute job %s is owned by a newer attempt than %d; standing down",
        compute_job_id,
        attempt,
    )
    raise CancelJob(
        f"attempt {attempt} of compute job {compute_job_id} no longer owns this job"
    )


async def _write_progress(
    compute_job_id: uuid.UUID,
    simulation_id: uuid.UUID,
    message: str,
    details: dict[str, Any],
    attempt: int,
) -> bool:
    async with db.acquire() as conn:
        return await repository.record_progress(
            conn, compute_job_id, simulation_id, message, details, attempt
        )


async def _record_failure(
    compute_job_id: uuid.UUID,
    simulation_id: uuid.UUID,
    exc: Exception,
    attempt: int,
) -> None:
    """Persist a failed run, matching the decision rqueue is about to make.

    `should_retry` is the same predicate `rqueue.Worker` consults, so the
    `details` a watching client sees ("retrying" versus terminal) cannot drift
    from what the queue actually does with the job.
    """
    try:
        async with db.acquire() as conn:
            await repository.record_failure(
                conn,
                compute_job_id,
                simulation_id,
                exc,
                step=await repository.get_current_step(conn, compute_job_id),
                will_retry=TRANSIENT_RETRY.should_retry(exc, attempt=attempt),
                attempt=attempt,
            )
    except Exception:
        # A database outage here must not replace the failure it is reporting.
        logger.exception("Could not record the failure of job %s", compute_job_id)


async def sweep_abandoned_work_dirs() -> None:
    """Delete terminal-job workspaces older than WORK_DIR_TTL."""
    cutoff = datetime.now().astimezone() - WORK_DIR_TTL
    for simulation_id in await repository.list_abandoned_work_dirs(cutoff):
        await asyncio.to_thread(remove_workspace, JOBS_DIR / simulation_id)


async def reconcile_terminal_jobs(*, grace: timedelta = RECONCILE_GRACE) -> None:
    """Sync compute.jobs to jobs the queue finished without the run reporting.

    Procrastinate's reaper used to close this gap for one of its causes: a
    stalled job whose retries ran out. rqueue's fenced leases replace the
    queue-state half of that reaper outright and do it better, but the half
    that wrote `compute.jobs` had no replacement, and the same hole is reachable
    from more than stalling alone. This is that replacement, written against
    the condition rather than against any one of the paths that reaches it.
    """
    queue = get_queue()
    reconciled = await repository.reconcile_terminal_jobs(
        queue_schema=queue.schema,
        queue_name=queue.name,
        task=RUN_SIMULATION,
        cutoff=datetime.now().astimezone() - grace,
    )
    for compute_job_id in reconciled:
        # Never routine: every one of these is a run that ended without being
        # able to say so, so it is worth a line in the worker log.
        logger.warning(
            "compute job %s was terminal in the queue but still unfinished; "
            "status reconciled to failed",
            compute_job_id,
        )


async def _run_periodically(
    description: str,
    run_pass: Callable[[], Awaitable[None]],
    stop: asyncio.Event,
    interval: float,
) -> None:
    """Run one maintenance pass on an interval until `stop` is set.

    Plain asyncio tasks in the worker process, not `rqueue.Scheduler` jobs.
    Both passes are idempotent and harmless to run twice, so neither needs the
    scheduler's occurrence-key machinery, and a scheduler process would be dead
    weight beside them. A failed pass is logged and the loop continues: a
    database outage must not silently end maintenance for the process lifetime.
    """
    while not stop.is_set():
        try:
            await run_pass()
        except Exception:
            logger.exception("%s failed", description)
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(interval):
                await stop.wait()


async def run_periodic_sweep(
    stop: asyncio.Event, *, interval: float = SWEEP_INTERVAL_SECONDS
) -> None:
    """Sweep abandoned workspaces until `stop` is set."""
    await _run_periodically(
        "Sweep of abandoned work directories",
        lambda: sweep_abandoned_work_dirs(),
        stop,
        interval,
    )


async def run_periodic_reconcile(
    stop: asyncio.Event, *, interval: float = RECONCILE_INTERVAL_SECONDS
) -> None:
    """Reconcile queue-terminal jobs until `stop` is set."""
    await _run_periodically(
        "Reconciliation of queue-terminal jobs",
        lambda: reconcile_terminal_jobs(),
        stop,
        interval,
    )


def register_tasks(queue: Queue) -> Queue:
    """Register every task this deployment runs, and return the queue.

    Both processes register. The producer needs it too: `Queue.build_insert`
    reads the registration to stamp the task's retry budget and timeout onto
    the row it writes, so an unregistered producer would quietly enqueue jobs
    with the queue's defaults instead of TRANSIENT_RETRY's.
    """
    if RUN_SIMULATION not in queue.tasks:
        queue.register(
            name=RUN_SIMULATION,
            handler=run_simulation_task,
            decoder=decode_payload,
            retry=TRANSIENT_RETRY,
            timeout=RUN_TIMEOUT_SECONDS,
        )
    return queue
