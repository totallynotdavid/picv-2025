import argparse
import asyncio
import importlib.util
import sys

from .config import ConfigManager
from .core import JobMonitor, SimulationManager
from .ui import UserInterface


def check_dependencies():
    if importlib.util.find_spec("colorama") is None:
        print("⚠️  Instala colorama para mejor experiencia: pip install colorama")


def prompt_confirmation(message: str = "¿Continuar?") -> bool:
    response = input(f"{message} (s/n): ").lower()
    return response in {"s", "si", "sí"}


async def main():
    check_dependencies()

    parser = argparse.ArgumentParser(
        description="Cliente TSDHN - Sistema de Alerta de Tsunamis",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--test", action="store_true", help="Ejecutar prueba completa")
    group.add_argument(
        "--monitor", nargs="?", const="last", help="Monitorear simulación"
    )

    parser.add_argument("--url", help="URL base de la API")
    parser.add_argument("--intervalo", type=int, help="Intervalo de verificación (s)")
    parser.add_argument("--timeout", type=int, help="Tiempo máximo de monitoreo (s)")
    parser.add_argument("--no-guardar", action="store_false", dest="save_results")

    args = parser.parse_args()
    cm = ConfigManager()
    config = cm.load_config()

    # Actualizar configuración con argumentos CLI
    if args.url:
        config["base_url"] = args.url
    if args.intervalo:
        config["check_interval"] = args.intervalo
    if args.timeout:
        config["timeout"] = args.timeout
    config["save_results"] = args.save_results

    try:
        if args.test:
            manager = SimulationManager(config)
            job_id = await manager.full_test_flow()
            if job_id and prompt_confirmation("¿Monitorizar esta simulación?"):
                monitor = JobMonitor(config)
                await monitor.monitor_job(job_id)
        else:
            job_id = args.monitor
            if job_id == "last":
                job_id = cm.load_last_job_id()
                if not job_id:
                    UserInterface.show_error("No hay simulaciones recientes")
                    return
                UserInterface.show_info(f"Usando última simulación: {job_id}")

            monitor = JobMonitor(config)
            await monitor.monitor_job(job_id)

    except KeyboardInterrupt:
        UserInterface.show_warning("\nOperación cancelada por el usuario")
    except Exception as e:
        UserInterface.show_error(f"Error crítico: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
