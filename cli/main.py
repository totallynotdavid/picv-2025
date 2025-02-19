import asyncio

from cli.config import ConfigManager
from cli.core import JobMonitor, SimulationManager
from cli.ui import RichUI


async def main():
    config = ConfigManager().load_config()
    sim = SimulationManager(config)
    job_id = await sim.full_test_flow()
    if job_id:
        job_monitor = JobMonitor(config, job_id)
        await job_monitor.monitor_job()
    else:
        RichUI.show_error("La simulación no pudo ser iniciada.")
    RichUI.show_info("Usa -v para ver detalles técnicos.")


if __name__ == "__main__":
    asyncio.run(main())
