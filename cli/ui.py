from colorama import Fore, Style


class UserInterface:
    @staticmethod
    def show_section(title: str, color=Fore.CYAN) -> None:
        border = "-" * (len(title) + 10)
        print(f"\n{color}{Style.BRIGHT}{border}")
        print(f"{' ' * 5}{title}{' ' * 5}")
        print(f"{border}{Style.RESET_ALL}")

    @staticmethod
    def show_status(icon: str, message: str, color=Fore.WHITE) -> None:
        print(f"{color}{Style.BRIGHT}{icon} {message}{Style.RESET_ALL}")

    @staticmethod
    def show_success(message: str) -> None:
        UserInterface.show_status("✅", message, Fore.GREEN)

    @staticmethod
    def show_error(message: str) -> None:
        UserInterface.show_status("❌", message, Fore.RED)

    @staticmethod
    def show_warning(message: str) -> None:
        UserInterface.show_status("⚠️", message, Fore.YELLOW)

    @staticmethod
    def show_info(*messages: str) -> None:
        for msg in messages:
            UserInterface.show_status("🔔", msg, Fore.BLUE)

    @staticmethod
    def show_step(number: int, description: str) -> None:
        print(f"{Fore.MAGENTA}{Style.BRIGHT}[{number}] {description}{Style.RESET_ALL}")

    @staticmethod
    def show_parameters(config: dict) -> None:
        print(f"{Fore.CYAN}Parámetros:{Style.RESET_ALL}")
        params = config["simulation_params"]
        labels = {
            "Mw": "Magnitud (Mw)",
            "h": "Profundidad (h)",
            "lat0": "Latitud",
            "lon0": "Longitud",
            "hhmm": "Hora (HHMM)",
            "dia": "Día",
        }
        for key, label in labels.items():
            value = params.get(key, "N/A")
            unit = " km" if key == "h" else "°" if key in ["lat0", "lon0"] else ""
            print(f"  • {label}: {Fore.YELLOW}{value}{unit}{Style.RESET_ALL}")

    @staticmethod
    def progress_bar(percentage: float, width: int = 50) -> None:
        filled = int(width * percentage / 100)
        bar = f"[{Fore.GREEN}{'█' * filled}{Style.RESET_ALL}{'░' * (width - filled)}]"
        print(f"\r{bar} {percentage:.1f}%", end="", flush=True)
