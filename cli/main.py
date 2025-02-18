import asyncio

from cli.config import ConfigManager
from cli.core import JobMonitor, SimulationManager
from cli.ui import UserInterface


async def main():
    config = ConfigManager().load_config()
    sim = SimulationManager(config)
    job_id = await sim.full_test_flow()
    if job_id:
        monitor = JobMonitor(config)
        await monitor.monitor_job(job_id)
    else:
        UserInterface.show_error("La simulación no pudo ser iniciada.")
    UserInterface.show_info("Usa -v para ver detalles técnicos.")


if __name__ == "__main__":
    asyncio.run(main())
