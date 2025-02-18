from pathlib import Path

DEFAULT_CONFIG = {
    "base_url": "http://localhost:8000",
    "check_interval": 60,
    "timeout": None,
    "save_results": True,
    "simulation_params": {
        "Mw": 9.0,
        "h": 12,
        "lat0": 56,
        "lon0": -156,
        "hhmm": "0000",
        "dia": "23",
    },
}

CONFIG_FILE = Path("configuracion_simulacion.json")
JOB_ID_FILE = Path("last_job_id.txt")
DEFAULT_TIMEOUTS = {
    "calculate": 30,
    "travel_times": 60,
    "run_simulation": 30,
    "status_check": 15,
    "report_download": 60,
}
