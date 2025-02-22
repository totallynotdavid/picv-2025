import shutil


def check_dependencies():
    required = ["gfortran", "pdflatex", "csh"]
    missing = [cmd for cmd in required if not shutil.which(cmd)]
    if missing:
        raise RuntimeError(f"Missing required commands: {', '.join(missing)}")
