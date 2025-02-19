import asyncio
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

console = Console()


class RichUI:
    @staticmethod
    def print_header():
        console.print(
            Panel("🌊 CLIENTE DE SIMULACIÓN TSUNAMI [v1.0]", style="bold cyan")
        )

    @staticmethod
    def show_error(message: str):
        console.print(f"[bold red]❌ {message}[/bold red]")

    @staticmethod
    def show_success(message: str):
        console.print(f"[bold green]✅ {message}[/bold green]")

    @staticmethod
    def show_info(message: str):
        console.print(f"[bold cyan]{message}[/bold cyan]")

    @staticmethod
    def show_parameters_box(config: dict):
        params = config.get("simulation_params", {})
        lines = [
            f"Magnitud (Mw)    : {params.get('Mw', 'N/D')}",
            f"Profundidad (km) : {params.get('h', 'N/D')}",
            f"Latitud          : {params.get('lat0', 'N/D')}°",
            f"Longitud         : {params.get('lon0', 'N/D')}°",
            f"Hora (UTC)       : {params.get('hhmm', 'N/D')}",
            f"Día del mes      : {params.get('dia', 'N/D')}",
        ]
        content = "\n".join(lines)
        console.print(Panel(content, title="Parámetros de simulación", style="cyan"))

    @staticmethod
    def prompt_yes_no(prompt_text: str) -> bool:
        return Confirm.ask(prompt_text, default=False)

    @staticmethod
    def prompt_input(prompt_text: str, default: str = "") -> str:
        return Prompt.ask(prompt_text, default=default)

    @staticmethod
    def prompt_float(prompt_text: str, default: float) -> float:
        while True:
            response = Prompt.ask(prompt_text, default=str(default))
            try:
                return float(response)
            except ValueError:
                RichUI.show_error("Por favor ingrese un número válido.")

    @staticmethod
    def prompt_time(prompt_text: str, default: str) -> str:
        while True:
            response = Prompt.ask(prompt_text, default=default)
            if len(response) == 4 and response.isdigit():
                return response
            RichUI.show_error("El formato debe ser HHMM (4 dígitos).")

    @staticmethod
    def prompt_day(prompt_text: str, default: str) -> str:
        while True:
            response = Prompt.ask(prompt_text, default=default)
            if response.isdigit() and 1 <= int(response) <= 31:
                return response
            RichUI.show_error("El día debe estar entre 1 y 31.")

    @staticmethod
    def show_analysis_start(timestamp: str):
        console.print(
            Panel(f"🚀 El análisis ha comenzado [{timestamp}]", style="bold green")
        )

    @staticmethod
    def show_simulation_step(
        current: int, total: int, description: str, duration: float
    ):
        console.print(
            f"[bold cyan][{current}/{total}] {description}... ({duration:.1f}s)[/bold cyan]"
        )


class InteractiveMonitor:
    """
    Implementa la interfaz interactiva con un layout de cuatro zonas:
      - Header: Estado general de la simulación.
      - Monitor: Estado y duración, con cuenta regresiva.
      - Output: Resultados temporales o ayuda contextual.
      - Input: Comando actual.
    """

    def __init__(self, simulation_id: str, start_time: float):
        self.simulation_id = simulation_id
        self.start_time = start_time
        self.status = "PROCESANDO"
        self.latest_event = "Esperando actualización..."
        self.progress = 0.0
        self.elapsed = "00:00:00"
        self.countdown = 0
        self.help_visible = False
        self.command = ""
        self.exit_requested = False
        self.running = False

        self.layout = Layout()
        self.create_layout()

    def create_layout(self):
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="monitor", size=4),
            Layout(name="output", size=8),
            Layout(name="input", size=3),
        )

    def update_header(self):
        header_text = (
            f"🌊 Orchestrator-TSDHN CLI [v1.0]\nSimulación ID: {self.simulation_id}"
        )
        self.layout["header"].update(Panel(header_text, style="bold cyan"))

    def update_monitor(self):
        now = datetime.now().strftime("%H:%M:%S")
        monitor_text = (
            f"🔍 Monitoreo activo [{now}]\n"
            f"ESTADO: {self.status} | DURACIÓN: {self.elapsed}\n"
            f"ÚLTIMO EVENTO: {self.latest_event}\n"
            f"Próxima actualización en: {self.countdown:2d} s"
        )
        self.layout["monitor"].update(Panel(monitor_text, style="magenta"))

    def update_output(self):
        if self.help_visible:
            help_text = (
                "🛠 Comandos disponibles durante monitoreo:\n"
                "  ver [1-3]     Mostrar resultados de paso específico\n"
                "  log           Ver registro detallado de ejecución\n"
                "  alertas       Listar alertas activas\n"
                "  salir         Volver al menú principal"
            )
            self.layout["output"].update(Panel(help_text, title="Ayuda", style="green"))
        elif self.command:
            result_text = f"Mostrando resultados para: [bold]{self.command}[/bold]\n"
            result_text += "(Presione Enter para continuar...)"
            self.layout["output"].update(
                Panel(result_text, title="Resultados", style="blue")
            )
        else:
            self.layout["output"].update(Panel("Esperando comando...", style="dim"))

    def update_input(self):
        input_text = f"Comando › {self.command}"
        self.layout["input"].update(Panel(input_text, style="bold yellow"))

    def refresh(self):
        self.update_header()
        self.update_monitor()
        self.update_output()
        self.update_input()

    async def input_listener(self):
        while self.running:
            cmd = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("Comando › ")
            )
            cmd = cmd.strip().lower()
            if cmd == "f1":
                self.help_visible = not self.help_visible
            elif cmd == "salir":
                self.exit_requested = True
            elif cmd:
                self.command = cmd
                self.latest_event = f"Ejecutado comando: {self.command}"
                await asyncio.sleep(2)
                self.command = ""
            await asyncio.sleep(0.1)

    async def run(self):
        self.running = True
        asyncio.create_task(self.input_listener())
        from rich.live import Live

        with Live(self.layout, refresh_per_second=4, screen=True):
            while self.running and not self.exit_requested:
                self.elapsed = str(
                    datetime.now() - datetime.fromtimestamp(self.start_time)
                ).split(".")[0]
                self.refresh()
                await asyncio.sleep(0.25)
