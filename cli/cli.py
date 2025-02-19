import argparse
import asyncio

from cli.main import main


def parse_args():
    parser = argparse.ArgumentParser(description="Cliente de Simulación TSUNAMI")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Activar modo desarrollador para opciones avanzadas",
    )
    return parser.parse_args()


def run():
    args = parse_args()
    asyncio.run(main(args))


if __name__ == "__main__":
    run()
