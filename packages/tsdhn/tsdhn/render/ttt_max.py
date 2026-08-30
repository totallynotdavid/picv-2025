import contextlib
import logging
import os
from collections.abc import Iterator
from html import escape
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def change_dir(destination: Path) -> Iterator[None]:
    prev_cwd = Path(os.getcwd())
    os.chdir(destination)
    try:
        yield
    finally:
        os.chdir(prev_cwd)


def process_tsunami_data(working_dir: Path) -> None:
    """Generate wave-height summary files and the mareogram plot."""
    logger.info("Processing tsunami wave height and timing data...")

    m = 1681

    station_names = [
        "cruz",
        "tala",
        "pait",
        "pime",
        "sala",
        "chim",
        "huar",
        "huac",
        "cala",
        "cerr",
        "pisc",
        "juan",
        "atic",
        "cama",
        "mata",
        "iloo",
        "aric",
    ]

    station_data = {name: np.zeros(m) for name in station_names}

    with change_dir(working_dir):
        logger.info("Reading green.dat...")
        try:
            data = np.loadtxt("./zfolder/green.dat")
        except Exception as e:
            logger.error(f"Error reading green.dat: {e}")
            raise FileNotFoundError(f"Failed to read green.dat: {e}") from e

        tiem = data[:, 0]
        for i, name in enumerate(station_names):
            station_data[name] = data[:, i + 1]

        # Adjust synthetic amplitudes for each station's depth.
        scaling_factors = {
            "cruz": (12.9 / 14.0) ** (0.25),
            "tala": (183.1 / 20.0) ** (0.25),
            "pait": (50.0 / 210.0) ** (0.25),
            "pime": (26.2 / 54.0) ** (0.25),
            "sala": (247.1 / 24.0) ** (0.25),
            "chim": (51.7 / 28.0) ** (0.25),
            "huar": (69.7 / 14.0) ** (0.25),
            "huac": (148.9 / 12.0) ** (0.25),
            "cala": (76.0 / 16.0) ** (0.25),
            "cerr": (125.4 / 12.0) ** (0.25),
            "pisc": (25.0 / 36.0) ** (0.25),
            "juan": (222.2 / 8.0) ** (0.25),
            "atic": (163.5 / 84.0) ** (0.25),
            "cama": (46.1 / 350.0) ** (0.25),
            "mata": (313.4 / 112.0) ** (0.25),
            "iloo": (455.9 / 26.0) ** (0.25),
            "aric": (48.0 / 10.0) ** (0.25),
        }

        for name, factor in scaling_factors.items():
            station_data[name] = factor * station_data[name]

        logger.info("Writing green_rev.dat...")
        try:
            with open("./zfolder/green_rev.dat", "w") as f:
                for k in range(m):
                    time_val = tiem[k] / 60.0
                    tala_val = station_data["tala"][k]
                    cala_val = station_data["cala"][k]
                    mata_val = station_data["mata"][k]
                    f.write(
                        f"{time_val:12.6f} {fortran_float_format(tala_val)} {fortran_float_format(cala_val)} {fortran_float_format(mata_val)}\n"  # noqa: E501
                    )
        except Exception as e:
            logger.error(f"Error writing green_rev.dat: {e}")
            raise OSError(f"Failed to write green_rev.dat: {e}") from e

        # The report needs the first positive sample and peak amplitude.
        first_nonzero = {}
        max_values = {}
        for name in station_names:
            nonzero_indices = np.where(station_data[name] > 0.0)[0]
            first_nonzero[name] = (
                nonzero_indices[0] + 1 if nonzero_indices.size > 0 else 0
            )
            max_values[name] = np.max(station_data[name])

        logger.info("Writing ttt_max.dat...")
        try:
            with open("ttt_max.dat", "w") as f:
                for name in station_names:
                    index_val = float(first_nonzero[name])
                    max_val = max_values[name]
                    f.write(f"{index_val:6.1f}{max_val:6.2f}\n")
        except Exception as e:
            logger.error(f"Error writing ttt_max.dat: {e}")
            raise OSError(f"Failed to write ttt_max.dat: {e}") from e

        maxmax = max(max_values.values())
        logger.info(f"Maximum wave height: {maxmax}")

        # Choose a scale that contains the largest wave.
        if maxmax <= 0.1:
            plot_mareograma(scale=0.1, tick_type="small")
        elif maxmax <= 0.2:
            plot_mareograma(scale=0.2, tick_type="small")
        elif maxmax <= 0.6:
            plot_mareograma(scale=0.6, tick_type="medium")
        elif maxmax <= 1.0:
            plot_mareograma(scale=1.0, tick_type="medium")
        elif maxmax <= 2.0:
            plot_mareograma(scale=2.0, tick_type="medium")
        elif maxmax <= 3.0:
            plot_mareograma(scale=3.0, tick_type="large")
        elif maxmax <= 4.0:
            plot_mareograma(scale=4.0, tick_type="large")
        else:
            plot_mareograma(scale=5.0, tick_type="large")

        logger.info("Successfully created ttt_max.dat")


