import tempfile
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from tsdhn.assets import ModelStore, model_version_for_package
from tsdhn.calculator import TsunamiCalculator
from tsdhn.domain import EarthquakeInput
from tsdhn.engine import run_simulation
from tsdhn.runtime import RuntimeContext, check_capabilities

app = typer.Typer(
    add_completion=False,
    help="TSDHN CLI for tsunami source calculations and simulations.",
)
assets_app = typer.Typer(add_completion=False, help="Manage versioned model datasets.")
app.add_typer(assets_app, name="assets")
console = Console()

MwOpt = Annotated[float, typer.Option("--mw", help="Magnitude (Mw).")]
DepthOpt = Annotated[float, typer.Option("--depth", "-h", help="Depth in km.")]
LatOpt = Annotated[float, typer.Option("--lat", help="Epicenter latitude.")]
LonOpt = Annotated[float, typer.Option("--lon", help="Epicenter longitude.")]
TimeOpt = Annotated[str, typer.Option("--time", help="Origin time as HHMM UTC.")]
DayOpt = Annotated[str, typer.Option("--day", help="Origin day of month.")]
ModelDirOpt = Annotated[
    Path | None,
    typer.Option("--model-dir", help="Explicit model dataset directory."),
]
ModelVersionOpt = Annotated[
    str | None,
    typer.Option("--model-version", help="Model dataset version."),
]


def _build_input(
    mw: float,
    depth: float,
    lat: float,
    lon: float,
    hhmm: str,
    dia: str,
) -> EarthquakeInput:
    return EarthquakeInput(Mw=mw, h=depth, lat0=lat, lon0=lon, hhmm=hhmm, dia=dia)


def _calculation_table(calc: dict[str, object]) -> Table:
    table = Table(title="Source parameters", show_header=False)
    rows = {
        "Rupture length (km)": f"{calc['length']:.2f}",
        "Rupture width (km)": f"{calc['width']:.2f}",
        "Dislocation (m)": f"{calc['dislocation']:.3f}",
        "Seismic moment (N.m)": f"{calc['seismic_moment']:.3e}",
        "Azimuth (deg)": f"{calc['azimuth']:.1f}",
        "Dip (deg)": f"{calc['dip']:.1f}",
        "Coast distance (km)": f"{calc['distance_to_coast']:.1f}",
        "Epicenter location": str(calc["epicenter_location"]),
        "Tsunami warning": str(calc["tsunami_warning"]),
    }
    for label, value in rows.items():
        table.add_row(label, value)
    return table


@assets_app.command("status")
def assets_status(model_version: ModelVersionOpt = None) -> None:
    resolved_version = model_version_for_package(model_version)
    status = ModelStore().status(resolved_version)
    console.print_json(data=status)


@assets_app.command("install")
def assets_install(
    model_version: ModelVersionOpt = None,
    url: Annotated[
        str | None, typer.Option("--url", help="Override archive URL.")
    ] = None,
    sha256: Annotated[
        str | None,
        typer.Option("--sha256", help="Expected archive SHA-256."),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Replace existing dataset.")
    ] = False,
) -> None:
    resolved_version = model_version_for_package(model_version)
    dataset = ModelStore().install(
        resolved_version,
        url=url,
        sha256=sha256,
        force=force,
    )
    console.print(f"Installed model {dataset.version}: [bold]{dataset.path}[/bold]")


@app.command()
def doctor(
    model_dir: ModelDirOpt = None, model_version: ModelVersionOpt = None
) -> None:
    try:
        runtime = RuntimeContext.resolve(
            model_dir=model_dir,
            model_version=model_version,
        )
        model_status = "available"
        model_detail = str(runtime.model_dir)
    except Exception as e:
        runtime = None
        model_status = "missing"
        model_detail = str(e)

    table = Table(title="TSDHN runtime")
    table.add_column("Capability")
    table.add_column("Status")
    table.add_column("Detail")
    table.add_row("model", model_status, model_detail)

    capabilities = runtime.capabilities if runtime is not None else check_capabilities()
    for capability in capabilities.values():
        table.add_row(
            capability.name,
            "available" if capability.available else "missing",
            capability.version or capability.path or capability.detail or "",
        )
    console.print(table)


@app.command()
def calc(
    mw: MwOpt = 9.0,
    depth: DepthOpt = 12.0,
    lat: LatOpt = -20.5,
    lon: LonOpt = -70.5,
    time: TimeOpt = "0000",
    day: DayOpt = "23",
    model_dir: ModelDirOpt = None,
    model_version: ModelVersionOpt = None,
) -> None:
    data = _build_input(mw, depth, lat, lon, time, day)
    runtime = RuntimeContext.resolve(
        model_dir=model_dir,
        model_version=model_version,
    )
    calculator = TsunamiCalculator(runtime.model_dir)
    with tempfile.TemporaryDirectory() as tmp:
        calculation = calculator.calculate_earthquake_parameters(data, Path(tmp))
    travel = calculator.calculate_tsunami_travel_times(data)

    console.print(_calculation_table(calculation.model_dump()))

    arrivals = Table(title="Tsunami arrival times")
    arrivals.add_column("Port")
    arrivals.add_column("Arrival")
    arrivals.add_column("Distance (km)", justify="right")
    distances = travel.distances
    for port, eta in travel.arrival_times.items():
        arrivals.add_row(port, eta, f"{distances.get(port, 0.0):.1f}")
    console.print(arrivals)


@app.command()
def run(
    mw: MwOpt = 9.0,
    depth: DepthOpt = 12.0,
    lat: LatOpt = -20.5,
    lon: LonOpt = -70.5,
    time: TimeOpt = "0000",
    day: DayOpt = "23",
    work_dir: Annotated[
        Path | None,
        typer.Option("--work-dir", help="Run directory. Defaults to jobs/<timestamp>."),
    ] = None,
    model_dir: ModelDirOpt = None,
    model_version: ModelVersionOpt = None,
) -> None:
    data = _build_input(mw, depth, lat, lon, time, day)
    if work_dir is None:
        work_dir = Path("jobs") / datetime.now().strftime("%Y%m%d-%H%M%S")

    console.print(
        Panel.fit(
            f"Mw={mw}  h={depth} km  lat={lat}  lon={lon}  {time} UTC day {day}\n"
            f"Run directory: [bold]{work_dir}[/bold]",
            title="TSDHN simulation",
        )
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Starting...", total=None)

        def on_progress(message: str, details: dict[str, object]) -> None:
            if "step_index" in details:
                message = (
                    f"[{details['step_index']}/{details['total_steps']}] {message}"
                )
            progress.update(task, description=message)

        try:
            result = run_simulation(
                data,
                work_dir,
                model_dir=model_dir,
                model_version=model_version,
                on_progress=on_progress,
            )
        except ValueError as e:
            progress.stop()
            console.print(f"[red]Invalid parameters:[/red] {e}")
            raise typer.Exit(code=2) from e
        except Exception as e:
            progress.stop()
            console.print(f"[red]Simulation failed:[/red] {e}")
            print(f"Inspect run directory: {work_dir}")
            raise typer.Exit(code=1) from e

    console.print(_calculation_table(result.calculation.model_dump()))
    console.print("[green]Simulation complete.[/green]")
    for output in result.outputs.files:
        console.print(f"{output.name}: [bold]{output.path}[/bold]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
