import contextlib
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def change_dir(destination: Path):
    """
    Context manager for changing the current working directory.
    """
    prev_cwd = Path(os.getcwd())
    os.chdir(destination)
    try:
        yield
    finally:
        os.chdir(prev_cwd)


def process_tsunami_data(working_dir: Path) -> None:
    """
    Process tsunami data to calculate wave heights and timing information.

    Args:
        working_dir: Working directory for the job.
    """
    logger.info("Processing tsunami wave height and timing data...")

    # Define constants
    m = 1681  # Number of time steps

    # Station names
    station_names = [
        "cruz",
        "tala",
        "pait",
        "pime",
        "sala",
        "chim",
        "huar",
        "huac",
        "cala",
        "cerr",
        "pisc",
        "juan",
        "atic",
        "cama",
        "mata",
        "iloo",
        "aric",
    ]

    # Initialize arrays for each station
    station_data = {name: np.zeros(m) for name in station_names}

    with change_dir(working_dir):
        # Read the input file
        logger.info("Reading green.dat...")
        try:
            data = np.loadtxt("./zfolder/green.dat")
        except Exception as e:
            logger.error(f"Error reading green.dat: {e}")
            raise FileNotFoundError(f"Failed to read green.dat: {e}") from e

        # Extract data columns
        tiem = data[:, 0]
        for i, name in enumerate(station_names):
            station_data[name] = data[:, i + 1]

        # Apply scaling factors ("Relacion de Green")
        scaling_factors = {
            "cruz": (12.9 / 14.0) ** (0.25),
            "tala": (183.1 / 20.0) ** (0.25),
            "pait": (50.0 / 210.0) ** (0.25),
            "pime": (26.2 / 54.0) ** (0.25),
            "sala": (247.1 / 24.0) ** (0.25),
            "chim": (51.7 / 28.0) ** (0.25),
            "huar": (69.7 / 14.0) ** (0.25),
            "huac": (148.9 / 12.0) ** (0.25),
            "cala": (76.0 / 16.0) ** (0.25),
            "cerr": (125.4 / 12.0) ** (0.25),
            "pisc": (25.0 / 36.0) ** (0.25),
            "juan": (222.2 / 8.0) ** (0.25),
            "atic": (163.5 / 84.0) ** (0.25),
            "cama": (46.1 / 350.0) ** (0.25),
            "mata": (313.4 / 112.0) ** (0.25),
            "iloo": (455.9 / 26.0) ** (0.25),
            "aric": (48.0 / 10.0) ** (0.25),
        }

        for name, factor in scaling_factors.items():
            station_data[name] = factor * station_data[name]

        # Write to green_rev.dat using scientific notation format
        logger.info("Writing green_rev.dat...")
        try:
            with open("./zfolder/green_rev.dat", "w") as f:
                for k in range(m):
                    time_val = tiem[k] / 60.0
                    tala_val = station_data["tala"][k]
                    cala_val = station_data["cala"][k]
                    mata_val = station_data["mata"][k]
                    f.write(
                        f"{time_val:12.6f} {fortran_float_format(tala_val)} {fortran_float_format(cala_val)} {fortran_float_format(mata_val)}\n"  # noqa: E501
                    )
        except Exception as e:
            logger.error(f"Error writing green_rev.dat: {e}")
            raise IOError(f"Failed to write green_rev.dat: {e}") from e

        # Find first non-zero readings and maximum values
        first_nonzero = {}
        max_values = {}
        for name in station_names:
            nonzero_indices = np.where(station_data[name] > 0.0)[0]
            first_nonzero[name] = (
                nonzero_indices[0] + 1 if nonzero_indices.size > 0 else 0
            )
            max_values[name] = np.max(station_data[name])

        # Write to ttt_max.dat
        logger.info("Writing ttt_max.dat...")
        try:
            with open("ttt_max.dat", "w") as f:
                for name in station_names:
                    index_val = float(first_nonzero[name])
                    max_val = max_values[name]
                    f.write(f"{index_val:6.1f}{max_val:6.2f}\n")
        except Exception as e:
            logger.error(f"Error writing ttt_max.dat: {e}")
            raise IOError(f"Failed to write ttt_max.dat: {e}") from e

        # Find the overall maximum value
        maxmax = max(max_values.values())
        logger.info(f"Maximum wave height: {maxmax}")

        # Run appropriate plotting function based on maximum value
        if maxmax <= 0.1:
            plot_mareograma(scale=0.1, tick_type="small")
        elif maxmax <= 0.2:
            plot_mareograma(scale=0.2, tick_type="small")
        elif maxmax <= 0.6:
            plot_mareograma(scale=0.6, tick_type="medium")
        elif maxmax <= 1.0:
            plot_mareograma(scale=1.0, tick_type="medium")
        elif maxmax <= 2.0:
            plot_mareograma(scale=2.0, tick_type="medium")
        elif maxmax <= 3.0:
            plot_mareograma(scale=3.0, tick_type="large")
        elif maxmax <= 4.0:
            plot_mareograma(scale=4.0, tick_type="large")
        else:
            plot_mareograma(scale=5.0, tick_type="large")

        logger.info("Successfully created ttt_max.dat")


def fortran_float_format(value: float) -> str:
    """
    Format a floating point number to match Fortran's scientific notation style.
    For small values near zero, returns a formatted zero.

    Args:
        value: The floating point number to format.

    Returns:
        A string with Fortran-style formatted value.
    """
    if abs(value) < 1e-12:
        return "  0.0000000E+00"
    formatted = f"{value:17.7E}"
    return formatted.replace("e", "E")


