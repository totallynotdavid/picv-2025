"""Behavior of the GMT-backed maximum-height plot."""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pygmt
import pytest
import xarray as xr

from tsdhn.render.maxola import (
    GridConfig,
    StyleConfig,
    TidalStation,
    add_tidal_stations,
    cleanup_files,
    create_cpt_files,
    create_grid_dataarray,
    generate_maxola_plot,
)

MECA_LINE = "210.25 -9.50 10 20 30 40 7.5 210 -9 event\n"


def _psconvert_works(tmp_path_factory: pytest.TempPathFactory) -> bool:
    """Return whether GMT and Ghostscript can render a PDF here."""
    probe_dir = tmp_path_factory.mktemp("psconvert-probe")
    try:
        fig = pygmt.Figure()
        fig.basemap(region=[0, 1, 0, 1], projection="X1c", frame=False)
        fig.savefig(str(probe_dir / "probe.pdf"))
    except pygmt.exceptions.GMTCLibError:
        return False
    return True


def test_create_cpt_files_writes_the_legacy_wave_height_convention(
    tmp_path: Path,
) -> None:
    depth_cpt, hgt_cpt = create_cpt_files(tmp_path)

    assert depth_cpt.is_file()
    assert hgt_cpt.is_file()
    tail = hgt_cpt.read_text().splitlines()[-3:]
    assert tail == ["B 0 0 255", "F 255 0 0", "N 255 255 255"]


def test_add_tidal_stations_skips_when_none_are_active(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fig = pygmt.Figure()
    fig.basemap(region=[190, 290, -60, 60], projection="M10c", frame=True)
    inactive = TidalStation(lon=210.0, lat=-10.0, code="X", name="x", active=False)

    with caplog.at_level(logging.WARNING):
        add_tidal_stations(fig, [inactive], StyleConfig())

    assert "No active tidal stations" in caplog.text


class _RecordingFigure:
    """Record the renderer's semantic drawing operations, not GMT internals."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _record(self, name: str, **kwargs: Any) -> None:
        self.calls.append((name, kwargs))

    def shift_origin(self, **kwargs: Any) -> None:
        self._record("shift_origin", **kwargs)

    def grdimage(self, **kwargs: Any) -> None:
        self._record("grdimage", **kwargs)

    def coast(self, **kwargs: Any) -> None:
        self._record("coast", **kwargs)

    def plot(self, **kwargs: Any) -> None:
        self._record("plot", **kwargs)

    def text(self, **kwargs: Any) -> None:
        self._record("text", **kwargs)

    def meca(self, **kwargs: Any) -> None:
        self._record("meca", **kwargs)

    def savefig(self, path: str) -> None:
        self._record("savefig", path=path)
        Path(path).write_bytes(b"rendered plot")


def test_generate_maxola_plot_requests_the_complete_plot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The plot must contain the map, context, stations, mechanism, and legend."""
    figure = _RecordingFigure()
    monkeypatch.setattr(pygmt, "Figure", lambda: figure)
    monkeypatch.setattr(
        "tsdhn.render.maxola.process_grid", lambda work_dir, grid_config: _tiny_grid()
    )
    (tmp_path / "meca.dat").write_text(MECA_LINE, encoding="utf-8")

    generate_maxola_plot(tmp_path)

    names = [name for name, _ in figure.calls]
    assert names[0] == "shift_origin"
    assert names[-1] == "savefig"
    assert {"grdimage", "coast", "plot", "meca"} <= set(names)
    text_values = [kwargs["text"] for name, kwargs in figure.calls if name == "text"]
    assert {"TALA", "CALL", "MATA", "+", "PACIFIC OCEAN"} <= set(text_values)


def test_cleanup_files_removes_existing_and_ignores_missing(tmp_path: Path) -> None:
    present = tmp_path / "present.txt"
    present.write_text("x")
    missing = tmp_path / "missing.txt"

    cleanup_files([present, missing])

    assert not present.exists()


def _tiny_grid() -> xr.DataArray:
    config = GridConfig(ncols=4, nrows=3, dx=111.1994)
    data = np.linspace(0, 1, 12, dtype=np.float32).reshape(3, 4)
    return create_grid_dataarray(data, config)


def test_generate_maxola_plot_produces_a_pdf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    if not _psconvert_works(tmp_path_factory):
        pytest.skip("this machine's Ghostscript cannot run GMT's psconvert")
    monkeypatch.setattr(
        "tsdhn.render.maxola.process_grid", lambda work_dir, grid_config: _tiny_grid()
    )
    (tmp_path / "meca.dat").write_text(MECA_LINE, encoding="utf-8")

    generate_maxola_plot(tmp_path)

    output = tmp_path / "maxola.pdf"
    assert output.is_file()
    assert output.stat().st_size > 0


def test_generate_maxola_plot_cleans_up_cpt_files_even_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def boom(work_dir: Path, grid_config: GridConfig) -> xr.DataArray:
        raise RuntimeError("grid processing error")

    monkeypatch.setattr("tsdhn.render.maxola.process_grid", boom)

    with pytest.raises(RuntimeError, match="grid processing error"):
        generate_maxola_plot(tmp_path)

    assert not (tmp_path / "depth.cpt").exists()
    assert not (tmp_path / "hgt.cpt").exists()
