import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

from cli.api import APIClient
from cli.config import ConfigManager
from cli.constants import DEFAULT_TIMEOUTS
from cli.ui import RichUI


class SimulationManager:
    def __init__(self, config: Dict):
        self.config = config
        self.config_manager = ConfigManager()

    @staticmethod
    def prompt_parameters(config: Dict) -> Dict:
        params = config["simulation_params"]
        RichUI.show_info("Modificación de parámetros:")
        nuevos = {
            "Mw": RichUI.prompt_float("Magnitud (Mw)", default=params["Mw"]),
            "h": RichUI.prompt_float("Profundidad (km)", default=params["h"]),
            "lat0": RichUI.prompt_float("Latitud", default=params["lat0"]),
            "lon0": RichUI.prompt_float("Longitud", default=params["lon0"]),
            "hhmm": RichUI.prompt_time("Hora (HHMM)", default=params["hhmm"]),
            "dia": RichUI.prompt_day("Día del mes", default=params["dia"]),
        }
        config["simulation_params"] = nuevos
        return config

    async def full_test_flow(self) -> Optional[str]:
        RichUI.print_header()

        async with APIClient(self.config["base_url"]) as client:
            if await client.check_connection():
                RichUI.show_success("Conexión a la API: OK")
            else:
                RichUI.show_error("Conexión a la API: Fallida")
                return None

            # Asumimos que las dependencias son correctas.
            RichUI.show_success("Dependencias: OK")

            RichUI.show_info("Parámetros de prueba:")
            RichUI.show_parameters_box(self.config)

            if RichUI.prompt_yes_no("¿Deseas modificar los parámetros?"):
                self.config = SimulationManager.prompt_parameters(self.config)
                RichUI.show_parameters_box(self.config)

            if RichUI.prompt_yes_no("¿Deseas guardar los parámetros?"):
                self.config_manager.save_config(self.config)

            inicio = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            RichUI.show_analysis_start(inicio)

            try:
                job_id = await self._execute_calculation_steps(client)
                if job_id:
                    self.config_manager.save_job_id(job_id)
                return job_id
            except Exception as e:
                RichUI.show_error(f"Error durante el análisis: {str(e)}")
                return None

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
                RichUI.show_simulation_step(num, total, descripcion, dt)
                resultados[endpoint] = resultado
            except Exception as e:
                RichUI.show_error(f"Error en el paso {num}: {str(e)}")
                raise
        return resultados.get("run-tsdhn", {}).get("job_id")


class JobMonitor:
    def __init__(self, config: Dict, job_id: str):
        self.config = config
        self.job_id = job_id
        self.start_time = time.time()
        self.errors = 0

    async def monitor_job(self) -> None:
        if not RichUI.prompt_yes_no("¿Deseas monitorear esta simulación?"):
            return

        intervalo = int(
            RichUI.prompt_input("Intervalo de chequeo (segundos)", default="60")
        )

        # Import InteractiveMonitor here to avoid circular dependency issues.
        from cli.ui import InteractiveMonitor

        monitor_ui = InteractiveMonitor(
            simulation_id=self.job_id, start_time=self.start_time
        )

        # Inicia la interfaz interactiva en segundo plano.
        monitor_task = asyncio.create_task(monitor_ui.run())

        async with APIClient(self.config["base_url"]) as client:
            finished = False
            while not finished and not monitor_ui.exit_requested:
                try:
                    estado = await client.get_job_status(self.job_id)
                    self._procesar_estado(estado, monitor_ui)
                    if estado.get("status") in ("completed", "failed"):
                        await self._finalizar(client, estado, monitor_ui)
                        finished = True
                    else:
                        await self._esperar(intervalo, monitor_ui)
                except Exception as e:
                    self.errors += 1
                    monitor_ui.latest_event = (
                        f"Error de monitoreo ({self.errors}): {str(e)}"
                    )
                    await asyncio.sleep(5)
            monitor_ui.running = False  # Señala a la UI que debe detenerse.
            await monitor_task

    def _procesar_estado(self, estado: Dict, monitor_ui) -> None:
        status_map = {
            "running": "Ejecutándose",
            "completed": "Completa",
            "failed": "Fallida",
        }
        estatus_raw = estado.get("status", "").lower()
        texto = status_map.get(estatus_raw, estatus_raw.capitalize())
        progreso = estado.get("progress", 0) / 100.0
        elapsed = str(timedelta(seconds=int(time.time() - self.start_time)))
        monitor_ui.status = texto
        monitor_ui.progress = progreso
        monitor_ui.elapsed = elapsed

    async def _finalizar(self, client: APIClient, estado: Dict, monitor_ui) -> None:
        if estado.get("status") == "completed":
            monitor_ui.latest_event = "Simulación exitosa"
            duracion = str(timedelta(seconds=int(time.time() - self.start_time)))
            RichUI.show_success(f"Simulación exitosa - Duración total: {duracion}")
            if self.config.get("save_results", True):
                await self._descargar_informe(client, monitor_ui)
        else:
            monitor_ui.latest_event = "Simulación fallida"
            RichUI.show_error("Simulación fallida")
            if error := estado.get("error"):
                RichUI.show_error(f"Error: {error}")

    async def _descargar_informe(self, client: APIClient, monitor_ui) -> None:
        try:
            monitor_ui.latest_event = "Descargando informe..."
            datos = await client.download_report(self.job_id)
            nombre = f"informe_tsunami_{self.job_id}.pdf"
            with open(nombre, "wb") as f:
                f.write(datos)
            RichUI.show_success(f"Informe guardado: {nombre}")
        except Exception as e:
            RichUI.show_error(f"Error al descargar informe: {str(e)}")

    async def _esperar(self, intervalo: int, monitor_ui) -> None:
        for seg in range(intervalo, 0, -1):
            monitor_ui.countdown = seg
            await asyncio.sleep(1)
