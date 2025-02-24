import logging
from pathlib import Path

import pygmt

logger = logging.getLogger(__name__)


def generate_ttt_map(working_dir: Path) -> None:
    """
    Generate a TTT map using GMT via pygmt.
    Validates input files, configures GMT settings, creates the plot,
    and saves it as an EPS file.
    """
    region = [120.0, 300.0, -65.0, 61.0]
    projection = "M16c"
    frame_parameters = ["WsNe", "xa20f10", "ya20f10"]

    # GMT parameters
    grd_filename = "cortado.i2"
    grd_params = "=bs"
    tttb_filename = "ttt.b"
    tttb_params = "=bf"

    # Path definitions
    grd_file = working_dir / grd_filename
    tttb_file = working_dir / tttb_filename
    cmt_file = working_dir.parent / "meca.dat"
    output_file = working_dir / "ttt.eps"

    try:
        # Validate input files
        required_files = [grd_file, tttb_file, cmt_file]
        for file in required_files:
            if not file.exists():
                raise FileNotFoundError(f"Required file {file} not found.")

        # Configure GMT settings
        pygmt.config(
            MAP_FRAME_TYPE="plain",
            FONT_ANNOT_PRIMARY="9p",
            FONT_LABEL="9p",
            FONT_TITLE="9p",
            PS_MEDIA="A4",
        )

        fig = pygmt.Figure()

        # Create color palette
        pygmt.makecpt(
            cmap="globe", output=str(working_dir / "color.cpt"), continuous=True
        )

        # Plot grid image
        fig.grdimage(
            grid=f"{grd_file}{grd_params}",
            region=region,
            projection=projection,
            cmap=str(working_dir / "color.cpt"),
        )

        # Add coastlines
        fig.coast(
            region=region,
            projection=projection,
            frame=frame_parameters,
            resolution="l",
            borders=["1/0.5p,30"],  # N1
            shorelines="0.5,30",
        )

        # Add contour lines
        fig.grdcontour(
            grid=f"{tttb_file}{tttb_params}",
            region=region,
            projection=projection,
            levels=1,
            annotation="1.f1+uh",
            pen=["c1.,30,-", "a1.,30,-"],
        )

        # Add focal mechanisms
        fig.meca(
            cmt_file,
            region=region,
            projection=projection,
            scale="0.29c",
            compressionfill="black",
            convention="mt",
        )

        # Save output as EPS
        fig.savefig(str(output_file))

        # Verify output creation
        if not output_file.exists():
            raise RuntimeError("Failed to generate TTT EPS file.")

        logger.info("TTT map generated successfully.")

    except Exception as e:
        # Cleanup on failure if output file exists
        if output_file.exists():
            output_file.unlink()
        logger.exception(f"TTT map generation failed: {e}")
        raise RuntimeError(f"TTT map generation failed: {e}") from e
