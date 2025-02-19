import asyncio

from cli.config import ConfigManager
from cli.core import JobMonitor, SimulationManager
from cli.ui import SimpleUI


async def main(args):
    config = ConfigManager().load_config()
    sim = SimulationManager(config, dev_mode=args.dev)
    job_id = await sim.full_test_flow()
    if job_id:
        monitor = JobMonitor(config, job_id)
        await monitor.monitor_job()
    else:
        SimpleUI.show_error("La simulación no pudo ser iniciada.")
    SimpleUI.print_exit()


if __name__ == "__main__":
    asyncio.run(main())
