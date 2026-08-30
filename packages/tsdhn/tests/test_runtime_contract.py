import subprocess
from pathlib import Path
from typing import Self

import numpy as np
import pygmt
import pytest
from pygmt.enums import GridRegistration, GridType

from tsdhn.pipeline.types import ProcessingStep
from tsdhn.render import ttt_inverso
from tsdhn.render.maxola import GridConfig, load_stations, process_grid
from tsdhn.runtime import (
    REQUIRED_MODEL_FILES,
    RuntimeContext,
)
from tsdhn.utils.file_utils import (
    WORKSPACE_DIRS,
    WORKSPACE_INPUTS,
    prepare_simulation_workspace,
)
from tsdhn.utils.processing import process_step


def _create_model_dir(root: Path) -> Path:
    model_dir = root / "model"
    model_dir.mkdir()
    for dirname in WORKSPACE_DIRS:
        (model_dir / dirname).mkdir()
    for relative_name in REQUIRED_MODEL_FILES:
        path = model_dir / relative_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative_name}\n", encoding="utf-8")
    return model_dir


def test_runtime_context_reports_missing_managed_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TSDHN_MODEL_DIR", raising=False)
    monkeypatch.setenv("TSDHN_DATA_HOME", str(tmp_path / "missing"))

    with pytest.raises(RuntimeError, match="tsdhn assets install"):
        RuntimeContext.resolve()


def test_runtime_resolves_an_explicit_model_dir(tmp_path: Path) -> None:
    model_dir = _create_model_dir(tmp_path)

    runtime = RuntimeContext.resolve(model_dir=model_dir)

    assert runtime.model_dir == model_dir.resolve()


def test_runtime_resolves_the_model_dir_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = _create_model_dir(tmp_path)
    monkeypatch.setenv("TSDHN_MODEL_DIR", str(model_dir))

    assert RuntimeContext.resolve().model_dir == model_dir.resolve()


def test_runtime_reports_external_tool_capabilities(tmp_path: Path) -> None:
    """Report GMT and ttt_client when they are resolved from PATH."""
    model_dir = _create_model_dir(tmp_path)

    runtime = RuntimeContext.resolve(model_dir=model_dir)

    assert set(runtime.capabilities) == {"gmt", "ttt_client"}
    assert not hasattr(runtime, "tools_dir")


def test_prepare_simulation_workspace_links_only_required_inputs(
    tmp_path: Path,
) -> None:
    work_dir = tmp_path / "work"
    model_dir = _create_model_dir(tmp_path)

    generated_seed = model_dir / "zfolder" / "green.dat"
    generated_seed.write_text("stale generated output\n", encoding="utf-8")

    work_dir.mkdir()
    (work_dir / "old.txt").write_text("old workspace\n", encoding="utf-8")

    prepare_simulation_workspace(model_dir, work_dir)

    assert not (work_dir / "old.txt").exists()
    for dirname in WORKSPACE_DIRS:
        assert (work_dir / dirname).is_dir()
    for relative_name in WORKSPACE_INPUTS:
        assert (work_dir / relative_name).is_file()

    assert not (work_dir / "zfolder" / "green.dat").exists()


def test_load_stations_uses_package_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    stations = load_stations()

    assert {station.code for station in stations if station.active} == {
        "TALA",
        "CALL",
        "MATA",
    }


def test_process_grid_returns_pixel_registered_dataarray(tmp_path: Path) -> None:
    work_dir = tmp_path / "work"
    zfolder = work_dir / "zfolder"
    zfolder.mkdir(parents=True)
    np.savetxt(zfolder / "zmax_a.grd", np.arange(12, dtype=np.float32))

    grid_config = GridConfig(ncols=4, nrows=3, dx=111.1994)
    grid = process_grid(work_dir, grid_config)

    assert grid.dims == ("lat", "lon")
    assert grid.shape == (3, 4)
    assert grid.gmt.registration is GridRegistration.PIXEL
    assert grid.gmt.gtype is GridType.GEOGRAPHIC
    assert grid.lon.to_numpy().tolist() == pytest.approx(
        [128.02827778, 128.02927778, 128.03027778, 128.03127778]
    )
    assert grid.lat.to_numpy().tolist() == pytest.approx(
        [-76.00505556, -76.00405556, -76.00305556]
    )
    np.testing.assert_allclose(
        grid.to_numpy(),
        np.array(
            [
                [0.0, 1.09, 2.18, 3.27],
                [4.36, 5.45, 6.55, 7.64],
                [8.73, 9.82, 10.91, 12.0],
            ],
            dtype=np.float32,
        ),
    )


