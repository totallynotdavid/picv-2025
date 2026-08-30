import logging
from pathlib import Path

import pygmt

from tsdhn.render.meca import read_meca_spec

logger = logging.getLogger(__name__)


def generate_ttt_map(working_dir: Path) -> None:
    """Generate the TTT map from legacy model outputs in the job workspace."""
    region = [120.0, 300.0, -65.0, 61.0]
    projection = "M16c"
    frame_parameters = ["WsNe", "xa20f10", "ya20f10"]

    # These suffixes tell GMT how to decode the legacy binary grids.
    grd_filename = "cortado.i2"
    grd_params = "=bs"
    tttb_filename = "ttt.b"
    tttb_params = "=bf"

    grd_file = working_dir / grd_filename
    tttb_file = working_dir / tttb_filename
    meca_file = working_dir.parent / "meca.dat"
    output_file = working_dir / "ttt.pdf"

    try:
        for file in (grd_file, tttb_file, meca_file):
            if not file.exists():
                raise FileNotFoundError(f"Required file {file} not found.")

        pygmt.config(
            MAP_FRAME_TYPE="plain",
            FONT_ANNOT_PRIMARY="9p",
            FONT_LABEL="9p",
            FONT_TITLE="9p",
            PS_MEDIA="A4",
        )

        fig = pygmt.Figure()

        color_cpt = working_dir / "color.cpt"
        pygmt.makecpt(cmap="globe", output=str(color_cpt), continuous=True)

        fig.grdimage(
            grid=f"{grd_file}{grd_params}",
            region=region,
            projection=projection,
            cmap=str(color_cpt),
        )

        fig.coast(
            region=region,
            projection=projection,
            frame=frame_parameters,
            resolution="l",
            borders=["1/0.5p,30"],
            shorelines="0.5,30",
        )

        # The legacy map labels travel-time isolines in hours.
        fig.grdcontour(
            grid=f"{tttb_file}{tttb_params}",
            region=region,
            projection=projection,
            levels=1,
            annotation="1.f1+uh",
            pen=["c1.,30,-", "a1.,30,-"],
        )

        spec = read_meca_spec(meca_file)
        logger.info("Parsed meca spec: %s", spec)

        fig.meca(
            spec=spec,
            region=region,
            projection=projection,
            scale="0.29c",
            compressionfill="black",
            convention="mt",
        )

        fig.savefig(str(output_file))

        if not output_file.exists():
            raise RuntimeError("Failed to generate TTT PDF file.")

        logger.info("TTT map generated successfully.")

    except Exception as e:
        if output_file.exists():
            output_file.unlink()
        logger.exception("TTT map generation failed: %s", e)
        raise RuntimeError(f"TTT map generation failed: {e}") from e
