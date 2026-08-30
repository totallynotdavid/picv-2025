import os
import shutil
import subprocess
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

__all__ = [
    "REQUIRED_MODEL_DIRS",
    "REQUIRED_MODEL_FILES",
    "SYSTEM_EXECUTABLES",
    "CapabilityStatus",
    "RuntimeContext",
    "check_capabilities",
    "resolve_model_dir",
    "validate_model_dir",
]

REQUIRED_MODEL_DIRS: tuple[str, ...] = ("bathy", "ttt_mundo")
REQUIRED_MODEL_FILES: tuple[str, ...] = (
    "pacifico.mat",
    "maper1.mat",
    "mecfoc.dat",
    "puertos.txt",
    "tidal.dat",
    "bathy/grid_a.grd",
    "bathy/xa.dat",
    "bathy/ya.dat",
    "ttt_mundo/cortado.i2",
)

# The external scientific tools the pipeline shells out to, all resolved
# from PATH. There is no longer a TSDHN_TOOLS_DIR of prebuilt Fortran
# binaries: every DEFAULT_PIPELINE step is a Python function, and the
# ifx-compiled fault_plane/deform/tsunami executables are needed only by
# the tsdhn-parity suite, which resolves them itself.
SYSTEM_EXECUTABLES: tuple[str, ...] = ("gmt", "ttt_client")


@dataclass(frozen=True)
class CapabilityStatus:
    name: str
    available: bool
    version: str | None = None
    path: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class RuntimeContext:
    model_dir: Path
    model_version: str
    capabilities: dict[str, CapabilityStatus]

    @classmethod
    def resolve(
        cls,
        model_dir: Path | None = None,
        *,
        model_version: str | None = None,
    ) -> RuntimeContext:
        resolved_model_dir, resolved_model_version = resolve_model_dir(
            model_dir=model_dir,
            model_version=model_version,
        )
        return cls(
            model_dir=resolved_model_dir,
            model_version=resolved_model_version,
            capabilities=check_capabilities(),
        )


def resolve_model_dir(
    *,
    model_dir: Path | None = None,
    model_version: str | None = None,
) -> tuple[Path, str]:
    resolved_version = model_version or version("tsdhn")
    if model_dir is not None:
        return validate_model_dir(model_dir.resolve()), resolved_version
    if value := os.environ.get("TSDHN_MODEL_DIR"):
        return validate_model_dir(Path(value).resolve()), resolved_version

    from tsdhn.assets import ModelStore

    dataset = ModelStore().resolve_installed(resolved_version)
    if dataset is not None:
        return dataset.path, dataset.version

    raise RuntimeError(
        "TSDHN model assets are not installed. "
        f"Run: tsdhn assets install --model-version {resolved_version}"
    )


def validate_model_dir(path: Path) -> Path:
    missing_dirs = [
        dirname for dirname in REQUIRED_MODEL_DIRS if not (path / dirname).is_dir()
    ]
    missing_files = [
        filename for filename in REQUIRED_MODEL_FILES if not (path / filename).is_file()
    ]
    if missing_dirs or missing_files:
        missing = [f"{dirname}/" for dirname in missing_dirs] + missing_files
        raise RuntimeError(
            f"Invalid TSDHN model directory '{path}'. Missing: {', '.join(missing)}"
        )
    return path


def check_capabilities(
    *,
    executables: tuple[str, ...] = SYSTEM_EXECUTABLES,
) -> dict[str, CapabilityStatus]:
    return {name: _check_executable(name) for name in executables}


def _check_executable(name: str) -> CapabilityStatus:
    path = shutil.which(name)
    if path is None:
        return CapabilityStatus(
            name=name,
            available=False,
            detail=f"{name} was not found on PATH",
        )
    version_text = _read_tool_version(name)
    return CapabilityStatus(
        name=name,
        available=True,
        version=version_text,
        path=path,
    )


def _read_tool_version(name: str) -> str | None:
    commands = {
        "gmt": [name, "--version"],
        "ttt_client": [name],
    }
    command = commands.get(name, [name, "--version"])
    try:
        result = subprocess.run(  # noqa: S603
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else None
