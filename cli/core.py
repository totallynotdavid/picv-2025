import asyncio
import json
import sys
import time
from datetime import datetime
from typing import Dict, Optional

from colorama import Fore, Style

from cli.api import APIClient
from cli.config import ConfigManager
from cli.constants import DEFAULT_TIMEOUTS
from cli.ui import UserInterface


class SimulationManager:
    """Manejador principal de la ejecución de simulaciones"""

    def __init__(self, config: Dict):
        self.config = config
        self.config_manager = ConfigManager()
        self.ui = UserInterface()

    async def full_test_flow(self) -> Optional[str]:
        """
        Ejecuta el flujo completo de pruebas:
        1. Cálculo de parámetros iniciales
        2. Cálculo de tiempos de arribo
        3. Inicio de simulación TSDHN
        """
        async with APIClient(self.config["base_url"]) as client:
            if not await self._verify_connection(client):
                return None

            self._show_initial_header()
            self.ui.show_parameters(self.config)

            try:
                job_id = await self._execute_calculation_steps(client)
                if job_id:
                    self._save_configuration(job_id)
                return job_id
            except Exception as e:
                self.ui.show_error(f"Error en el flujo de pruebas: {str(e)}")
                return None

    async def _verify_connection(self, client: APIClient) -> bool:
        """Verifica la conexión con el servidor"""
        self.ui.show_section("🔍 VERIFICANDO CONEXIÓN")
        if await client.check_connection():
            self.ui.show_success("Conexión exitosa con el servidor")
            return True
        self.ui.show_error("No se pudo establecer conexión con el servidor")
        return False

    def _show_initial_header(self) -> None:
        """Muestra el encabezado inicial de la simulación"""
        self.ui.show_section("🥼 INICIANDO ANÁLISIS DE TSUNAMI")
        print(f"Fecha/hora: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")

    async def _execute_calculation_steps(self, client: APIClient) -> Optional[str]:
        """Ejecuta los pasos secuenciales de cálculo"""
        # Paso 1: Cálculo inicial
        self.ui.show_step(1, "Calculando parámetros iniciales del tsunami...")
        initial_params = await client.call_endpoint(
            "calculate", self.config["simulation_params"], DEFAULT_TIMEOUTS["calculate"]
        )
        self.ui.show_success("Parámetros calculados correctamente")
        print(json.dumps(initial_params, indent=2))

        # Paso 2: Tiempos de arribo
        self.ui.show_step(2, "Calculando tiempos de arribo...")
        travel_times = await client.call_endpoint(
            "tsunami-travel-times",
            self.config["simulation_params"],
            DEFAULT_TIMEOUTS["travel_times"],
        )
        self.ui.show_success("Tiempos de arribo calculados")
        print(json.dumps(travel_times, indent=2))

        # Paso 3: Iniciar simulación
        self.ui.show_step(3, "Iniciando simulación TSDHN...")
        simulation_response = await client.call_endpoint(
            "run-tsdhn", {"skip_steps": ["tsunami"]}, DEFAULT_TIMEOUTS["run_simulation"]
        )
        job_id = simulation_response["job_id"]
        self.ui.show_success("Simulación iniciada correctamente")
        self.ui.show_info(f"ID de simulación: {job_id}")
        return job_id

    def _save_configuration(self, job_id: str) -> None:
        """Guarda la configuración y ID de trabajo"""
        self.config_manager.save_config(self.config)
        self.config_manager.save_job_id(job_id)


