import shutil
from typing import Dict, Optional

from colorama import Fore, Style, init

init(autoreset=True)

COLORS = {
    "header": Fore.BLUE,
    "section": Fore.CYAN,
    "prompt": Fore.YELLOW,
    "success": Fore.GREEN,
    "error": Fore.RED,
    "warning": Fore.YELLOW,
    "info": Fore.BLUE,
    "progress": Fore.MAGENTA,
}

ICONS = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️ ",
    "info": "ℹ️ ",
    "prompt": "❓",
    "config": "⚙️ ",
    "simulation": "🌊",
    "monitoring": "📡",
    "progress": "▰",
    "empty": "▱",
}


class UserInterface:
    _verbose = False

    @classmethod
    def set_verbose(cls, verbose: bool) -> None:
        cls._verbose = verbose

    @classmethod
    def show_header(cls):
        width = shutil.get_terminal_size().columns
        print(
            f"\n{COLORS['header']}{Style.BRIGHT}"
            f"🌊 CLIENTE DE SIMULACIÓN TSUNAMI [v1.0]{Style.RESET_ALL}"
        )
        print(f"{COLORS['header']}{'=' * width}{Style.RESET_ALL}\n")

    @classmethod
    def show_section(cls, title: str, icon: str = "section"):
        icon_map = {
            "config": ICONS["config"],
            "connection": "🌐",
            "analysis": "🚀",
            "monitoring": ICONS["monitoring"],
            "success": ICONS["success"],
            "error": ICONS["error"],
        }
        section_icon = icon_map.get(icon.lower(), "»")
        print(
            f"\n{COLORS['section']}{Style.BRIGHT}"
            f"{section_icon} {title.upper()}{Style.RESET_ALL}"
        )
        cls._print_rule()

    @staticmethod
    def _print_rule(length: int = None):
        length = length or shutil.get_terminal_size().columns - 2
        print(f"{COLORS['section']}{'─' * length}{Style.RESET_ALL}")

    @classmethod
    def show_parameters(cls, config: Dict):
        params = config["simulation_params"]
        labels = {
            "Mw": ("Magnitud (Mw)", ""),
            "h": ("Profundidad", " km"),
            "lat0": ("Latitud", "°"),
            "lon0": ("Longitud", "°"),
            "hhmm": ("Hora UTC", ""),
            "dia": ("Día del mes", ""),
        }

        max_length = max(len(l[0]) for l in labels.values())

        print(f"{COLORS['info']}Parámetros de simulación:{Style.RESET_ALL}")
        for key, (label, unit) in labels.items():
            value = f"{params.get(key, 'N/D')}{unit}"
            print(f"  {label.ljust(max_length)} : {Fore.WHITE}{value}")

    @classmethod
    def show_progress_step(cls, current: int, total: int, label: str, duration: float):
        progress = f"[{current}/{total}]".ljust(6)
        duration_str = f"{Fore.WHITE}({duration:.1f}s){Style.RESET_ALL}"
        print(
            f"{COLORS['progress']}{Style.BRIGHT}"
            f"{progress} {label.ljust(40)} {ICONS['success']} "
            f"{duration_str}"
        )

    @classmethod
    def show_monitoring_status(cls, elapsed: str, progress: float, eta: str):
        bar = cls._progress_bar(progress)
        print(f"{COLORS['info']}│ {elapsed} {bar} {eta}{Style.RESET_ALL}")

    @staticmethod
    def _progress_bar(progress: float, width: int = 30):
        filled = int(width * progress)
        return (
            f"{Fore.GREEN}{ICONS['progress'] * filled}"
            f"{Fore.WHITE}{ICONS['empty'] * (width - filled)}"
            f"{Style.RESET_ALL} {progress:.0%}"
        )

    @classmethod
    def confirm(cls, prompt: str) -> bool:
        response = input(f"{COLORS['prompt']}? {prompt} (s/n): ").lower()
        return response in {"s", "si", "sí", "y", "yes"}

    @classmethod
    def get_input(cls, prompt: str, default: Optional[str] = None) -> str:
        default_text = f" [{default}]" if default else ""
        return input(f"{COLORS['prompt']}? {prompt}{default_text}: ").strip() or default

    @classmethod
    def get_float(cls, prompt: str, default: float) -> float:
        while True:
            try:
                return float(cls.get_input(prompt, str(default)))
            except ValueError:
                cls.show_error("Por favor ingrese un número válido")

    @classmethod
    def get_time(cls, prompt: str, default: str) -> str:
        while True:
            value = cls.get_input(prompt, default)
            if len(value) == 4 and value.isdigit():
                return value
            cls.show_error("Formato debe ser HHMM (4 dígitos)")

    @classmethod
    def get_day(cls, prompt: str, default: str) -> str:
        while True:
            value = cls.get_input(prompt, default)
            if value.isdigit() and 1 <= int(value) <= 31:
                return value
            cls.show_error("Día debe estar entre 1 y 31")

    @classmethod
    def show_status(cls, icon: str, message: str, color: str = Fore.WHITE):
        print(f"{color}{Style.BRIGHT}{icon} {message}{Style.RESET_ALL}")

    @classmethod
    def show_success(cls, message: str):
        cls.show_status(ICONS["success"], message, COLORS["success"])

    @classmethod
    def show_error(cls, message: str):
        cls.show_status(ICONS["error"], message, COLORS["error"])

    @classmethod
    def show_warning(cls, message: str):
        cls.show_status(ICONS["warning"], message, COLORS["warning"])

    @classmethod
    def show_info(cls, *messages: str):
        for msg in messages:
            cls.show_status(ICONS["info"], msg, COLORS["info"])