def plot_mareograma(scale: float, tick_type: str) -> None:
    """
    Generate a mareograma plot using GMT commands.
    Replaces: mareograma.csh, mareograma2.csh, mareograma3.csh

    Args:
        scale: Y-axis scale value.
        tick_type: Tick interval style ("small", "medium", or "large").
    """
    logger.info(f"Plotting mareograma with scale={scale}, tick_type={tick_type}")
    datafile = "./zfolder/green_rev.dat"
    size = "15.0c/3.0c"
    psfile = "mareograma.ps"
    dy = "4.2c"
    tdur = 28  # Time duration in hours

    # Determine tick interval
    if tick_type == "small":
        y_tick = f"a{scale}g.05"  # mareograma1.csh (0.05 intervals)
    elif tick_type == "medium":
        y_tick = f"a{scale}g.2"  # mareograma.csh (0.2 intervals)
    else:  # large
        y_tick = f"a{scale}g1."  # mareograma2.csh (1.0 intervals)

    # Initialize GMT settings
    gmt_init_commands = [
        "gmt set MAP_FRAME_TYPE=plain",
        "gmt set FONT_ANNOT_PRIMARY 9",
        "gmt set FONT_LABEL 9",
        "gmt set FONT_TITLE 9",
        "gmt set PS_MEDIA A4",
    ]
    for cmd in gmt_init_commands:
        try:
            subprocess.run(cmd, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.warning(f"GMT initialization command failed: {e}")

    temp_files = []
    try:
        # Plot Talara
        station = "Talara"
        region = f"0/{tdur}/-{scale}/{scale}"
        axis = f'a2g1:"":/a{y_tick}:"":SW'
        cmd = (
            f"gmt psbasemap -JX{size} -R{region} -B{axis} "
            f"-P -K -X3.0c -Y24.0c > {psfile}"
        )
        subprocess.run(cmd, shell=True, check=True)

        cmd = (
            f"awk '{{ print $1,$2 }}' {datafile} | "
            f"gmt psxy -W.5,blue -JX{size} -R{region} "
            f"-K -O -P >> {psfile}"
        )
        subprocess.run(cmd, shell=True, check=True)

        # Add Talara label
        with tempfile.NamedTemporaryFile(delete=False, mode="w") as talara_text:
            talara_text.write(f"0.2 4.0 11 0 0 LT {station}\n")
            talara_filename = talara_text.name
        temp_files.append(talara_filename)
        cmd = f"gmt pstext -JX{size} -R0/10/0/4 -K -O < {talara_filename} >> {psfile}"
        subprocess.run(cmd, shell=True, check=True)

        # Plot Callao
        station = "Callao"
        region = f"0/{tdur}/-{scale}/{scale}"
        axis = f'a2g1:"":/a{y_tick}:"H\\40(m)":SW'
        cmd = (
            f"gmt psbasemap -JX{size} -R{region} -B{axis} "
            f"-P -K -X0 -Y-{dy} -O >> {psfile}"
        )
        subprocess.run(cmd, shell=True, check=True)

        cmd = (
            f"awk '{{ print $1,$3 }}' {datafile} | "
            f"gmt psxy -W.5,blue -JX{size} -R{region} "
            f"-K -O -P >> {psfile}"
        )
        subprocess.run(cmd, shell=True, check=True)

        with tempfile.NamedTemporaryFile(delete=False, mode="w") as callao_text:
            callao_text.write(f"0.2 4.0 11 0 0 LT {station}\n")
            callao_filename = callao_text.name
        temp_files.append(callao_filename)
        cmd = (
            f"gmt pstext -JX{size} -R0/10/0/4 -K -O -V < {callao_filename} >> {psfile}"
        )
        subprocess.run(cmd, shell=True, check=True)

        # Plot Matarani
        station = "Matarani"
        region = f"0/{tdur}/-{scale}/{scale}"
        axis = f'a2g1:"Time\\40(h)":/a{y_tick}:"":SW'
        cmd = (
            f"gmt psbasemap -JX{size} -R{region} -B{axis} "
            f"-P -K -X0 -Y-{dy} -O >> {psfile}"
        )
        subprocess.run(cmd, shell=True, check=True)

        cmd = (
            f"awk '{{ print $1,$4 }}' {datafile} | "
            f"gmt psxy -W.5,blue -JX{size} -R{region} "
            f"-K -O -P >> {psfile}"
        )
        subprocess.run(cmd, shell=True, check=True)

        with tempfile.NamedTemporaryFile(delete=False, mode="w") as matarani_text:
            matarani_text.write(f"0.2 4.0 11 0 0 LT {station}\n")
            matarani_filename = matarani_text.name
        temp_files.append(matarani_filename)
        cmd = (
            f"gmt pstext -JX{size} -R0/10/0/4 -K -O -V < "
            f"{matarani_filename} >> {psfile}"
        )
        subprocess.run(cmd, shell=True, check=True)

        # Convert PS to EPS and cleanup
        subprocess.run(f"ps2eps {psfile} -f", shell=True, check=True)
        subprocess.run(f"rm {psfile}", shell=True, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error during mareograma plotting: {e}")
        raise RuntimeError(f"Failed to plot mareograma: {e}") from e
    finally:
        # Clean up temporary files
        for file in temp_files:
            try:
                os.unlink(file)
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {file}: {e}")
