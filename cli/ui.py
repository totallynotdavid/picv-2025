from typing import Dict, Optional

from colorama import Fore, Style, init

init(autoreset=True)

# Usamos solo tres colores:
COLORS = {
    "main": Fore.CYAN,
    "success": Fore.GREEN,
    "error": Fore.RED,
}

# Íconos simples
ICONS = {
    "header": "🌊",
    "check": "✓",
    "error": "✗",
}


class UserInterface:
    _verbose = False

    @classmethod
    def set_verbose(cls, verbose: bool) -> None:
        cls._verbose = verbose

    @classmethod
    def show_header(cls) -> None:
        print(
            f"\n{COLORS['main']}{Style.BRIGHT}{ICONS['header']} CLI del Orchestrator-TSDHN [v1.0]{Style.RESET_ALL}\n"
        )

    @classmethod
    def show_parameters_box(cls, config: Dict) -> None:
        params = config.get("simulation_params", {})
        lines = [
            f"Magnitud (Mw)    : {params.get('Mw', 'N/D')}",
            f"Profundidad (km) : {params.get('h', 'N/D')}",
            f"Latitud          : {params.get('lat0', 'N/D')}°",
            f"Longitud         : {params.get('lon0', 'N/D')}°",
            f"Hora (UTC)       : {params.get('hhmm', 'N/D')}",
            f"Día del mes      : {params.get('dia', 'N/D')}",
        ]
        width = max(len(line) for line in lines) + 4
        top = "╔" + "═" * (width - 2) + "╗"
        bottom = "╚" + "═" * (width - 2) + "╝"
        print(COLORS["main"] + top + Style.RESET_ALL)
        for line in lines:
            print(
                COLORS["main"] + "║ " + line.ljust(width - 4) + " ║" + Style.RESET_ALL
            )
        print(COLORS["main"] + bottom + Style.RESET_ALL)
        print()

    @classmethod
    def ask_yes_no(cls, pregunta: str) -> bool:
        respuesta = (
            input(f"{COLORS['main']}{pregunta} [y/N]: {Style.RESET_ALL}")
            .strip()
            .lower()
        )
        return respuesta in {"y", "yes", "s", "si", "sí"}

    @classmethod
    def get_input(cls, prompt: str, default: Optional[str] = None) -> str:
        dft = f" [{default}]" if default else ""
        respuesta = input(f"{COLORS['main']}{prompt}{dft}: {Style.RESET_ALL}").strip()
        return respuesta if respuesta else (default or "")

    @classmethod
    def get_float(cls, prompt: str, default: float) -> float:
        while True:
            val = cls.get_input(prompt, str(default))
            try:
                return float(val)
            except ValueError:
                cls.show_error("Por favor ingrese un número válido.")

    @classmethod
    def get_time(cls, prompt: str, default: str) -> str:
        while True:
            val = cls.get_input(prompt, default)
            if len(val) == 4 and val.isdigit():
                return val
            cls.show_error("El formato debe ser HHMM (4 dígitos).")

    @classmethod
    def get_day(cls, prompt: str, default: str) -> str:
        while True:
            val = cls.get_input(prompt, default)
            if val.isdigit() and 1 <= int(val) <= 31:
                return val
            cls.show_error("El día debe estar entre 1 y 31.")

    @classmethod
    def show_success(cls, mensaje: str) -> None:
        print(
            f"{COLORS['success']}{Style.BRIGHT}{ICONS['check']} {mensaje}{Style.RESET_ALL}"
        )

    @classmethod
    def show_error(cls, mensaje: str) -> None:
        print(
            f"{COLORS['error']}{Style.BRIGHT}{ICONS['error']} {mensaje}{Style.RESET_ALL}"
        )

    @classmethod
    def show_info(cls, mensaje: str) -> None:
        print(f"{COLORS['main']}{mensaje}{Style.RESET_ALL}")

    @classmethod
    def show_analysis_start(cls, timestamp: str) -> None:
        print(
            f"\n{COLORS['main']}{Style.BRIGHT}🚀 El análisis ha comenzado [{timestamp}]{Style.RESET_ALL}"
        )
        print("-" * 44)

    @classmethod
    def show_simulation_step(
        cls, actual: int, total: int, descripcion: str, duracion: float
    ) -> None:
        linea = f"[{actual}/{total}] {descripcion}... ({duracion:.1f}s)"
        print(f"{COLORS['main']}{linea}{Style.RESET_ALL}")

    @classmethod
    def show_monitoring_header(cls, sim_id: str, inicio: str) -> None:
        print(
            f"\n{COLORS['main']}{Style.BRIGHT}🕒 Monitoreando {sim_id} [Inicio {inicio}]{Style.RESET_ALL}"
        )
        print("-" * 44)

    @classmethod
    def show_monitoring_status(
        cls, transcurrido: str, estado: str, progreso: float
    ) -> None:
        barra = cls._progress_bar(progreso)
        print(
            f"{COLORS['main']}[{transcurrido}] Estado: {estado} {barra}{Style.RESET_ALL}"
        )

    @classmethod
    def _progress_bar(cls, progreso: float, ancho: int = 30) -> str:
        llenado = int(ancho * progreso)
        vacio = ancho - llenado
        return f"[{'█' * llenado}{'░' * vacio}] {progreso:.0%}"
