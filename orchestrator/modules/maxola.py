import subprocess
from pathlib import Path
from typing import Tuple

import numpy as np
import pygmt

from orchestrator.modules.point_ttt import read_meca_spec


def create_custom_cpt(work_dir: Path) -> Tuple[Path, Path]:
    depth_cpt = work_dir / "depth.cpt"
    hgt_cpt = work_dir / "hgt.cpt"

    pygmt.makecpt(cmap="globe", output=str(depth_cpt))
    pygmt.makecpt(
        cmap="polar",
        series="-0.5/0.5/0.01",
        continuous=True,
        output=str(hgt_cpt),
    )

    # Append B, F, N entries to match original .csh script
    with open(hgt_cpt, "a") as f:
        f.write("B 0 0 255\n")
        f.write("F 255 0 0\n")
        f.write("N 255 255 255\n")

    return depth_cpt, hgt_cpt


def process_maximo_grid(work_dir: Path) -> None:
    grid_path = work_dir / "zfolder" / "zmax_a.grd"
    data = np.loadtxt(grid_path)
    ia, ja = 2461, 2056

    arr = data.reshape((ia, ja), order="F")
    mirrored = np.flipud(arr.T)

    max_val = np.nanmax(mirrored)
    normalized = (12.0 * mirrored) / (max_val + 1e-9)

    # Calculate values
    DX = 7412.9951096
    cellsize = DX / 1000.0 / 111.1994
    xllcorner = 128.02777778
    yllcorner = -76.00555556

    output_grid = work_dir / "maximo.grd"
    with open(output_grid, "w") as f:
        f.write(f"ncols {ia}\n")
        f.write(f"nrows {ja}\n")
        f.write("xllcorner {:.8f}\n".format(xllcorner))
        f.write("yllcorner {:.8f}\n".format(yllcorner))
        f.write("cellsize {:.8f}\n".format(cellsize))
        f.write("nodata_value -9999\n")

        # Fortran-style fixed-width formatting
        np.savetxt(
            f, normalized, fmt="%8.2f", delimiter="", newline="\n", encoding="ascii"
        )


def generate_maxola_plot(work_dir: Path) -> None:
    pygmt.config(
        MAP_FRAME_TYPE="plain",
        FONT_ANNOT_PRIMARY="12p",
        FONT_LABEL="12p",
        FONT_TITLE="12p",
        PS_MEDIA="A4",
    )

    depth_cpt, hgt_cpt = create_custom_cpt(work_dir)
    process_maximo_grid(work_dir)

    # grdadjust is not available in pygmt
    subprocess.run(
        [
            "gmt",
            "grdconvert",
            str(work_dir / "maximo.grd"),
            "-G" + str(work_dir / "maxola.grd"),
        ],
        check=True,
    )

    fig = pygmt.Figure()
    fig.shift_origin(xshift="4.2c", yshift="10.0c")

    # Add a map of the height of the tsunami waves
    # We pass the cmap which adds the red color to the highest values
    fig.grdimage(
        grid=str(work_dir / "maxola.grd"), cmap=hgt_cpt, projection="A210/-10/5.0i"
    )

    # Add the coastlines and borders
    fig.coast(
        shorelines="0.5p,black",
        area_thresh=1000,
        borders=["1/0.5p,black"],
        resolution="i",
        land="gray",
        frame=["WSen", "xa20f10", "ya20f10"],  # Adds frame to the map
    )

    # Add the stations
    tidal_data = np.loadtxt(work_dir / "tidal.txt", comments="#", usecols=(0, 1))
    if tidal_data.size > 0:
        tidal_data[:, 0] -= 1
        fig.plot(
            x=tidal_data[:, 0],
            y=tidal_data[:, 1],
            style="t0.35c",
            pen="0.5p,black",
            fill="blue",
        )

    # Add the name of the stations
    annotations = [
        (278.71, -4.57, "Tala"),
        (282.8333, -12.068883, "Call"),
        (287.8912, -17.0010, "Mata"),
    ]
    for lon, lat, text in annotations:
        fig.text(
            x=lon,
            y=lat,
            text=text,
            font="10p,Helvetica-Bold,black",
            justify="LT",
            offset="0.1c",
        )

    # Add the beach balls
    spec = read_meca_spec(work_dir / "meca.dat")
    fig.meca(
        spec=spec,
        scale="0.23c",
        compressionfill="blue",
        convention="mt",
    )

    # Add legend: 'Pacific Ocean' and '+' sign at the center
    fig.text(x=210, y=-10, text="+", font="16p,Helvetica-Bold,black", justify="CM")
    fig.text(
        x=210, y=10, text="PACIFIC OCEAN", font="10p,Helvetica-Bold,black", justify="CB"
    )

    fig.psconvert(prefix=str(work_dir / "maxola"), fmt="E")

    # Cleanup
    for f in [work_dir / "maximo.grd", work_dir / "maxola.grd", hgt_cpt, depth_cpt]:
        f.unlink(missing_ok=True)
