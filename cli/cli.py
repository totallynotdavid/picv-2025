import argparse
import asyncio

from cli.main import main


def parse_args():
    parser = argparse.ArgumentParser(description="Cliente de Simulación TSUNAMI")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Mostrar detalles técnicos"
    )
    return parser.parse_args()


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
