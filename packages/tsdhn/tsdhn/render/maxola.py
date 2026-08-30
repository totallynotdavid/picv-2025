import logging
import shutil
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import numpy as np
import pygmt
import xarray as xr
import yaml
from pygmt.enums import GridRegistration, GridType
from pygmt.helpers import GMTTempFile

from tsdhn.render.meca import read_meca_spec

logger = logging.getLogger(__name__)

MAX_WAVE_HEIGHT_METERS = 12.0
LEGACY_GRID_DECIMALS = 2


@dataclass(frozen=True)
class GridConfig:
    ncols: int = 2461
    nrows: int = 2056
    dx: float = 7412.9951096
    xllcorner: float = 128.02777778
    yllcorner: float = -76.00555556
    cellsize: float = dx / 1000.0 / 111.1994

    def __post_init__(self) -> None:
        object.__setattr__(self, "cellsize", self.dx / 1000.0 / 111.1994)


@dataclass(frozen=True)
class StyleConfig:
    font_primary: str = "10p,Helvetica-Bold,black"
    font_secondary: str = "12p"
    tidal_marker: str = "t0.35c"
    tidal_pen: str = "0.5p,black"
    tidal_fill: str = "blue"
    meca_scale: str = "0.23c"
    coastline_pen: str = "0.5p,black"


@dataclass(frozen=True)
class TidalStation:
    lon: float
    lat: float
    code: str
    name: str
    active: bool = True
    annotation_offset: str = "0.1c"


def load_stations() -> list[TidalStation]:
    stations_path = files("tsdhn.render.data").joinpath("stations.yml")
    logger.info("Loading stations configuration: %s", stations_path)
    try:
        with stations_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "stations" not in data:
            raise ValueError("Invalid stations configuration: 'stations' key missing")

        return [TidalStation(**station) for station in data["stations"]]

    except (yaml.YAMLError, TypeError, KeyError) as e:
        logger.error(f"Failed to parse stations configuration: {e!s}")
        raise ValueError(f"Invalid stations configuration: {e!s}") from e


def create_cpt_files(work_dir: Path) -> tuple[Path, Path]:
    """Create GMT color palette tables for depth and wave height."""
    depth_cpt = work_dir / "depth.cpt"
    hgt_cpt = work_dir / "hgt.cpt"

    try:
        with GMTTempFile() as temp_cpt:
            pygmt.makecpt(cmap="globe", output=temp_cpt.name)
            shutil.move(temp_cpt.name, depth_cpt)

        with GMTTempFile() as temp_cpt:
            # Preserve the legacy blue-to-red wave-height scale.
            pygmt.makecpt(
                cmap="polar",
                series="-0.5/0.5/0.01",
                continuous=True,
                output=temp_cpt.name,
            )
            shutil.move(temp_cpt.name, hgt_cpt)

            with open(hgt_cpt, "a") as f:
                f.write("B 0 0 255\nF 255 0 0\nN 255 255 255\n")

    except pygmt.exceptions.GMTError as e:
        logger.error(f"CPT creation failed: {e!s}")
        raise RuntimeError("CPT generation error") from e

    return depth_cpt, hgt_cpt


def process_grid(work_dir: Path, grid_config: GridConfig) -> xr.DataArray:
    """Normalize the legacy max-height grid into a PyGMT-ready data array."""
    grid_path = work_dir / "zfolder" / "zmax_a.grd"

    if not grid_path.exists():
        logger.error("Grid file missing: %s", grid_path)
        raise FileNotFoundError(f"Grid file not found: {grid_path}")

    try:
        values = np.loadtxt(grid_path, dtype=np.float32)
        max_height_grid = reshape_model_grid(values, grid_config)
        normalized_grid = normalize_max_height_grid(max_height_grid)
        return create_grid_dataarray(normalized_grid, grid_config)

    except (ValueError, OSError) as e:
        logger.error("Grid processing failed: %s", e)
        raise RuntimeError("Grid processing error") from e


def reshape_model_grid(values: np.ndarray, grid_config: GridConfig) -> np.ndarray:
    expected_size = grid_config.ncols * grid_config.nrows
    if values.size != expected_size:
        raise ValueError(
            "Unexpected zmax_a.grd size: "
            f"expected {expected_size} values from "
            f"{grid_config.ncols}x{grid_config.nrows} grid, got {values.size}"
        )

    model_grid = values.reshape((grid_config.ncols, grid_config.nrows), order="F")
    return np.flipud(model_grid.T)


def normalize_max_height_grid(max_height_grid: np.ndarray) -> np.ndarray:
    """Rescale solver values for display with a 12 m maximum."""
    finite_values = max_height_grid[np.isfinite(max_height_grid)]
    if finite_values.size == 0:
        return np.zeros_like(max_height_grid, dtype=np.float32)

    max_value = np.max(finite_values)
    if max_value == 0:
        return np.zeros_like(max_height_grid, dtype=np.float32)

    normalized_grid = (MAX_WAVE_HEIGHT_METERS * max_height_grid) / max_value

    return np.asarray(
        np.round(normalized_grid, LEGACY_GRID_DECIMALS),
        dtype=np.float32,
    )


