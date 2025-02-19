import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

from cli.api import APIClient
from cli.config import ConfigManager
from cli.constants import DEFAULT_TIMEOUTS
from cli.ui import SimpleUI


class SimulationManager:
    def __init__(self, config: Dict):
        self.config = config
        self.config_manager = ConfigManager()

    async def full_test_flow(self) -> Optional[str]:
        SimpleUI.print_header()

        async with APIClient(self.config["base_url"]) as client:
            current_base_url = self.config.get("base_url", "http://localhost:8000")
            nuevo_base_url = input(
                f"◇  Base URL (actual: {current_base_url}): "
            ).strip()
            if nuevo_base_url:
                self.config["base_url"] = nuevo_base_url

            SimpleUI.show_info("")

            if await client.check_connection():
                SimpleUI.show_success("Conexión a la API: OK")
            else:
                SimpleUI.show_error("Conexión a la API: Fallida")
                return None

            SimpleUI.show_info("")

            SimpleUI.show_success("Parámetros de simulación:")
            SimpleUI.show_info(
                "   * Magnitud (Mw): "
                + str(self.config["simulation_params"].get("Mw", "N/D"))
            )
            SimpleUI.show_info(
                "   * Profundidad (km): "
                + str(self.config["simulation_params"].get("h", "N/D"))
            )
            SimpleUI.show_info(
                "   * Latitud: "
                + str(self.config["simulation_params"].get("lat0", "N/D"))
            )
            SimpleUI.show_info(
                "   * Longitud: "
                + str(self.config["simulation_params"].get("lon0", "N/D"))
            )
            SimpleUI.show_info(
                "   * Hora (UTC): "
                + str(self.config["simulation_params"].get("hhmm", "N/D"))
            )
            SimpleUI.show_info(
                "   * Día: " + str(self.config["simulation_params"].get("dia", "N/D"))
            )
            SimpleUI.show_info("")

            self.modify_parameters()
            self.config_manager.save_config(self.config)

            SimpleUI.show_info("")

            inicio = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            SimpleUI.show_success(f"Análisis iniciado [{inicio}]")
            SimpleUI.show_info("")

            job_id = await self._execute_calculation_steps(client)
            return job_id

    def modify_parameters(self):
        respuesta = (
            input("◇  ¿Deseas modificar los parámetros? (s/n): ").strip().lower()
        )
        if respuesta == "s":
            for key, label in [
                ("Mw", "Magnitud (Mw)"),
                ("h", "Profundidad (km)"),
                ("lat0", "Latitud"),
                ("lon0", "Longitud"),
                ("hhmm", "Hora (UTC)"),
                ("dia", "Día"),
            ]:
                current_val = self.config["simulation_params"].get(key)
                nuevo = input(f"│     * {label} (actual: {current_val}): ").strip()
                if nuevo:
                    if key in ["Mw", "h", "lat0", "lon0"]:
                        try:
                            nuevo = float(nuevo)
                        except ValueError:
                            SimpleUI.show_error(
                                "Valor inválido, se mantiene el valor actual"
                            )
                            continue
                    self.config["simulation_params"][key] = nuevo

        SimpleUI.show_info("")

        skip_input = input(
            "◇  ¿Deseas omitir algún paso? (Ingresa los nombres separados por comas): "
        ).strip()
        if skip_input:
            self.config["skip_steps"] = [
                step.strip() for step in skip_input.split(",") if step.strip()
            ]
        else:
            self.config["skip_steps"] = []

        SimpleUI.show_info("")

        current_interval = self.config.get("check_interval", 60)
        new_interval = input(
            "◇  Intervalo de actualización para monitoreo (segundos) "
            f"(actual: {current_interval}): "
        ).strip()

        if new_interval:
            try:
                self.config["check_interval"] = int(new_interval)
            except ValueError:
                SimpleUI.show_error(
                    "Valor inválido para intervalo, se mantiene el valor actual"
                )
        SimpleUI.show_info("")

    async def _execute_calculation_steps(self, client: APIClient) -> Optional[str]:
        pasos = [
            (1, "Parámetros iniciales", "calculate"),
            (2, "Tiempos de arribo", "tsunami-travel-times"),
            (3, "Simulación TSDHN", "run-tsdhn"),
        ]
        resultados = {}
        total = len(pasos)
        for num, descripcion, endpoint in pasos:
            t0 = time.time()
            try:
                resultado = await client.call_endpoint(
                    endpoint,
                    self.config["simulation_params"],
                    timeout=DEFAULT_TIMEOUTS.get(endpoint, 30),
                )
                dt = time.time() - t0
                SimpleUI.show_success(
                    f"[Endpoint {num}/{total}] {descripcion}... ({dt:.1f}s)"
                )
                resultados[endpoint] = resultado
            except Exception as e:
                SimpleUI.show_error(f"Error en el paso {num}: {str(e)}")
                raise

        SimpleUI.show_info("")
        job_id = resultados.get("run-tsdhn", {}).get("job_id")
        if job_id:
            SimpleUI.show_success(f"ID de simulación: {job_id}")
        SimpleUI.show_info("")
        return job_id


