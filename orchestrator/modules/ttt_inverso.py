import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def ttt_inverso_python(working_dir: Path) -> None:
    """
    Read coordinates from meca.dat, format them, and execute:
    - ttt_client
    - grdmath (not yet implemented in pygmt)

    Args:
        working_dir: The working directory for the ttt_inverso process.
    """
    meca_path = working_dir.parent / "meca.dat"
    if not meca_path.exists():
        raise FileNotFoundError(f"Required file {meca_path} not found.")

    with open(meca_path, "r") as f:
        parts = f.readline().strip().split()
        if len(parts) < 2:
            raise ValueError(
                f"Invalid meca.dat format: not enough values in {meca_path}"
            )
        try:
            xep = float(parts[0])
            yep = float(parts[1])
        except ValueError as e:
            raise ValueError(f"Invalid coordinate values in {meca_path}: {e}") from e

    # Determine formatting based on yep's value
    if yep <= -10.0:
        x_fmt, y_fmt = "{:6.2f}", "{:6.2f}"
    elif yep < 0.0:
        x_fmt, y_fmt = "{:6.2f}", "{:5.2f}"
    elif yep < 10.0:
        x_fmt, y_fmt = "{:6.2f}", "{:4.2f}"
    else:  # yep >= 10.0
        x_fmt, y_fmt = "{:6.2f}", "{:5.2f}"

    # Format coordinates
    loc = f"{x_fmt.format(xep)}/{y_fmt.format(yep)}"
    logger.info(f"Formatted location: {loc}")

    # Execute ttt_client command
    try:
        subprocess.run(
            ["ttt_client", "cortado.i2", f"-E{loc}", "-Tttt.b", "-VL"],
            cwd=working_dir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        logger.info("ttt_client executed successfully.")
    except subprocess.CalledProcessError as e:
        logger.exception(f"ttt_client execution failed: {e}")
        raise

    # Process output grid with grdmath
    try:
        subprocess.run(
            ["gmt", "grdmath", "ttt.b=bf", "1.0", "MUL", "=", "ttt.b=bf"],
            cwd=working_dir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        logger.info("grdmath executed successfully.")
    except subprocess.CalledProcessError as e:
        logger.exception(f"grdmath execution failed: {e}")
        raise
