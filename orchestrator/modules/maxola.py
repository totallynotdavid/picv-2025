import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pygmt
import yaml
from pygmt.helpers import GMTTempFile

from orchestrator.modules.point_ttt import read_meca_spec

logger = logging.getLogger(__name__)

CONFIG_DIR = Path("data")


# Grid configuration
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


# Style configuration
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


def load_stations(config_dir: Path) -> List[TidalStation]:
    stations_path = config_dir / "stations.yml"
    logger.info(f"Loading stations configuration: {stations_path}")

    if not stations_path.exists():
        logger.error(f"Stations configuration file not found: {stations_path}")
        raise FileNotFoundError(f"Stations file not found: {stations_path}")

    try:
        with open(stations_path, "r") as f:
            data = yaml.safe_load(f)

        if not data or "stations" not in data:
            raise ValueError("Invalid stations configuration: 'stations' key missing")

        return [TidalStation(**station) for station in data["stations"]]

    except (yaml.YAMLError, TypeError, KeyError) as e:
        logger.error(f"Failed to parse stations configuration: {str(e)}")
        raise ValueError(f"Invalid stations configuration: {str(e)}") from e


def create_cpt_files(work_dir: Path) -> Tuple[Path, Path]:
    """Create custom color palette tables (CPT) for visualization"""
    depth_cpt = work_dir / "depth.cpt"
    hgt_cpt = work_dir / "hgt.cpt"

    try:
        # Create depth color palette
        with GMTTempFile() as temp_cpt:
            pygmt.makecpt(cmap="globe", output=temp_cpt.name)
            Path(temp_cpt.name).rename(depth_cpt)

        # Create height color palette
        with GMTTempFile() as temp_cpt:
            pygmt.makecpt(
                cmap="polar",
                series="-0.5/0.5/0.01",
                continuous=True,
                output=temp_cpt.name,
            )
            Path(temp_cpt.name).rename(hgt_cpt)

            # Append B, F, N entries to height CPT
            with open(hgt_cpt, "a") as f:
                f.write("B 0 0 255\nF 255 0 0\nN 255 255 255\n")

    except pygmt.exceptions.GMTError as e:
        logger.error(f"CPT creation failed: {str(e)}")
        raise RuntimeError("CPT generation error") from e

    return depth_cpt, hgt_cpt


def process_grid(work_dir: Path, grid_config: GridConfig) -> Path:
    """Process and normalize grid data for visualization"""
    grid_path = work_dir / "zfolder" / "zmax_a.grd"

    if not grid_path.exists():
        logger.error(f"Grid file missing: {grid_path}")
        raise FileNotFoundError(f"Grid file not found: {grid_path}")

    try:
        # Load and validate grid data
        data = np.loadtxt(grid_path, dtype=np.float32)
        expected_size = grid_config.ncols * grid_config.nrows

        if data.size != expected_size:
            logger.error(f"Grid size mismatch: {data.size} vs {expected_size}")
            raise ValueError(
                f"Data size mismatch: Expected {expected_size}, got {data.size}"
            )

        # Reshape and process grid data
        arr = data.reshape((grid_config.ncols, grid_config.nrows), order="F")
        processed = np.flipud(arr.T)

        # Normalize values
        max_val = np.nanmax(processed)
        normalized = np.divide(
            12.0 * processed,
            max_val + np.finfo(float).eps,
            out=np.zeros_like(processed),
            where=(max_val != 0),
        )

        # Write processed grid to file
        output_grid = work_dir / "maximo.grd"
        write_grid_file(output_grid, normalized, grid_config)
        return output_grid

    except (ValueError, IOError) as e:
        logger.error(f"Grid processing failed: {str(e)}")
        raise RuntimeError("Grid processing error") from e


