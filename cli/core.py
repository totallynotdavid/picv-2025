import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

from colorama import Fore

from cli.api import APIClient
from cli.config import ConfigManager
from cli.constants import DEFAULT_TIMEOUTS
from cli.ui import UserInterface


class SimulationManager:
    def __init__(self, config: Dict):
        self.config = config
        self.config_manager = ConfigManager()

    @staticmethod
    def prompt_parameters(config: Dict) -> Dict:
        params = config["simulation_params"]
        UserInterface.show_section("Configuración de Simulación")

        new_params = {
            "Mw": UserInterface.get_float("Magnitud (Mw)", default=params["Mw"]),
            "h": UserInterface.get_float("Profundidad (km)", default=params["h"]),
            "lat0": UserInterface.get_float("Latitud", default=params["lat0"]),
            "lon0": UserInterface.get_float("Longitud", default=params["lon0"]),
            "hhmm": UserInterface.get_time("Hora (HHMM)", default=params["hhmm"]),
            "dia": UserInterface.get_day("Día del mes", default=params["dia"]),
        }

        config["simulation_params"] = new_params
        return config

    async def full_test_flow(self) -> Optional[str]:
        async with APIClient(self.config["base_url"]) as client:
            if not await self._verify_connection(client):
                return None

            self._show_operation_header()
            UserInterface.show_parameters(self.config)

            try:
                job_id = await self._execute_calculation_steps(client)
                if job_id:
                    self._save_configuration(job_id)
                return job_id
            except Exception as e:
                UserInterface.show_error(f"Error en el flujo: {str(e)}")
                return None

    async def _verify_connection(self, client: APIClient) -> bool:
        UserInterface.show_section("Verificación de Conexión")
        try:
            if await client.check_connection():
                UserInterface.show_success("Conexión establecida")
                return True
            return False
        except Exception as e:
            UserInterface.show_error(f"Error de conexión: {str(e)}")
            return False

    def _show_operation_header(self) -> None:
        UserInterface.show_section("Inicio de Análisis")
        print(
            f"{Fore.CYAN}│ Fecha/hora: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"
        )

    async def _execute_calculation_steps(self, client: APIClient) -> Optional[str]:
        steps = [
            (1, "calculate", "Calculando parámetros iniciales..."),
            (2, "tsunami-travel-times", "Calculando tiempos de arribo..."),
            (3, "run-tsdhn", "Iniciando simulación TSDHN..."),
        ]

        results = {}
        for step_num, endpoint, description in steps:
            UserInterface.show_step(step_num, description)
            try:
                result = await client.call_endpoint(
                    endpoint,
                    self.config["simulation_params"],
                    timeout=DEFAULT_TIMEOUTS.get(endpoint, 30),
                )
                UserInterface.show_json(result)
                results[endpoint] = result
            except Exception as e:
                UserInterface.show_error(f"Error en paso {step_num}: {str(e)}")
                raise

        return results.get("run-tsdhn", {}).get("job_id")

    def _save_configuration(self, job_id: str) -> None:
        self.config_manager.save_config(self.config)
        self.config_manager.save_job_id(job_id)
        UserInterface.show_success(f"Configuración guardada - ID: {job_id}")


class JobMonitor:
    def __init__(self, config: Dict):
        self.config = config
        self.start_time = time.time()
        self.last_progress = 0
        self.status_counts = {"success": 0, "errors": 0}

    async def monitor_job(self, job_id: str) -> None:
        self._show_monitoring_header(job_id)

        async with APIClient(self.config["base_url"]) as client:
            while not self._timeout_reached():
                try:
                    status = await client.get_job_status(job_id)
                    self._process_status(status)

                    if status["status"] in ("completed", "failed"):
                        await self._handle_final_status(client, job_id, status)
                        return

                    await self._wait_for_next_check()

                except Exception as e:
                    self._handle_monitoring_error(e)
                    await asyncio.sleep(5)

            self._handle_timeout()

    def _show_monitoring_header(self, job_id: str) -> None:
        UserInterface.show_section(f"Monitoreo de Simulación: {job_id}")
        print(f"{Fore.CYAN}│ Inicio: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
        print(f"│ Intervalo: {self.config['check_interval']}s")
        if timeout := self.config.get("timeout"):
            print(f"│ Tiempo máximo: {timedelta(seconds=timeout)}")

    def _timeout_reached(self) -> bool:
        if timeout := self.config.get("timeout"):
            elapsed = time.time() - self.start_time
            return elapsed > timeout
        return False

    def _process_status(self, status: Dict) -> None:
        current_progress = status.get("progress", 0)
        self._update_progress(current_progress)
        self._show_status_details(status)

    def _update_progress(self, progress: int) -> None:
        if progress != self.last_progress:
            UserInterface.progress_bar(progress, 100, "Progreso:")
            self.last_progress = progress

    def _show_status_details(self, status: Dict) -> None:
        elapsed = timedelta(seconds=time.time() - self.start_time)
        print(f"{Fore.CYAN}│ Tiempo transcurrido: {elapsed}")
        UserInterface.show_json(status, "Estado actual")

        if est := status.get("estimated_remaining_minutes"):
            print(f"{Fore.CYAN}│ Tiempo restante estimado: {est:.1f} minutos")

    async def _handle_final_status(
        self, client: APIClient, job_id: str, status: Dict
    ) -> None:
        if status["status"] == "completed":
            await self._handle_success(client, job_id)
        else:
            self._handle_failure(status)

    async def _handle_success(self, client: APIClient, job_id: str) -> None:
        UserInterface.show_section("Simulación Exitosa", Fore.GREEN)
        total_time = timedelta(seconds=time.time() - self.start_time)
        print(f"{Fore.GREEN}│ Duración total: {total_time}")

        if self.config.get("save_results", True):
            await self._download_report(client, job_id)

    async def _download_report(self, client: APIClient, job_id: str) -> None:
        try:
            UserInterface.show_info("Descargando informe...")
            report_data = await client.download_report(job_id)
            filename = f"informe_tsunami_{job_id}.pdf"

            with open(filename, "wb") as f:
                f.write(report_data)

            UserInterface.show_success(f"Informe guardado: {filename}")
        except Exception as e:
            UserInterface.show_error(f"Error en descarga: {str(e)}")

    def _handle_failure(self, status: Dict) -> None:
        UserInterface.show_section("Simulación Fallida", Fore.RED)
        if error := status.get("error"):
            UserInterface.show_error(f"Error: {error}")

        print(
            f"{Fore.RED}│ Tiempo transcurrido: {timedelta(seconds=time.time() - self.start_time)}"
        )
        UserInterface.show_info(
            "Recomendaciones:",
            "1. Verifique los parámetros de entrada",
            "2. Revise los logs del servidor",
            "3. Contacte al soporte técnico",
        )

    async def _wait_for_next_check(self) -> None:
        interval = self.config["check_interval"]
        for remaining in range(interval, 0, -1):
            print(f"{Fore.CYAN}│ Próxima actualización en: {remaining}s", end="\r")
            await asyncio.sleep(1)
        print(" " * 50, end="\r")  # Clear line

    def _handle_monitoring_error(self, error: Exception) -> None:
        self.status_counts["errors"] += 1
        UserInterface.show_error(
            f"Error de monitoreo ({self.status_counts['errors']}): {str(error)}"
        )

    def _handle_timeout(self) -> None:
        UserInterface.show_warning("Tiempo máximo de espera alcanzado")
        print(f"{Fore.YELLOW}│ Para reanudar:")
        print("│ python -m cli.cli --monitor last")
        print("│ Agregar --timeout para extender el tiempo")
