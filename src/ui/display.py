# =====================================================================================
# Target File: src/ui/display.py
# Source Reference: src/display_handler.py
# =====================================================================================
"""Handles rendering the UI with the `rich` library."""

from typing import Optional
import threading
import time
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from src.ui.provider import DashboardDataProvider
from src.infrastructure.logging_handler import StructuredLogger
import src.ui.formatter as formatter


class DisplayManager:
    """Exclusively handles rendering the UI with the `rich` library, using data
    received from the provider.

    This class is responsible for pure UI rendering without any data fetching or business logic.
    """

    def __init__(self, provider: DashboardDataProvider, logger: StructuredLogger, refresh_rate: int = 2):
        """Initializes the display manager with an injected data provider.

        Args:
            provider (DashboardDataProvider): The data provider for the dashboard.
            logger (StructuredLogger): The logger for recording operations.
            refresh_rate (int, optional): The refresh rate for the display in seconds. Defaults to 2.
        """
        self.provider = provider
        self.logger = logger
        self.console = Console()
        self.layout = self._create_layout()
        self.live: Optional[Live] = None
        self.running = False
        self._update_thread: Optional[threading.Thread] = None
        self._refresh_rate = refresh_rate

    def _create_layout(self) -> Layout:
        """Creates and returns the main layout structure for the dashboard.

        Returns:
            Layout: The main layout structure.
        """
        layout = Layout(name="root")
        layout.split(
            Layout(name="header", size=3),
            Layout(ratio=1, name="main"),
            Layout(size=1, name="footer"),
        )
        layout["main"].split_row(Layout(name="left"), Layout(name="right", ratio=2))
        layout["left"].split(Layout(name="system_stats"), Layout(name="gpu_resources"))
        return layout

    def start(self) -> None:
        """Starts the display update loop in a separate thread."""
        if self.running:
            self.logger.warning("Display manager is already running.")
            return

        self.running = True
        self.live = Live(self.layout, console=self.console, screen=True, auto_refresh=False)
        self.live.start()

        self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self._update_thread.start()
        self.logger.info("Display manager started.")

    def stop(self) -> None:
        """Stops the display update loop and cleans up resources."""
        if not self.running:
            return

        self.running = False
        if self._update_thread:
            self._update_thread.join()

        if self.live:
            self.live.stop()
        self.logger.info("Display manager stopped.")

    def _update_loop(self) -> None:
        """The main update loop that runs in a separate thread."""
        while self.running:
            try:
                self.provider.refresh_all_data()
                self.update_display()
                time.sleep(self._refresh_rate)
            except Exception as e:
                self.logger.error("Error in display update loop", {"error": str(e)})
                time.sleep(5) # Wait longer after an error

    def update_display(self) -> None:
        """Updates the display with fresh data from the provider."""
        # Header
        header_text = Text(f"MQI Communicator Dashboard - Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", justify="center")
        self.layout["header"].update(Panel(header_text, style="bold blue"))

        # System Stats
        stats_data = self.provider.get_system_stats()
        self.layout["system_stats"].update(self._create_system_stats_panel(stats_data))

        # GPU Resources
        gpu_data = self.provider.get_gpu_data()
        self.layout["gpu_resources"].update(self._create_gpu_panel(gpu_data))

        # Active Cases
        cases_data = self.provider.get_active_cases_data()
        self.layout["right"].update(self._create_cases_panel(cases_data))
        
        # Footer
        footer_text = Text(f"Watching for new cases... | Total Active Cases: {stats_data.get('total_cases', 0)} | Available GPUs: {stats_data.get('available_gpus', 0)}/{stats_data.get('total_gpus', 0)}", justify="left")
        self.layout["footer"].update(Panel(footer_text, style="white"))
        
        if self.live:
            self.live.refresh()

    def _create_system_stats_panel(self, stats_data: dict) -> Panel:
        """Creates a panel for system statistics.

        Args:
            stats_data (dict): A dictionary of system statistics.

        Returns:
            Panel: A `rich` Panel object.
        """
        table = Table(show_header=False, expand=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        
        stats = {
            "Total Active": stats_data.get('total_cases', 0),
            "Pending": stats_data.get('pending', 0),
            "Preprocessing": stats_data.get('preprocessing', 0),
            "Processing": stats_data.get('processing', 0),
            "Postprocessing": stats_data.get('postprocessing', 0),
        }
        for key, value in stats.items():
            table.add_row(key, str(value))

        return Panel(table, title="[bold]System Status[/bold]", border_style="green")

    def _create_gpu_panel(self, gpu_data: list) -> Panel:
        """Creates a panel for GPU resources.

        Args:
            gpu_data (list): A list of GPU resource data.

        Returns:
            Panel: A `rich` Panel object.
        """
        table = Table(expand=True)
        table.add_column("ID", style="dim", width=5)
        table.add_column("Name", style="cyan")
        table.add_column("Status", style="white")
        table.add_column("Mem (Used/Total)", style="white")
        table.add_column("Util", style="white")
        table.add_column("Temp", style="white")

        for gpu in gpu_data:
            table.add_row(
                gpu['uuid'][-4:],
                gpu['name'],
                formatter.get_gpu_status_text(gpu['status']),
                formatter.format_memory_usage(gpu['memory_used'], gpu['memory_total']),
                formatter.format_utilization(gpu['utilization']),
                formatter.format_temperature(gpu['temperature'])
            )
        return Panel(table, title="[bold]GPU Resources[/bold]", border_style="green")

    def _create_cases_panel(self, cases_data: list) -> Panel:
        """Creates a panel for active cases.

        Args:
            cases_data (list): A list of active case data.

        Returns:
            Panel: A `rich` Panel object.
        """
        table = Table(expand=True)
        table.add_column("Case ID", style="cyan", no_wrap=True)
        table.add_column("Status", style="white")
        table.add_column("Progress", style="white", width=28)
        table.add_column("GPU", style="dim")
        table.add_column("Elapsed", style="dim")

        for case in cases_data:
            table.add_row(
                case['case_id'],
                formatter.get_case_status_text(case['status']),
                formatter.format_progress_bar(case['progress']),
                case['assigned_gpu'][-4:] if case['assigned_gpu'] else "N/A",
                formatter.format_elapsed_time(case['elapsed_time'])
            )
        return Panel(table, title="[bold]Active Cases[/bold]", border_style="magenta")