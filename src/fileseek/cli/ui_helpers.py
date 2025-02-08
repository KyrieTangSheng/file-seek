from typing import List, Dict, Optional, Any, Callable
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich import box
import shutil
import os
from pathlib import Path

class UIHelpers:
    """Helper class for CLI user interface elements."""
    
    def __init__(self, use_color: bool = True):
        """Initialize UI helpers."""
        self.console = Console(color_system="auto" if use_color else None)
        self.term_width = shutil.get_terminal_size().columns

    def print_header(self, text: str):
        """Print a formatted header."""
        self.console.print(f"\n[bold blue]{text}[/bold blue]")
        self.console.print("=" * min(len(text), self.term_width))

    def print_error(self, message: str):
        """Print an error message."""
        self.console.print(f"[bold red]Error:[/bold red] {message}")

    def print_warning(self, message: str):
        """Print a warning message."""
        self.console.print(f"[bold yellow]Warning:[/bold yellow] {message}")

    def print_success(self, message: str):
        """Print a success message."""
        self.console.print(f"[bold green]Success:[/bold green] {message}")

    def print_info(self, message: str):
        """Print an info message."""
        self.console.print(f"[bold blue]Info:[/bold blue] {message}")

    def create_progress_bar(self, description: str = "Processing") -> Progress:
        """Create a rich progress bar."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            console=self.console
        )

    def _trim_path(self, path: str, max_width: int) -> str:
        """Trim path from the front, keeping the filename part."""
        if len(path) <= max_width:
            return path
            
        # Split into directory and filename
        path_obj = Path(path)
        filename = path_obj.name
        
        if len(filename) >= max_width - 3:
            # If filename itself is too long, trim it from the front
            return "..." + filename[-(max_width-3):]
            
        # Calculate remaining space for directory
        remaining_width = max_width - len(filename) - 3  # -3 for "..."
        if remaining_width > 0:
            return "..." + str(path_obj.parent)[-remaining_width:] + "/" + filename
        return "..." + filename

    def display_table(self, 
                     headers: List[str], 
                     rows: List[List[str]], 
                     title: Optional[str] = None,
                     column_widths: Optional[Dict[str, int]] = None):
        """Display data in a table format with path trimming."""
        # Filter out "created" column
        if "Created" in headers:
            created_index = headers.index("Created")
            headers = [h for i, h in enumerate(headers) if i != created_index]
            rows = [[col for i, col in enumerate(row) if i != created_index] for row in rows]
        
        # Adjust column widths if needed
        if column_widths and "Created" in column_widths:
            del column_widths["Created"]
        
        table = Table(title=title, box=box.ROUNDED)
        
        # Add columns with optional width constraints
        for header in headers:
            width = column_widths.get(header) if column_widths else None
            table.add_column(header, width=width, overflow="fold")
            
        # Process rows, trimming paths where needed
        for row in rows:
            processed_row = []
            for header, value in zip(headers, row):
                if header in ["Document", "Path", "File"]:  # Column names that contain paths
                    width = column_widths.get(header) if column_widths else None
                    if width:
                        value = self._trim_path(value, width)
                processed_row.append(value)
            table.add_row(*processed_row)
            
        self.console.print(table)

    def prompt_input(self, 
                    message: str, 
                    default: Optional[str] = None, 
                    password: bool = False) -> str:
        """Prompt user for input."""
        return Prompt.ask(
            message,
            default=default,
            password=password,
            console=self.console
        )

    def prompt_confirm(self, 
                      message: str, 
                      default: bool = True) -> bool:
        """Prompt user for confirmation."""
        return Confirm.ask(message, default=default, console=self.console)

    def prompt_choice(self, 
                     message: str, 
                     choices: List[str], 
                     default: Optional[str] = None) -> str:
        """Prompt user to choose from a list of options."""
        if not choices:
            raise ValueError("No choices provided")
            
        # Display choices
        self.console.print(f"\n{message}")
        for i, choice in enumerate(choices, 1):
            self.console.print(f"{i}. {choice}")
        
        while True:
            try:
                response = self.prompt_input(
                    "Enter number",
                    default=str(choices.index(default) + 1) if default else None
                )
                index = int(response) - 1
                if 0 <= index < len(choices):
                    return choices[index]
            except ValueError:
                self.print_error("Please enter a valid number")

    def display_file_preview(self, 
                           file_path: Path, 
                           language: Optional[str] = None,
                           max_lines: int = 20):
        """Display a preview of a file's contents."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = ''.join(f.readlines()[:max_lines])
                
            syntax = Syntax(
                content,
                language or self._guess_language(file_path),
                theme="monokai",
                line_numbers=True,
                word_wrap=True
            )
            
            self.console.print(Panel(
                syntax,
                title=str(file_path),
                subtitle=f"Preview ({max_lines} lines)"
            ))
            
        except Exception as e:
            self.print_error(f"Could not preview file: {e}")

    def display_markdown(self, content: str):
        """Display markdown-formatted content."""
        markdown = Markdown(content)
        self.console.print(markdown)

    def create_processing_progress(self) -> Progress:
        """Create a progress bar specifically for file processing."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("[bold]{task.fields[status]}"),
            console=self.console
        )

    def display_results_summary(self, results: List[Dict]):
        """Display a summary of processing results grouped by file type."""
        # Overall summary
        total = len(results)
        successful = sum(1 for r in results if r.get('status') == 'completed')
        failed = sum(1 for r in results if r.get('status') == 'failed')
        
        # Group by file type
        type_groups = {}
        for result in results:
            if result.get('file_info') and result['file_info'].mime_type:
                mime_type = result['file_info'].mime_type
                if mime_type not in type_groups:
                    type_groups[mime_type] = {'total': 0, 'completed': 0, 'failed': 0}
                
                type_groups[mime_type]['total'] += 1
                if result.get('status') == 'completed':
                    type_groups[mime_type]['completed'] += 1
                elif result.get('status') == 'failed':
                    type_groups[mime_type]['failed'] += 1

        # Display overall summary
        self.print_header("Processing Summary")
        table = Table(box=box.ROUNDED)
        table.add_column("Metric", style="bold blue")
        table.add_column("Count", style="bold")
        
        table.add_row("Total Files", str(total))
        table.add_row("Successful", f"[green]{successful}[/green]")
        table.add_row("Failed", f"[red]{failed}[/red]")
        
        self.console.print(table)
        
        # Display type-specific summary
        if type_groups:
            self.print_header("\nBreakdown by File Type")
            type_table = Table(box=box.ROUNDED)
            type_table.add_column("File Type", style="bold blue")
            type_table.add_column("Total", style="bold")
            type_table.add_column("Successful", style="bold green")
            type_table.add_column("Failed", style="bold red")
            
            for mime_type, stats in sorted(type_groups.items()):
                type_table.add_row(
                    mime_type,
                    str(stats['total']),
                    str(stats['completed']),
                    str(stats['failed'])
                )
            
            self.console.print(type_table)

    def _guess_language(self, file_path: Path) -> str:
        """Guess the programming language based on file extension."""
        extension_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.html': 'html',
            '.css': 'css',
            '.md': 'markdown',
            '.json': 'json',
            '.xml': 'xml',
            '.yaml': 'yaml',
            '.sql': 'sql'
        }
        return extension_map.get(file_path.suffix.lower(), 'text')

    def clear_screen(self):
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def get_terminal_size(self) -> tuple[int, int]:
        """Get terminal dimensions."""
        return shutil.get_terminal_size() 