class JobMonitor:
    """Manejador del monitoreo de trabajos en ejecución"""

    def __init__(self, config: Dict):
        self.config = config
        self.ui = UserInterface()
        self.config_manager = ConfigManager()
        self.start_time = 0.0
        self.last_progress = -1

    async def monitor_job(self, job_id: str) -> None:
        """Monitorea el progreso de un trabajo hasta su finalización"""
        self._show_monitoring_header(job_id)
        self.start_time = time.time()

        async with APIClient(self.config["base_url"]) as client:
            while True:
                if self._timeout_reached():
                    break

                try:
                    status = await client.get_job_status(job_id)
                    self._process_status(status)

                    if status["status"] in ("completed", "failed"):
                        await self._handle_final_status(client, job_id, status)
                        break

                    await self._wait_for_next_check()

                except Exception as e:
                    self._handle_monitoring_error(e)
                    await asyncio.sleep(5)

    def _show_monitoring_header(self, job_id: str) -> None:
        """Muestra el encabezado de monitoreo"""
        self.ui.show_section(f"👀 MONITOREANDO SIMULACIÓN: {job_id}")
        print(f"• Inicio: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
        print(f"• Intervalo de verificación: {self.config['check_interval']}s")
        if self.config.get("timeout"):
            print(f"• Tiempo máximo: {self.config['timeout'] / 60:.1f} minutos")

    def _timeout_reached(self) -> bool:
        """Verifica si se ha excedido el tiempo máximo de espera"""
        if self.config.get("timeout"):
            elapsed = time.time() - self.start_time
            if elapsed > self.config["timeout"]:
                self.ui.show_warning("¡Tiempo máximo de espera alcanzado!")
                self._show_resume_instructions()
                return True
        return False

    def _show_resume_instructions(self) -> None:
        """Muestra instrucciones para reanudar el monitoreo"""
        print("\nPara reanudar más tarde ejecuta:")
        print(f"{Fore.YELLOW}python -m tsunami-cli.cli --monitor last{Style.RESET_ALL}")
        print("Para extender el tiempo usa --timeout <segundos>")

    def _process_status(self, status: Dict) -> None:
        """Procesa y muestra el estado actual del trabajo"""
        current_progress = status.get("progress", 0)

        if current_progress != self.last_progress:
            self._show_progress_update(status, current_progress)
            self.last_progress = current_progress

        if status["status"] == "in_progress":
            self._show_estimated_time(status)

    def _show_progress_update(self, status: Dict, progress: float) -> None:
        """Muestra la actualización de progreso"""
        elapsed_min = (time.time() - self.start_time) / 60
        print(
            f"\n🕒 {datetime.now().strftime('%H:%M:%S')} "
            f"(Transcurrido: {elapsed_min:.1f} min)"
        )

        if "progress" in status:
            self.ui.progress_bar(progress)
            print()  # Nueva línea después de la barra

        print(json.dumps(status, indent=2, ensure_ascii=False))

    def _show_estimated_time(self, status: Dict) -> None:
        """Muestra el tiempo restante estimado"""
        if "estimated_remaining_minutes" in status:
            remaining = status["estimated_remaining_minutes"]
            if isinstance(remaining, (int, float)):
                print(f"⏳ Tiempo restante estimado: {remaining:.1f} minutos")

    async def _handle_final_status(
        self, client: APIClient, job_id: str, status: Dict
    ) -> None:
        """Maneja los estados finales de la simulación"""
        if status["status"] == "completed":
            await self._handle_completed_job(client, job_id)
        else:
            self._handle_failed_job(status)

    async def _handle_completed_job(self, client: APIClient, job_id: str) -> None:
        """Maneja una simulación completada exitosamente"""
        self.ui.show_section("✨ SIMULACIÓN COMPLETADA", Fore.GREEN)
        total_time = (time.time() - self.start_time) / 60
        print(f"🕒 Duración total: {total_time:.1f} minutos")

        if self.config.get("save_results", True):
            await self._download_and_save_report(client, job_id)

    async def _download_and_save_report(self, client: APIClient, job_id: str) -> None:
        """Descarga y guarda el informe de resultados"""
        try:
            self.ui.show_info("Descargando informe de resultados...")
            report_data = await client.download_report(job_id)
            filename = f"informe_tsunami_{job_id}.pdf"

            with open(filename, "wb") as f:
                f.write(report_data)

            self.ui.show_success(f"Informe guardado como: {filename}")
            self.ui.show_info("Abre el archivo con tu visor de PDF favorito")

        except Exception as e:
            self.ui.show_error(f"Error al descargar informe: {str(e)}")
            self.ui.show_info(
                f"Intenta descargarlo manualmente desde: "
                f"{self.config['base_url']}/job-result/{job_id}"
            )

    def _handle_failed_job(self, status: Dict) -> None:
        """Maneja una simulación fallida"""
        self.ui.show_section("⚠️ SIMULACIÓN FALLIDA", Fore.RED)
        if "error" in status:
            self.ui.show_error(f"Motivo del fallo: {status['error']}")

        self.ui.show_info("Acciones recomendadas:")
        self.ui.show_info("1. Revisa los logs del servidor en 'tsunami_api.log'")
        self.ui.show_info("2. Verifica los parámetros de la simulación")
        self.ui.show_info("3. Contacta al soporte técnico si el problema persiste")

    async def _wait_for_next_check(self) -> None:
        """Espera para la próxima verificación con cuenta regresiva"""
        intervalo = self.config["check_interval"]
        sys.stdout.write("Próxima actualización en: ")

        for i in range(intervalo, 0, -1):
            sys.stdout.write(f"\rPróxima actualización en: {i} segundos ")
            sys.stdout.flush()
            await asyncio.sleep(1)

        sys.stdout.write("\r" + " " * 40 + "\r")  # Limpiar línea

    def _handle_monitoring_error(self, error: Exception) -> None:
        """Maneja errores durante el monitoreo"""
        self.ui.show_error(f"Error de monitoreo: {str(error)}")
        self.ui.show_info("Reintentando en 5 segundos...")