def write_grid_file(
    output_path: Path, data: np.ndarray, grid_config: GridConfig
) -> None:
    header = (
        f"ncols {grid_config.ncols}\n"
        f"nrows {grid_config.nrows}\n"
        f"xllcorner {grid_config.xllcorner:.8f}\n"
        f"yllcorner {grid_config.yllcorner:.8f}\n"
        f"cellsize {grid_config.cellsize:.8f}\n"
        "nodata_value -9999\n"
    )

    try:
        with open(output_path, "w") as f:
            f.write(header)
            np.savetxt(f, data, fmt="%8.2f", delimiter="", newline="\n")
    except IOError as e:
        logger.error(f"Grid write failed: {str(e)}")
        raise RuntimeError("Grid file I/O error") from e


def convert_grid_format(input_grid: Path, output_grid: Path) -> None:
    try:
        subprocess.run(
            ["gmt", "grdconvert", str(input_grid), "-G" + str(output_grid)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"GMT command failed: {e.stderr.decode().strip()}")
        raise RuntimeError("GMT grid conversion failed") from e
    except FileNotFoundError:
        logger.error("GMT command not found. Ensure GMT is installed and in PATH.")
        raise RuntimeError("GMT executable not found") from None


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
    fig: pygmt.Figure, stations: List[TidalStation], style_config: StyleConfig
) -> None:
    active_stations = [s for s in stations if s.active]

    if not active_stations:
        logger.warning("No active tidal stations found")
        return

    # Create array of station coordinates
    stations_array = np.array([(s.lon - 1, s.lat) for s in active_stations])

    try:
        # Plot markers
        fig.plot(
            x=stations_array[:, 0],
            y=stations_array[:, 1],
            style=style_config.tidal_marker,
            pen=style_config.tidal_pen,
            fill=style_config.tidal_fill,
        )

        # Add station names
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
        logger.warning(f"Tidal station plotting failed: {str(e)}")


def add_meca_data(fig: pygmt.Figure, work_dir: Path, style_config: StyleConfig) -> None:
    meca_file = work_dir / "meca.dat"

    if meca_file.exists():
        try:
            spec = read_meca_spec(meca_file)
            fig.meca(
                spec=spec,
                scale=style_config.meca_scale,
                compressionfill="blue",
                convention="mt",
            )
        except Exception as e:
            logger.warning(f"Mechanism plot failed: {str(e)}")


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


def cleanup_files(file_paths: List[Path]) -> None:
    for path in file_paths:
        try:
            path.unlink(missing_ok=True)
        except (PermissionError, OSError) as e:
            logger.debug(f"Cleanup failed for {path}: {str(e)}")


def generate_maxola_plot(work_dir: Path) -> None:
    grid_config = GridConfig()
    style_config = StyleConfig()

    stations = load_stations(CONFIG_DIR)

    files_to_cleanup: List[Path] = []

    pygmt.config(
        MAP_FRAME_TYPE="plain",
        FONT_ANNOT_PRIMARY=style_config.font_secondary,
        FONT_LABEL=style_config.font_secondary,
        FONT_TITLE=style_config.font_secondary,
        PS_MEDIA="A4",
    )

    try:
        # Create color palettes
        depth_cpt, hgt_cpt = create_cpt_files(work_dir)
        files_to_cleanup.extend([depth_cpt, hgt_cpt])

        # Process grid data
        maximo_grid = process_grid(work_dir, grid_config)
        maxola_grid = work_dir / "maxola.grd"
        files_to_cleanup.extend([maximo_grid, maxola_grid])

        # Convert grid format
        convert_grid_format(maximo_grid, maxola_grid)

        # Create the figure
        fig = pygmt.Figure()
        fig.shift_origin(xshift="4.2c", yshift="10.0c")

        # Add map of tsunami wave heights
        fig.grdimage(grid=str(maxola_grid), cmap=hgt_cpt, projection="A210/-10/5.0i")

        # Add map elements
        add_coastline(fig, style_config)
        add_tidal_stations(fig, stations, style_config)
        add_meca_data(fig, work_dir, style_config)
        add_legend(fig, style_config)

        # Save the figure
        fig.psconvert(prefix=str(work_dir / "maxola"), fmt="E")
        logger.info(f"Tsunami visualization created: {work_dir / 'maxola'}")

    except Exception as e:
        logger.error(f"Plot generation failed: {str(e)}")
        raise
    finally:
        cleanup_files(files_to_cleanup)
