import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime

import aiohttp
from colorama import Fore, Style, init

init()

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_CHECK_INTERVAL = 60
JOB_ID_FILE = "last_job_id.txt"
CONFIG_FILE = "configuracion_simulacion.json"


def imprimir_seccion(titulo, color=Fore.CYAN):
    ancho = len(titulo) + 10
    print(f"\n{color}{Style.BRIGHT}{'-' * ancho}")
    print(f"{' ' * 5}{titulo}{' ' * 5}")
    print(f"{'-' * ancho}{Style.RESET_ALL}")


def imprimir_exito(mensaje):
    print(f"{Fore.GREEN}{Style.BRIGHT}✅ {mensaje}{Style.RESET_ALL}")


def imprimir_error(mensaje):
    print(f"{Fore.RED}{Style.BRIGHT}❌ {mensaje}{Style.RESET_ALL}")


def imprimir_advertencia(mensaje):
    print(f"{Fore.YELLOW}{Style.BRIGHT}⚠️ {mensaje}{Style.RESET_ALL}")


def imprimir_info(mensaje):
    print(f"{Fore.BLUE}{Style.BRIGHT}ℹ️ {mensaje}{Style.RESET_ALL}")


def imprimir_paso(numero, descripcion):
    print(f"{Fore.MAGENTA}{Style.BRIGHT}[{numero}] {descripcion}{Style.RESET_ALL}")


