import json
from typing import Dict, Optional

from colorama import Fore, Style, init

# Initialize colorama automatically
init(autoreset=True)


class UserInterface:
    _verbose = False

    @classmethod
    def set_verbose(cls, verbose: bool) -> None:
        cls._verbose = verbose

    @classmethod
    def show_section(cls, title: str, color: str = Fore.CYAN) -> None:
        print(f"{color}{Style.BRIGHT}» {title.upper()}{Style.RESET_ALL}")
        print(f"{color}——————————————————————————————————————————————{Style.RESET_ALL}")

    @classmethod
    def show_json(cls, data: Dict, title: str = "") -> None:
        if cls._verbose:
            if title:
                print(f"{Fore.CYAN}{title}:{Style.RESET_ALL}")
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            cls.show_info("Use -v para ver detalles técnicos completos")

    @classmethod
    def confirm(cls, prompt: str) -> bool:
        response = input(f"{Fore.YELLOW}? {prompt} (s/n): {Style.RESET_ALL}").lower()
        return response in {"s", "si", "sí", "y", "yes"}

    @classmethod
    def progress_bar(cls, current: int, total: int, label: str = "") -> None:
        bar_length = 40
        progress = current / total
        filled = int(bar_length * progress)
        bar = (
            f"{Fore.GREEN}{'█' * filled}{Style.RESET_ALL}{'░' * (bar_length - filled)}"
        )
        percentage = f"{progress:.0%}"
        output = f"  {label} {bar} {percentage}"
        print(output, end="\n", flush=True)
        if current == total:
            print()  # Maintain final state

    @classmethod
    def show_status(cls, icon: str, message: str, color: str = Fore.WHITE) -> None:
        print(f"{color}{Style.BRIGHT}{icon} {message}{Style.RESET_ALL}")

    @classmethod
    def show_success(cls, message: str) -> None:
        cls.show_status("✅", message, Fore.GREEN)

    @classmethod
    def show_error(cls, message: str) -> None:
        cls.show_status("❌", message, Fore.RED)

    @classmethod
    def show_warning(cls, message: str) -> None:
        cls.show_status("⚠️", message, Fore.YELLOW)

    @classmethod
    def show_info(cls, message: str) -> None:
        cls.show_status("ℹ️", message, Fore.BLUE)

    @classmethod
    def show_step(cls, number: int, description: str) -> None:
        print(
            f"{Fore.MAGENTA}{Style.BRIGHT}│ Paso {number}: {description}{Style.RESET_ALL}"
        )

    @classmethod
    def show_parameters(cls, config: Dict) -> None:
        params = config["simulation_params"]
        labels = {
            "Mw": ("Magnitud (Mw)", ""),
            "h": ("Profundidad", " km"),
            "lat0": ("Latitud", "°"),
            "lon0": ("Longitud", "°"),
            "hhmm": ("Hora", " UTC"),
            "dia": ("Día del mes", ""),
        }

        cls.show_section("Parámetros de Simulación")
        for key, (label, unit) in labels.items():
            value = params.get(key, "N/D")
            print(
                f"{Fore.CYAN}│ {label}:{Style.RESET_ALL} {Fore.YELLOW}{value}{unit}{Style.RESET_ALL}"
            )

    @classmethod
    def get_input(cls, prompt: str, default: Optional[str] = None) -> str:
        default_text = f" [{default}]" if default else ""
        response = input(f"{Fore.CYAN}? {prompt}{default_text}: {Style.RESET_ALL}")
        return response or default or ""

    @classmethod
    def get_float(cls, prompt: str, default: float) -> float:
        while True:
            try:
                value = cls.get_input(prompt, str(default))
                return float(value)
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
