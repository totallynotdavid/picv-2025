import logging
import subprocess
from pathlib import Path

import pygmt
from pygmt.clib import Session

from tsdhn.external import resolve
from tsdhn.render.meca import read_meca_spec

logger = logging.getLogger(__name__)


def format_ttt_epicenter(longitude: float, latitude: float) -> str:
    # ttt_client expects fixed-width latitude text with width based on sign/magnitude.
    if latitude <= -10.0:
        latitude_format = "{:6.2f}"
    elif latitude < 0.0:
        latitude_format = "{:5.2f}"
    elif latitude < 10.0:
        latitude_format = "{:4.2f}"
    else:
        latitude_format = "{:5.2f}"

    return f"{longitude:6.2f}/{latitude_format.format(latitude)}"


def ttt_inverso_python(working_dir: Path) -> None:
    """Run ttt_client and grdmath from meca.dat epicenter coordinates."""
    meca_path = working_dir.parent / "meca.dat"
    if not meca_path.exists():
        raise FileNotFoundError(f"Required file {meca_path} not found.")

    meca_spec = read_meca_spec(meca_path)
    loc = format_ttt_epicenter(meca_spec["longitude"], meca_spec["latitude"])
    logger.info("Formatted location: %s", loc)

    try:
        # `loc` is a formatted float pair, not user input.
        subprocess.run(
            [
                str(resolve("ttt_client")),
                "cortado.i2",
                f"-E{loc}",
                "-Tttt.b",
                "-VL",
            ],
            cwd=working_dir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        logger.info("ttt_client executed successfully.")
    except subprocess.CalledProcessError as e:
        logger.exception("ttt_client execution failed: %s", e)
        raise

    # PyGMT does not expose grdmath. The no-op rewrite makes the ttt_client
    # grid header readable by the later GMT contour step.
    grid_arg = f"{working_dir / 'ttt.b'}=bf"
    try:
        with Session() as session:
            session.call_module("grdmath", [grid_arg, "1.0", "MUL", "=", grid_arg])
        logger.info("grdmath executed successfully.")
    except pygmt.exceptions.GMTError as e:
        logger.exception("grdmath execution failed: %s", e)
        raise
