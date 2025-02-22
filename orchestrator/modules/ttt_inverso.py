import subprocess
from pathlib import Path


def ttt_inverso_python(working_dir: Path) -> None:
    """
    Reads coordinates from meca.dat, formats them, and executes ttt_client
    and grdmath commands.
    """
    meca_path = working_dir.parent / "meca.dat"
    with open(meca_path, "r") as f:
        parts = f.readline().strip().split()
        if len(parts) < 2:
            raise ValueError(
                f"Invalid meca.dat format: not enough values in {meca_path}"
            )
        xep = float(parts[0])
        yep = float(parts[1])

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
    x_str = x_fmt.format(xep)
    y_str = y_fmt.format(yep)
    loc = f"{x_str}/{y_str}"

    # Execute ttt_client with constructed location string
    subprocess.run(
        ["ttt_client", "cortado.i2", f"-E{loc}", "-Tttt.b", "-VL"],
        cwd=working_dir,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Process output grid with grdmath
    subprocess.run(
        ["gmt", "grdmath", "ttt.b=bf", "1.0", "MUL", "=", "ttt.b=bf"],
        cwd=working_dir,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
