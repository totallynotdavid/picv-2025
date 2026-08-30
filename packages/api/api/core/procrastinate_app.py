import procrastinate

from api.core.settings import COMPUTE_DATABASE_URL, PROCRASTINATE_SEARCH_PATH

__all__ = ["app"]

app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(
        conninfo=COMPUTE_DATABASE_URL,
        kwargs={"options": f"-c search_path={PROCRASTINATE_SEARCH_PATH}"},
    ),
    import_paths=("api.core.tasks",),
)