def create_grid_dataarray(data: np.ndarray, grid_config: GridConfig) -> xr.DataArray:
    """Build a pixel-registered geographic grid for PyGMT."""
    lon = cell_centers(grid_config.xllcorner, grid_config.ncols, grid_config.cellsize)
    lat = cell_centers(grid_config.yllcorner, grid_config.nrows, grid_config.cellsize)

    grid = xr.DataArray(
        np.flipud(data),
        dims=("lat", "lon"),
        coords={"lat": lat, "lon": lon},
        name="z",
    )

    grid.gmt.registration = GridRegistration.PIXEL
    grid.gmt.gtype = GridType.GEOGRAPHIC
    return grid


def cell_centers(origin: float, count: int, cellsize: float) -> np.ndarray:
    return origin + (np.arange(count, dtype=np.float64) + 0.5) * cellsize


def add_coastline(fig: pygmt.Figure, style_config: StyleConfig) -> None:
    fig.coast(
        shorelines=style_config.coastline_pen,
        area_thresh=1000,
        borders=["1/0.5p,black"],
        resolution="i",
        land="gray",
        frame=["WSen", "xa20f10", "ya20f10"],
    )


def add_tidal_stations(
    fig: pygmt.Figure, stations: list[TidalStation], style_config: StyleConfig
) -> None:
    active_stations = [s for s in stations if s.active]

    if not active_stations:
        logger.warning("No active tidal stations found")
        return

    stations_array = np.array([(s.lon - 1, s.lat) for s in active_stations])

    try:
        fig.plot(
            x=stations_array[:, 0],
            y=stations_array[:, 1],
            style=style_config.tidal_marker,
            pen=style_config.tidal_pen,
            fill=style_config.tidal_fill,
        )

        for station in active_stations:
            fig.text(
                x=station.lon,
                y=station.lat,
                text=station.code,
                font=style_config.font_primary,
                justify="LT",
                offset=station.annotation_offset,
            )
    except pygmt.exceptions.GMTError as e:
        logger.warning(f"Tidal station plotting failed: {e!s}")


def add_meca_data(fig: pygmt.Figure, work_dir: Path, style_config: StyleConfig) -> None:
    meca_file = work_dir / "meca.dat"

    if meca_file.exists():
        try:
            spec = read_meca_spec(meca_file)
            fig.meca(
                spec=spec,
                scale=style_config.meca_scale,
                compression_fill="blue",
                convention="mt",
            )
        except Exception as e:
            logger.warning("Mechanism plot failed: %s", e)


def add_legend(fig: pygmt.Figure, style_config: StyleConfig) -> None:
    fig.text(
        x=210,
        y=-10,
        text="+",
        font="16p,Helvetica-Bold,black",
        justify="CM",
    )
    fig.text(
        x=210,
        y=10,
        text="PACIFIC OCEAN",
        font=style_config.font_primary,
        justify="CB",
    )


def cleanup_files(file_paths: list[Path]) -> None:
    for path in file_paths:
        try:
            path.unlink(missing_ok=True)
        except (PermissionError, OSError) as e:
            logger.debug(f"Cleanup failed for {path}: {e!s}")


def generate_maxola_plot(work_dir: Path) -> None:
    grid_config = GridConfig()
    style_config = StyleConfig()

    stations = load_stations()

    files_to_cleanup: list[Path] = []

    pygmt.config(
        MAP_FRAME_TYPE="plain",
        FONT_ANNOT_PRIMARY=style_config.font_secondary,
        FONT_LABEL=style_config.font_secondary,
        FONT_TITLE=style_config.font_secondary,
        PS_MEDIA="A4",
    )

    try:
        depth_cpt, hgt_cpt = create_cpt_files(work_dir)
        files_to_cleanup.extend([depth_cpt, hgt_cpt])

        max_height_grid = process_grid(work_dir, grid_config)

        fig = pygmt.Figure()
        fig.shift_origin(xshift="4.2c", yshift="10.0c")

        # Center the projection on the Pacific basin.
        fig.grdimage(
            grid=max_height_grid,
            cmap=hgt_cpt,
            projection="A210/-10/5.0i",
        )

        add_coastline(fig, style_config)
        add_tidal_stations(fig, stations, style_config)
        add_meca_data(fig, work_dir, style_config)
        add_legend(fig, style_config)

        fig.savefig(str(work_dir / "maxola.pdf"))
        logger.info("Tsunami visualization created: %s", work_dir / "maxola")

    except Exception as e:
        logger.error("Plot generation failed: %s", e)
        raise
    finally:
        cleanup_files(files_to_cleanup)
