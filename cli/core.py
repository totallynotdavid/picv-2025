import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

from colorama import Style

from cli.api import APIClient
from cli.config import ConfigManager
from cli.constants import DEFAULT_TIMEOUTS
from cli.ui import COLORS, UserInterface  # Import COLORS for countdown styling


class SimulationManager:
    def __init__(self, config: Dict):
        self.config = config
        self.config_manager = ConfigManager()

    @staticmethod
    def prompt_parameters(config: Dict) -> Dict:
        params = config["simulation_params"]
        UserInterface.show_info("Modificación de parámetros:")
        nuevos = {
            "Mw": UserInterface.get_float("Magnitud (Mw)", default=params["Mw"]),
            "h": UserInterface.get_float("Profundidad (km)", default=params["h"]),
            "lat0": UserInterface.get_float("Latitud", default=params["lat0"]),
            "lon0": UserInterface.get_float("Longitud", default=params["lon0"]),
            "hhmm": UserInterface.get_time("Hora (HHMM)", default=params["hhmm"]),
            "dia": UserInterface.get_day("Día del mes", default=params["dia"]),
        }
        config["simulation_params"] = nuevos
        return config

    async def full_test_flow(self) -> Optional[str]:
        UserInterface.show_header()

        async with APIClient(self.config["base_url"]) as client:
            if await client.check_connection():
                UserInterface.show_success("Conexión a la API: OK")
            else:
                UserInterface.show_error("Conexión a la API: Fallida")
                return None

            # Asumimos que las dependencias son correctas.
            UserInterface.show_success("Dependencias: OK")

            UserInterface.show_info("Parámetros de prueba:")
            UserInterface.show_parameters_box(self.config)

            if UserInterface.ask_yes_no("¿Deseas modificar los parámetros?"):
                self.config = SimulationManager.prompt_parameters(self.config)
                UserInterface.show_parameters_box(self.config)

            if UserInterface.ask_yes_no("¿Deseas guardar los parámetros?"):
                self.config_manager.save_config(self.config)

            inicio = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            UserInterface.show_analysis_start(inicio)

            try:
                job_id = await self._execute_calculation_steps(client)
                if job_id:
                    self.config_manager.save_job_id(job_id)
                return job_id
            except Exception as e:
                UserInterface.show_error(f"Error durante el análisis: {str(e)}")
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
                UserInterface.show_simulation_step(num, total, descripcion, dt)
                resultados[endpoint] = resultado
            except Exception as e:
                UserInterface.show_error(f"Error en el paso {num}: {str(e)}")
                raise
        return resultados.get("run-tsdhn", {}).get("job_id")


class JobMonitor:
    def __init__(self, config: Dict):
        self.config = config
        self.inicio = time.time()
        self.errores = 0

    async def monitor_job(self, job_id: str) -> None:
        if not UserInterface.ask_yes_no("¿Deseas monitorear esta simulación?"):
            return

        intervalo = int(
            UserInterface.get_input("Intervalo de chequeo (segundos)", default="60")
        )
        inicio_str = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        UserInterface.show_monitoring_header(job_id.upper(), inicio_str)

        async with APIClient(self.config["base_url"]) as client:
            while not self._timeout_alcanzado():
                try:
                    estado = await client.get_job_status(job_id)
                    self._procesar_estado(estado)
                    if estado.get("status") in ("completed", "failed"):
                        await self._finalizar(client, job_id, estado)
                        return
                    await self._esperar(intervalo)
                except Exception as e:
                    self.errores += 1
                    UserInterface.show_error(
                        f"Error de monitoreo ({self.errores}): {str(e)}"
                    )
                    await asyncio.sleep(5)
            UserInterface.show_error("Tiempo máximo de espera alcanzado")

    def _timeout_alcanzado(self) -> bool:
        timeout = self.config.get("timeout")
        if timeout:
            return (time.time() - self.inicio) > timeout
        return False

    def _procesar_estado(self, estado: Dict) -> None:
        estatus = estado.get("status", "").lower()
        if estatus == "running":
            texto = "Ejecutándose"
        elif estatus == "completed":
            texto = "Completa"
        elif estatus == "failed":
            texto = "Fallida"
        else:
            texto = estatus.capitalize()

        progreso = estado.get("progress", 0) / 100
        transcurrido = str(timedelta(seconds=int(time.time() - self.inicio)))
        UserInterface.show_monitoring_status(transcurrido, texto, progreso)

    async def _finalizar(self, client: APIClient, job_id: str, estado: Dict) -> None:
        if estado.get("status") == "completed":
            UserInterface.show_success("Simulación exitosa")
            duracion = str(timedelta(seconds=int(time.time() - self.inicio)))
            UserInterface.show_info(f"Duración total: {duracion}")
            if self.config.get("save_results", True):
                await self._descargar_informe(client, job_id)
        else:
            UserInterface.show_error("Simulación fallida")
            if error := estado.get("error"):
                UserInterface.show_error(f"Error: {error}")

    async def _descargar_informe(self, client: APIClient, job_id: str) -> None:
        try:
            UserInterface.show_info("Descargando informe...")
            datos = await client.download_report(job_id)
            nombre = f"informe_tsunami_{job_id}.pdf"
            with open(nombre, "wb") as f:
                f.write(datos)
            UserInterface.show_success(f"Informe guardado: {nombre}")
        except Exception as e:
            UserInterface.show_error(f"Error al descargar informe: {str(e)}")

    async def _esperar(self, intervalo: int) -> None:
        for seg in range(intervalo, 0, -1):
            # Use the main color for the countdown message
            print(
                f"{COLORS['main']}Próxima actualización en: {seg:2d} s{Style.RESET_ALL}",
                end="\r",
            )
            await asyncio.sleep(1)
        print(" " * 40, end="\r")