def fortran_float_format(value: float) -> str:
    """Format floats for the legacy Fortran input parser."""
    if abs(value) < 1e-12:
        return "  0.0000000E+00"
    formatted = f"{value:17.7E}"
    return formatted.replace("e", "E")


def plot_mareograma(scale: float, tick_type: str) -> None:
    """Generate the SVG mareogram used by the report."""
    logger.info(f"Plotting mareograma with scale={scale}, tick_type={tick_type}")
    data = np.loadtxt("./zfolder/green_rev.dat")
    times = data[:, 0]
    stations = [
        ("Talara", data[:, 1]),
        ("Callao", data[:, 2]),
        ("Matarani", data[:, 3]),
    ]

    width = 720
    height = 560
    margin_left = 72
    margin_right = 28
    margin_top = 28
    panel_height = 120
    panel_gap = 45
    plot_width = width - margin_left - margin_right
    duration_hours = 28.0

    y_step = {"small": 0.05, "medium": 0.2, "large": 1.0}[tick_type]
    y_ticks = _tick_values(-scale, scale, y_step)
    x_ticks = list(range(0, int(duration_hours) + 1, 2))

    def x_to_px(value: float) -> float:
        return margin_left + (value / duration_hours) * plot_width

    def y_to_px(value: float, top: float) -> float:
        return top + ((scale - value) / (2 * scale)) * panel_height

    style = (
        "<style>text{font-family:Helvetica,Arial,sans-serif;font-size:12px}"
        ".axis{stroke:#111;stroke-width:1}.grid{stroke:#ddd;stroke-width:1}"
        ".series{fill:none;stroke:#1d4ed8;stroke-width:1.5}</style>"
    )
    elements = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
        style,
    ]

    for panel_index, (station, values) in enumerate(stations):
        top = margin_top + panel_index * (panel_height + panel_gap)
        bottom = top + panel_height

        elements.extend(
            [
                f'<rect x="{margin_left}" y="{top}" width="{plot_width}" '
                f'height="{panel_height}" fill="none" class="axis"/>',
                f'<text x="{margin_left + 8}" y="{top + 18}">{escape(station)}</text>',
            ]
        )

        for x_tick in x_ticks:
            x = x_to_px(x_tick)
            elements.append(
                f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" '
                f'y2="{bottom}" class="grid"/>'
            )
            if panel_index == len(stations) - 1:
                elements.append(
                    f'<text x="{x:.2f}" y="{bottom + 18}" '
                    f'text-anchor="middle">{x_tick}</text>'
                )

        for y_tick in y_ticks:
            y_pos = y_to_px(y_tick, top)
            elements.append(
                f'<line x1="{margin_left}" y1="{y_pos:.2f}" '
                f'x2="{margin_left + plot_width}" y2="{y_pos:.2f}" class="grid"/>'
            )
            elements.append(
                f'<text x="{margin_left - 8}" y="{y_pos + 4:.2f}" '
                f'text-anchor="end">{y_tick:g}</text>'
            )

        points = " ".join(
            f"{x_to_px(float(t)):.2f},{y_to_px(float(v), top):.2f}"
            for t, v in zip(times, values, strict=True)
        )
        elements.append(f'<polyline points="{points}" class="series"/>')

        if panel_index == 1:
            elements.append(
                f'<text x="20" y="{top + panel_height / 2:.2f}" '
                'transform="rotate(-90 20 '
                f'{top + panel_height / 2:.2f})" text-anchor="middle">H (m)</text>'
            )

    elements.append(
        f'<text x="{margin_left + plot_width / 2:.2f}" y="{height - 12}" '
        'text-anchor="middle">Time (h)</text>'
    )
    elements.append("</svg>")

    Path("mareograma.svg").write_text("\n".join(elements), encoding="utf-8")


def _tick_values(start: float, stop: float, step: float) -> list[float]:
    count = round((stop - start) / step)
    return [round(start + i * step, 10) for i in range(count + 1)]
