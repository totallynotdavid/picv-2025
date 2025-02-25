import logging
import subprocess
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pygmt

from orchestrator.modules.point_ttt import read_meca_spec

logger = logging.getLogger(__name__)

# Constants
NCOLS = 2461
NROWS = 2056
DX = 7412.9951096
CELLSIZE = DX / 1000.0 / 111.1994
XLLCORNER = 128.02777778
YLLCORNER = -76.00555556
TIDAL_ANNOTATIONS = [
    (278.71, -4.57, "Tala"),
    (282.8333, -12.068883, "Call"),
    (287.8912, -17.0010, "Mata"),
]


def create_custom_cpt(work_dir: Path) -> Tuple[Path, Path]:
    """Create custom color palette tables (CPT) for visualization."""
    depth_cpt = work_dir / "depth.cpt"
    hgt_cpt = work_dir / "hgt.cpt"

    try:
        pygmt.makecpt(cmap="globe", output=str(depth_cpt))
        pygmt.makecpt(
            cmap="polar",
            series="-0.5/0.5/0.01",
            continuous=True,
            output=str(hgt_cpt),
        )

        # Append B, F, N entries to hgt CPT
        with open(hgt_cpt, "a") as f:
            f.write("B 0 0 255\nF 255 0 0\nN 255 255 255\n")

    except Exception as e:
        logger.error(f"Failed to create CPT files: {e}")
        raise

    return depth_cpt, hgt_cpt


def process_maximo_grid(work_dir: Path) -> None:
    """Process and normalize grid data for visualization."""
    grid_path = work_dir / "zfolder" / "zmax_a.grd"
    if not grid_path.exists():
        raise FileNotFoundError(f"Grid file not found: {grid_path}")

    try:
        data = np.loadtxt(grid_path)
    except Exception as e:
        logger.error(f"Failed to load grid data: {e}")
        raise

    expected_size = NCOLS * NROWS
    if data.size != expected_size:
        raise ValueError(
            f"Data size mismatch: Expected {expected_size}, got {data.size}"
        )

    try:
        arr = data.reshape((NCOLS, NROWS), order="F")
        mirrored = np.flipud(arr.T)
        max_val = np.nanmax(mirrored)
        normalized = (12.0 * mirrored) / (max_val + 1e-9)
    except Exception as e:
        logger.error(f"Data processing failed: {e}")
        raise

    output_grid = work_dir / "maximo.grd"
    try:
        with open(output_grid, "w") as f:
            f.write(
                f"ncols {NCOLS}\n"
                f"nrows {NROWS}\n"
                f"xllcorner {XLLCORNER:.8f}\n"
                f"yllcorner {YLLCORNER:.8f}\n"
                f"cellsize {CELLSIZE:.8f}\n"
                "nodata_value -9999\n"
            )
            np.savetxt(
                f, normalized, fmt="%8.2f", delimiter="", newline="\n", encoding="ascii"
            )
    except IOError as e:
        logger.error(f"Failed to write output grid: {e}")
        raise


def generate_maxola_plot(work_dir: Path) -> None:
    """Generate the final visualization plot using processed data."""
    files_to_cleanup: List[Path] = []

    try:
        pygmt.config(
            MAP_FRAME_TYPE="plain",
            FONT_ANNOT_PRIMARY="12p",
            FONT_LABEL="12p",
            FONT_TITLE="12p",
            PS_MEDIA="A4",
        )

        depth_cpt, hgt_cpt = create_custom_cpt(work_dir)
        files_to_cleanup.extend([depth_cpt, hgt_cpt])

        process_maximo_grid(work_dir)
        maximo_grid = work_dir / "maximo.grd"
        maxola_grid = work_dir / "maxola.grd"
        files_to_cleanup.extend([maximo_grid, maxola_grid])

        # Convert grid format using GMT
        try:
            subprocess.run(
                ["gmt", "grdconvert", str(maximo_grid), "-G" + str(maxola_grid)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"GMT command failed: {e.stderr.decode().strip()}")
            raise
        except FileNotFoundError:
            logger.error("GMT command not found. Ensure GMT is installed and in PATH.")
            raise

        # Initialize figure
        fig = pygmt.Figure()
        fig.shift_origin(xshift="4.2c", yshift="10.0c")

        # Add a map of the height of the tsunami waves
        fig.grdimage(grid=str(maxola_grid), cmap=hgt_cpt, projection="A210/-10/5.0i")
        fig.coast(
            shorelines="0.5p,black",
            area_thresh=1000,
            borders=["1/0.5p,black"],
            resolution="i",
            land="gray",
            frame=["WSen", "xa20f10", "ya20f10"],
        )

        # Add tidal stations to the map
        tidal_file = work_dir / "tidal.txt"
        if tidal_file.exists():
            try:
                tidal_data = np.loadtxt(tidal_file, comments="#", usecols=(0, 1))
                if tidal_data.size > 0:
                    tidal_data[:, 0] -= 1
                    fig.plot(
                        x=tidal_data[:, 0],
                        y=tidal_data[:, 1],
                        style="t0.35c",
                        pen="0.5p,black",
                        fill="blue",
                    )
            except Exception as e:
                logger.warning(f"Failed to process tidal data: {e}")

        # Add the name of the tidal stations to the map
        for lon, lat, text in TIDAL_ANNOTATIONS:
            fig.text(
                x=lon,
                y=lat,
                text=text,
                font="10p,Helvetica-Bold,black",
                justify="LT",
                offset="0.1c",
            )

        # Add the beach ball (mechanism) of the earthquake
        meca_file = work_dir / "meca.dat"
        if meca_file.exists():
            try:
                spec = read_meca_spec(meca_file)
                fig.meca(
                    spec=spec,
                    scale="0.23c",
                    compressionfill="blue",
                    convention="mt",
                )
            except Exception as e:
                logger.warning(f"Failed to add beach balls: {e}")

        # Add legend elements
        fig.text(x=210, y=-10, text="+", font="16p,Helvetica-Bold,black", justify="CM")
        fig.text(
            x=210,
            y=10,
            text="PACIFIC OCEAN",
            font="10p,Helvetica-Bold,black",
            justify="CB",
        )

        fig.psconvert(prefix=str(work_dir / "maxola"), fmt="E")

    finally:
        # Cleanup temporary files
        for file_path in files_to_cleanup:
            try:
                file_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to clean up {file_path}: {e}")