class JobMonitor:
    def __init__(self, config: dict, job_id: str):
        self.config = config
        self.job_id = job_id
        self.start_time = time.time()

    async def monitor_job(self) -> None:
        from rich.console import Console
        from rich.live import Live
        from rich.text import Text

        intervalo = self.config.get("check_interval", 60)
        console = Console()
        status = "Queued"
        async with APIClient(self.config["base_url"]) as client:
            try:
                estado = await client.get_job_status(self.job_id)
                status = self._map_status(estado.get("status", "Queued"))
            except Exception:
                status = "Error"
            last_api_check = time.time()
            final_state = None

            with Live(
                Text(f"◇  Estado: {status} | Tiempo transcurrido: 0:00:00"),
                refresh_per_second=4,
                console=console,
                transient=False,
            ) as live:
                finished = False
                while not finished:
                    now = time.time()
                    elapsed = int(now - self.start_time)

                    if now - last_api_check >= intervalo:
                        try:
                            estado = await client.get_job_status(self.job_id)
                            raw_status = estado.get("status", "Queued")
                            status = self._map_status(raw_status)
                            if raw_status in ("completed", "failed"):
                                finished = True
                                final_state = estado
                        except Exception:
                            status = "Error"
                        last_api_check = now

                    live.update(
                        Text(
                            f"◇  Estado: {status} | "
                            f"Tiempo transcurrido: {self._format_elapsed(elapsed)}"
                        )
                    )
                    await asyncio.sleep(1)
            await self._finalizar(client, final_state)

    def _format_elapsed(self, seconds: int) -> str:
        return str(timedelta(seconds=seconds))

    def _map_status(self, raw_status: str) -> str:
        status_map = {
            "queued": "Queued",
            "running": "Ejecutándose",
            "completed": "Completa",
            "failed": "Fallida",
        }
        return status_map.get(raw_status.lower(), raw_status.capitalize())

    async def _finalizar(self, client: APIClient, estado: dict) -> None:
        duration = self._format_elapsed(int(time.time() - self.start_time))
        if estado.get("status") == "completed":
            SimpleUI.show_success(f"Simulación completada - Duración total: {duration}")
            if self.config.get("save_results", True):
                await self._descargar_informe(client)
        else:
            SimpleUI.show_error("Simulación fallida")
            if error := estado.get("error"):
                SimpleUI.show_error(f"Error: {error}")

    async def _descargar_informe(self, client: APIClient) -> None:
        try:
            datos = await client.download_report(self.job_id)
            nombre = f"informe_tsunami_{self.job_id}.pdf"
            with open(nombre, "wb") as f:
                f.write(datos)
            SimpleUI.show_success(f"Informe guardado: {nombre}")
        except Exception as e:
            SimpleUI.show_error(f"Error al descargar informe: {str(e)}")
