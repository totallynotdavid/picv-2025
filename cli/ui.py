from rich.console import Console

console = Console()


class SimpleUI:
    @staticmethod
    def print_header():
        console.clear()
        console.print("┌  ✨ Bienvenido al CLI de Orchestrator-TSDHN ✨")
        console.print("│")

    @staticmethod
    def show_info(message: str, add_separator: bool = False):
        if not message.strip():
            console.print("│")
        else:
            console.print(f"│  {message}")
        if add_separator:
            console.print("│")

    @staticmethod
    def show_success(message: str, add_separator: bool = True):
        console.print(f"◇  {message}")
        if add_separator:
            console.print("│")

    @staticmethod
    def show_error(message: str, add_separator: bool = True):
        console.print(f"■  Error: {message}")
        if add_separator:
            console.print("│")

    @staticmethod
    def prompt(prompt_text: str) -> str:
        user_input = input(f"◇  {prompt_text}")
        console.print("│")
        return user_input.strip()

    @staticmethod
    def show_question(message: str):
        console.print(f"◇  {message}", style="blue")

    @staticmethod
    def print_exit():
        console.print("└  Saliendo - ¡hasta luego! 👋")
