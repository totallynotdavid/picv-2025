import logging
from pathlib import Path

import pygmt

logger = logging.getLogger(__name__)


def generate_ttt_map() -> None:
    """
    Generate a TTT map using GMT via pygmt.
    Validates input files, configures GMT settings, creates the plot,
    and saves it as an EPS file.
    """
    region = [120.0, 300.0, -65.0, 61.0]  # WEST, EAST, SOUTH, NORTH
    projection = "M16c"
    axis = "a20f10WsNe"
    grd_file = "cortado.i2=bs"
    tttb_file = "ttt.b=bf"
    cmt_file = "../meca.dat"
    output_file = "ttt.eps"

    try:
        # Validate input files
        required_files = [
            Path(grd_file.split("=")[0]),
            Path(tttb_file.split("=")[0]),
            Path(cmt_file),
        ]
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
        pygmt.makecpt(cmap="globe", output="color.cpt", continuous=True)

        # Plot grid image
        fig.grdimage(
            grid=grd_file,
            region=region,
            projection=projection,
            cmap="color.cpt",
        )

        # Add coastlines
        fig.coast(
            region=region,
            projection=projection,
            frame=axis,
            resolution="l",
            borders=["1/0.5p,30"],  # N1
            shorelines="0.5,30",
            land="gray",
            water="white",
        )

        # Add contour lines
        fig.grdcontour(
            grid=tttb_file,
            region=region,
            projection=projection,
            levels=1,
            annotation="1+f1+uh",
            pen=["c1.0,30,-", "a1.0,30,-"],
        )

        # Add focal mechanisms
        fig.meca(
            spec=cmt_file,
            region=region,
            projection=projection,
            scale="a0.29c",
            color="0/0/0",
        )

        # Save output as EPS
        fig.save(output_file)

        # Verify output creation
        if not Path(output_file).exists():
            raise RuntimeError("Failed to generate TTT EPS file.")

        logger.info("TTT map generated successfully.")

    except Exception as e:
        # Cleanup on failure if output file exists
        if Path(output_file).exists():
            Path(output_file).unlink()
        logger.exception(f"TTT map generation failed: {e}")
        raise RuntimeError(f"TTT map generation failed: {e}") from e
