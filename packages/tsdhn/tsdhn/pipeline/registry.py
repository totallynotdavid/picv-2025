from tsdhn.deform import run_deform
from tsdhn.fault_plane import run_fault_plane
from tsdhn.pipeline.types import ProcessingStep
from tsdhn.render.copy import copy_ttt_pdf
from tsdhn.render.maxola import generate_maxola_plot
from tsdhn.render.point_ttt import generate_ttt_map
from tsdhn.render.ttt_inverso import ttt_inverso_python
from tsdhn.render.ttt_max import process_tsunami_data
from tsdhn.tsunami import run_tsunami

__all__ = [
    "DEFAULT_PIPELINE",
    "PROCESSING_PIPELINE",
    "TTT_MUNDO_PIPELINE",
]


PROCESSING_PIPELINE: tuple[ProcessingStep, ...] = (
    ProcessingStep(
        name="fault_plane",
        outputs=("pfalla.inp", "xyo.dat", "meca.dat"),
        runner=run_fault_plane,
    ),
    ProcessingStep(
        name="deform",
        outputs=("deform_a.grd",),
        runner=run_deform,
    ),
    ProcessingStep(
        name="tsunami",
        outputs=("zfolder/green.dat", "zfolder/zmax_a.grd"),
        runner=run_tsunami,
    ),
    ProcessingStep(
        name="maxola",
        outputs=("maxola.pdf",),
        runner=generate_maxola_plot,
        required_system_executables=("gmt",),
    ),
    ProcessingStep(
        name="ttt_max",
        outputs=("zfolder/green_rev.dat", "ttt_max.dat", "mareograma.svg"),
        runner=process_tsunami_data,
    ),
)

TTT_MUNDO_PIPELINE: tuple[ProcessingStep, ...] = (
    ProcessingStep(
        name="ttt_inverso",
        outputs=("ttt.b",),
        runner=ttt_inverso_python,
        required_system_executables=("gmt", "ttt_client"),
        working_dir="ttt_mundo",
    ),
    ProcessingStep(
        name="point_ttt",
        outputs=("ttt.pdf",),
        runner=generate_ttt_map,
        required_system_executables=("gmt",),
        working_dir="ttt_mundo",
    ),
    ProcessingStep(
        name="copy_ttt_pdf",
        outputs=("../ttt.pdf",),
        runner=copy_ttt_pdf,
        working_dir="ttt_mundo",
    ),
)

DEFAULT_PIPELINE: tuple[ProcessingStep, ...] = PROCESSING_PIPELINE + TTT_MUNDO_PIPELINE