@pytest.mark.parametrize(
    ("latitude", "expected_location"),
    [
        (-10.0, "210.25/-10.00"),
        (-9.5, "210.25/-9.50"),
        (9.5, "210.25/9.50"),
        (10.0, "210.25/10.00"),
    ],
)
def test_ttt_epicenter_format_matches_ttt_client_widths(
    latitude: float, expected_location: str
) -> None:
    assert ttt_inverso.format_ttt_epicenter(210.25, latitude) == expected_location


def test_ttt_inverso_uses_shared_meca_spec_for_epicenter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    working_dir = tmp_path / "ttt"
    working_dir.mkdir()
    (tmp_path / "meca.dat").write_text(
        "210.25 -9.50 10 20 30 40 7.5 210 -9 event\n",
        encoding="utf-8",
    )
    commands: list[tuple[list[str], Path]] = []
    module_calls: list[tuple[str, list[str]]] = []

    def fake_resolve(executable: str) -> Path:
        return Path("/tools") / executable

    def fake_run(
        args: list[str],
        *,
        cwd: Path,
        check: bool,
        stdout: int,
        stderr: int,
    ) -> subprocess.CompletedProcess[str]:
        commands.append((args, cwd))
        return subprocess.CompletedProcess(args, 0)

    class FakeSession:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def call_module(self, module: str, args: list[str]) -> None:
            module_calls.append((module, args))

    monkeypatch.setattr(ttt_inverso, "resolve", fake_resolve)
    monkeypatch.setattr("tsdhn.render.ttt_inverso.subprocess.run", fake_run)
    monkeypatch.setattr(ttt_inverso, "Session", FakeSession)

    ttt_inverso.ttt_inverso_python(working_dir)

    assert commands == [
        (
            [
                "/tools/ttt_client",
                "cortado.i2",
                "-E210.25/-9.50",
                "-Tttt.b",
                "-VL",
            ],
            working_dir,
        ),
    ]
    grid_arg = f"{working_dir / 'ttt.b'}=bf"
    assert module_calls == [("grdmath", [grid_arg, "1.0", "MUL", "=", grid_arg])]


def test_ttt_inverso_keeps_full_meca_dat_validation(tmp_path: Path) -> None:
    working_dir = tmp_path / "ttt"
    working_dir.mkdir()
    (tmp_path / "meca.dat").write_text("210.25 -9.50\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not contain exactly 10 values"):
        ttt_inverso.ttt_inverso_python(working_dir)


def test_ttt_inverso_surfaces_a_grdmath_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    working_dir = tmp_path / "ttt"
    working_dir.mkdir()
    (tmp_path / "meca.dat").write_text(
        "210.25 -9.50 10 20 30 40 7.5 210 -9 event\n",
        encoding="utf-8",
    )

    class BrokenSession:
        def __enter__(self) -> BrokenSession:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def call_module(self, module: str, args: list[str]) -> None:
            raise pygmt.exceptions.GMTError("grdmath failed")

    monkeypatch.setattr(ttt_inverso, "resolve", lambda name: Path("/tools") / name)
    monkeypatch.setattr(
        "tsdhn.render.ttt_inverso.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0),
    )
    monkeypatch.setattr(ttt_inverso, "Session", BrokenSession)

    with pytest.raises(pygmt.exceptions.GMTError, match="grdmath failed"):
        ttt_inverso.ttt_inverso_python(working_dir)


def test_process_step_runs_a_python_step_and_validates_its_outputs(
    tmp_path: Path,
) -> None:
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    def write_result(working_dir: Path) -> None:
        (working_dir / "ran.txt").write_text("ok\n", encoding="utf-8")

    process_step(
        ProcessingStep(name="hello", outputs=("ran.txt",), runner=write_result),
        work_dir,
    )

    assert (work_dir / "ran.txt").read_text(encoding="utf-8").strip() == "ok"
