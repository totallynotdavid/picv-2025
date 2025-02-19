from rich.console import Console

console = Console()


class SimpleUI:
    @staticmethod
    def print_header():
        console.clear()
        console.print("┌  ✨ Bienvenido al CLI de Orchestrator-TSDHN ✨")
        console.print("│")

    @staticmethod
    def show_info(message: str):
        if message.strip() == "":
            console.print("│")
        else:
            console.print(f"│  {message}")

    @staticmethod
    def show_success(message: str):
        console.print(f"◇  {message}")

    @staticmethod
    def show_error(message: str):
        console.print(f"■  Error: {message}")

    @staticmethod
    def show_question(message: str):
        console.print(f"◇  {message}", style="blue")

    @staticmethod
    def print_exit():
        console.print("└  Saliendo - ¡hasta luego! 👋")