def guardar_configuracion(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        imprimir_info(f"Configuración guardada en '{CONFIG_FILE}'")
    except Exception as e:
        imprimir_advertencia(f"No se pudo guardar la configuración: {str(e)}")


def cargar_configuracion():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        imprimir_advertencia(f"No se pudo cargar la configuración: {str(e)}")

    # Default configuration
    return {
        "Mw": 9.0,
        "h": 12,
        "lat0": 56,
        "lon0": -156,
        "hhmm": "0000",
        "dia": "23",
    }


def guardar_job_id(job_id):
    try:
        with open(JOB_ID_FILE, "w") as f:
            f.write(job_id)
        imprimir_info(f"ID de la simulación guardado en '{JOB_ID_FILE}'")
    except Exception as e:
        imprimir_advertencia(f"No se pudo guardar el ID de la simulación: {str(e)}")


def cargar_ultimo_job_id():
    try:
        if os.path.exists(JOB_ID_FILE):
            with open(JOB_ID_FILE, "r") as f:
                return f.read().strip()
    except Exception as e:
        imprimir_error(f"Error al leer el ID de la última simulación: {str(e)}")
    return None


def mostrar_parametros(config):
    print(f"{Fore.CYAN}Parámetros:{Style.RESET_ALL}")
    print(f"  • Magnitud (Mw): {Fore.YELLOW}{config['Mw']}{Style.RESET_ALL}")
    print(f"  • Profundidad (h): {Fore.YELLOW}{config['h']} km{Style.RESET_ALL}")
    print(f"  • Latitud: {Fore.YELLOW}{config['lat0']}°{Style.RESET_ALL}")
    print(f"  • Longitud: {Fore.YELLOW}{config['lon0']}°{Style.RESET_ALL}")
    print(f"  • Hora (HHMM): {Fore.YELLOW}{config['hhmm']}{Style.RESET_ALL}")
    print(f"  • Día: {Fore.YELLOW}{config['dia']}{Style.RESET_ALL}")


def mostrar_barra_progreso(porcentaje, ancho=50):
    barra_completada = int(ancho * porcentaje / 100)
    barra = (
        f"[{Fore.GREEN}{'█' * barra_completada}"
        f"{Style.RESET_ALL}{'░' * (ancho - barra_completada)}]"
    )
    print(f"\r{barra} {porcentaje:.1f}%", end="", flush=True)


async def probar_conexion(session, base_url):
    try:
        async with session.get(f"{base_url}/health") as response:
            if response.status == 200:
                return True
            else:
                imprimir_error(f"El servicio respondió con STATUS {response.status}")
                return False
    except aiohttp.ClientError as e:
        imprimir_error(f"No se pudo conectar a la API en {base_url}")
        imprimir_info(f"Error de conexión: {str(e)}")
        imprimir_info("Posibles soluciones:")
        imprimir_info("1. Verifica que el servicio esté en ejecución")
        imprimir_info("2. Comprueba que la URL sea correcta")
        return False


async def test_endpoints(base_url=DEFAULT_BASE_URL):
    config = cargar_configuracion()

    imprimir_seccion("🥼 INICIANDO ANÁLISIS DE TSUNAMI")
    print(f"Fecha/hora: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
    mostrar_parametros(config)

    async with aiohttp.ClientSession() as session:
        if not await probar_conexion(session, base_url):
            return None

        try:
            # Test /calculate endpoint
            imprimir_paso(1, "Calculando parámetros iniciales del tsunami...")
            async with session.post(
                f"{base_url}/calculate", json=config, timeout=30
            ) as response:
                if response.status == 200:
                    resultado = await response.json()
                    imprimir_exito("Cálculo completado correctamente")
                    print(json.dumps(resultado, indent=2, ensure_ascii=False))
                else:
                    imprimir_error(f"Error en el cálculo: {await response.text()}")
                    return None

            # Test /tsunami-travel-times endpoint
            imprimir_paso(2, "Calculando tiempos de arribo del tsunami...")
            async with session.post(
                f"{base_url}/tsunami-travel-times", json=config, timeout=60
            ) as response:
                if response.status == 200:
                    resultado = await response.json()
                    imprimir_exito("Tiempos de arribo calculados correctamente")
                    print(json.dumps(resultado, indent=2, ensure_ascii=False))
                else:
                    imprimir_error(
                        f"Error al calcular tiempos: {await response.text()}"
                    )
                    return None

            # Submit job
            imprimir_paso(3, "Iniciando simulación (TSDHN)...")
            async with session.post(
                f"{base_url}/run-tsdhn", json={"skip_steps": ["tsunami"]}, timeout=30
            ) as response:
                if response.status == 200:
                    response_data = await response.json()
                    job_id = response_data["job_id"]
                    imprimir_exito("Simulación iniciada correctamente")
                    imprimir_info(
                        f"ID de la simulación: {Fore.YELLOW}{job_id}{Style.RESET_ALL}"
                    )
                    print(json.dumps(response_data, indent=2, ensure_ascii=False))

                    # Guardar configuración y job ID
                    guardar_configuracion(config)
                    guardar_job_id(job_id)

                    return job_id
                else:
                    imprimir_error(
                        f"Error al iniciar la simulación: {await response.text()}"
                    )
                    return None

        except asyncio.TimeoutError:
            imprimir_error("La operación ha excedido el tiempo máximo de espera")
            imprimir_info("Esto puede deberse a sobrecarga del servidor")
            return None
        except Exception as e:
            imprimir_error(f"Error durante las pruebas: {str(e)}")
            return None


async def monitor_job(
    job_id,
    base_url=DEFAULT_BASE_URL,
    check_interval=DEFAULT_CHECK_INTERVAL,
    timeout=None,
    save_result=True,
):
    if not job_id:
        imprimir_error("No se proporcionó un ID de simulación válido")
        return

    imprimir_seccion(f"👀 MONITOREANDO SIMULACIÓN: {job_id}")
    print(f"Inicio: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
    print(f"Intervalo de verificación: {check_interval} segundos")
    if timeout:
        print(f"Tiempo máximo de espera: {timeout / 60:.1f} minutos")

    async with aiohttp.ClientSession() as session:
        if not await probar_conexion(session, base_url):
            return

        start_time = time.time()
        last_progress = -1

        while True:
            elapsed_seconds = time.time() - start_time
            if timeout and (elapsed_seconds > timeout):
                imprimir_advertencia(
                    "Se alcanzó el tiempo máximo de espera",
                    f"({timeout / 60:.1f} minutos)",
                )
                print("\nPara reanudar el monitoreo, ejecuta:")
                print(
                    f"{Fore.YELLOW}python {os.path.basename(__file__)}",
                    f"--monitor {job_id}{Style.RESET_ALL}",
                )
                print(
                    "Para extender el tiempo de monitoreo, agrega --timeout <segundos>"
                )
                break

            try:
                async with session.get(
                    f"{base_url}/job-status/{job_id}", timeout=15
                ) as status_response:
                    if status_response.status != 200:
                        imprimir_error(
                            f"Error al consultar STATUS: {await status_response.text()}"
                        )
                        break

                    status = await status_response.json()
                    elapsed_minutes = elapsed_seconds / 60

                    current_progress = status.get("progress", 0)
                    if current_progress != last_progress:
                        print(
                            f"\nProgreso a las {datetime.now().strftime('%H:%M:%S')} "
                            f"(tiempo transcurrido: {elapsed_minutes:.1f} min):"
                        )
                        if "progress" in status:
                            mostrar_barra_progreso(current_progress)
                            print()  # Nueva línea después de la barra
                        print(json.dumps(status, indent=2, ensure_ascii=False))
                        last_progress = current_progress

                    if status["status"] == "completed":
                        imprimir_seccion("✨ SIMULACIÓN COMPLETADA", Fore.GREEN)
                        print(f"Duración total: {elapsed_minutes:.1f} minutos")

                        if save_result:
                            try:
                                imprimir_info(
                                    "Descargando informe con los resultados..."
                                )
                                async with session.get(
                                    f"{base_url}/job-result/{job_id}", timeout=60
                                ) as result_response:
                                    if result_response.status == 200:
                                        filename = f"informe_tsunami_{job_id}.pdf"
                                        with open(filename, "wb") as f:
                                            f.write(await result_response.read())
                                        imprimir_exito(
                                            f"Informe guardado como: {filename}"
                                        )
                                        imprimir_info(
                                            "Puedes abrir el informe con tu visor",
                                            "de PDF favorito",
                                        )
                                    else:
                                        imprimir_error(
                                            "Error al obtener resultados:",
                                            f"{await result_response.text()}",
                                        )
                            except asyncio.TimeoutError:
                                imprimir_error(
                                    "Tiempo de espera excedido al descargar el informe"
                                )
                                imprimir_info(
                                    "Puedes intentar descargarlo manualmente desde",
                                    f"{base_url}/job-result/{job_id}",
                                )
                        break

                    elif status["status"] == "failed":
                        imprimir_seccion("⚠️ SIMULACIÓN FALLIDA", Fore.RED)
                        if "error" in status:
                            imprimir_error(f"Motivo: {status['error']}")
                        imprimir_info(
                            "Revisa los logs del servidor en",
                            "'tsunami_api.log' para más detalles",
                        )
                        imprimir_info(
                            "Contacta con el equipo de soporte si el problema persiste",
                            "en https://github.com/totallynotdavid/picv-2025/",
                        )
                        break

                    if status["status"] == "in_progress":
                        estimated_remaining = status.get(
                            "estimated_remaining_minutes", "desconocido"
                        )
                        if isinstance(estimated_remaining, (int, float)):
                            print(
                                "Tiempo estimado restante:",
                                f"{estimated_remaining:.1f} minutos",
                            )

                    sys.stdout.write("Próxima actualización en: ")
                    for i in range(check_interval, 0, -1):
                        sys.stdout.write(f"\rPróxima actualización en: {i} segundos")
                        sys.stdout.flush()
                        await asyncio.sleep(1)
                    sys.stdout.write("\r" + " " * 40 + "\r")  # Limpiar línea

            except asyncio.TimeoutError:
                imprimir_advertencia("Tiempo de espera excedido al consultar el STATUS")
                imprimir_info("Reintentando en el próximo intervalo...")
            except aiohttp.ClientError as e:
                imprimir_error(f"Error de conexión: {str(e)}")
                imprimir_info("Reintentando en el próximo intervalo...")
            except Exception as e:
                imprimir_error(f"Error inesperado: {str(e)}")
                imprimir_info("Reintentando en el próximo intervalo...")

            # Esperar antes de la próxima verificación
            await asyncio.sleep(
                1
            )  # Pequeña pausa para evitar el bucle continuo en caso de error


def solicitar_confirmacion(mensaje="¿Deseas continuar?"):
    respuesta = input(f"{mensaje} (s/n): ").lower()
    return respuesta == "s" or respuesta == "si" or respuesta == "sí"


async def main():
    parser = argparse.ArgumentParser(
        description="Herramienta de pruebas para el Orchestrator-TSDHN",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--test",
        action="store_true",
        help="Ejecutar pruebas en todos los endpoints e iniciar una simulación",
    )
    group.add_argument(
        "--monitor",
        metavar="ID_SIMULACION",
        help="Monitorear una simulación existente. "
        "Usa 'last' para monitorear la más reciente",
    )

    parser.add_argument(
        "--url",
        default=DEFAULT_BASE_URL,
        help="URL base de la API",
    )
    parser.add_argument(
        "--intervalo",
        type=int,
        default=DEFAULT_CHECK_INTERVAL,
        help="Intervalo de verificación en segundos "
        f"(predeterminado: {DEFAULT_CHECK_INTERVAL})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        help="Tiempo máximo de monitorización en segundos (opcional)",
    )
    parser.add_argument(
        "--no-guardar",
        action="store_true",
        help="No guardar los archivos de resultados (opcional)",
    )

    args = parser.parse_args()

    # Banner de inicio
    print(f"\n{Fore.CYAN}{Style.BRIGHT}" + "=" * 60)
    print(" CLIENTE TSDHN - SISTEMA DE ALERTA DE TSUNAMIS ".center(60))
    print("=" * 60 + f"{Style.RESET_ALL}\n")

    try:
        if args.test:
            job_id = await test_endpoints(args.url)
            if job_id:
                if solicitar_confirmacion("¿Deseas monitorizar esta simulación?"):
                    await monitor_job(
                        job_id,
                        args.url,
                        args.intervalo,
                        args.timeout,
                        not args.no_guardar,
                    )
            else:
                imprimir_error("No se pudo iniciar la simulación")
                imprimir_info("Revisa los errores anteriores para más detalles")
        else:  # args.monitor está presente por el grupo mutuamente excluyente
            job_id = args.monitor
            if job_id.lower() == "last":
                job_id = cargar_ultimo_job_id()
                if job_id:
                    imprimir_info(f"Usando el ID de la última simulación: {job_id}")
                else:
                    imprimir_error("No se encontró ningún ID de simulación guardado")
                    print(
                        "Por favor, proporciona un ID específico con",
                        "--monitor ID_SIMULACION",
                    )
                    return

            await monitor_job(
                job_id, args.url, args.intervalo, args.timeout, not args.no_guardar
            )
    except KeyboardInterrupt:
        print("\n")
        imprimir_advertencia("Operación cancelada por el usuario")
        imprimir_info("Puedes reanudar el monitoreo más tarde con:")
        if "job_id" in locals() and job_id:
            print(
                f"{Fore.YELLOW}python {os.path.basename(__file__)}",
                f"--monitor {job_id}{Style.RESET_ALL}",
            )
    except Exception as e:
        imprimir_error(f"Error inesperado: {str(e)}")
        imprimir_info(
            "Si el problema persiste, contacta con el equipo de soporte técnico",
            "en https://github.com/totallynotdavid/picv-2025/",
        )


if __name__ == "__main__":
    import importlib.util

    if importlib.util.find_spec("colorama") is None:
        print("⚠️  Se requiere el paquete 'colorama' para una mejor experiencia visual.")
        print("   Instálalo con: poetry add colorama -D")
        print("   Continuando sin colores...\n")

    asyncio.run(main())
