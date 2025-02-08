from typing import Optional
from rich.console import Console
from rich.text import Text
import shutil

class ASCIIArt:
    """ASCII art for NeonArc CLI."""
    
    def __init__(self, use_color: bool = True):
        """Initialize ASCII art generator."""
        self.console = Console(color_system="auto" if use_color else None)
        self.term_width = shutil.get_terminal_size().columns

    def get_logo(self, centered: bool = True) -> str:
        """Get NeonArc logo."""
        logo = """
 ███▄    █ ▓█████  ▒█████   ███▄    █  ▄▄▄       ██▀███   ▄████▄  
 ██ ▀█   █ ▓█   ▀ ▒██▒  ██▒ ██ ▀█   █ ▒████▄    ▓██ ▒ ██▒▒██▀ ▀█  
▓██  ▀█ ██▒▒███   ▒██░  ██▒▓██  ▀█ ██▒▒██  ▀█▄  ▓██ ░▄█ ▒▒▓█    ▄ 
▓██▒  ▐▌██▒▒▓█  ▄ ▒██   ██░▓██▒  ▐▌██▒░██▄▄▄▄██ ▒██▀▀█▄  ▒▓▓▄ ▄██▒
▒██░   ▓██░░▒████▒░ ████▓▒░▒██░   ▓██░ ▓█   ▓██▒░██▓ ▒██▒▒ ▓███▀ ░
░ ▒░   ▒ ▒ ░░ ▒░ ░░ ▒░▒░▒░ ░ ▒░   ▒ ▒  ▒▒   ▓▒█░░ ▒▓ ░▒▓░░ ░▒ ▒  ░
░ ░░   ░ ▒░ ░ ░  ░  ░ ▒ ▒░ ░ ░░   ░ ▒░  ▒   ▒▒ ░  ░▒ ░ ▒░  ░  ▒   
   ░   ░ ░    ░   ░ ░ ░ ▒     ░   ░ ░   ░   ▒     ░░   ░ ░        
         ░    ░  ░    ░ ░           ░       ░  ░   ░     ░ ░      
                                                          ░        
"""
        if centered:
            # Center each line based on terminal width
            lines = logo.split('\n')
            max_length = max(len(line) for line in lines)
            padding = max(0, (self.term_width - max_length) // 2)
            logo = '\n'.join(' ' * padding + line for line in lines)
            
        return logo

    def get_small_logo(self) -> str:
        """Get a smaller version of the logo."""
        return """
 ╔═╗  ╔╗     ╔═══╗    ╔═══╗ ╔═══╗ ╔═══╗ ╔═══╗
 ║╔╝ ╔╝╚╗    ║╔══╝    ║╔═╗║ ║╔═╗║ ║╔═╗║ ║╔═╗║
 ║║ ╔╝╔╗╚╗   ║╚══╗    ║║ ║║ ║╚═╝║ ║║ ║║ ║║ ║║
 ║║ ║ ║║ ║   ║╔══╝    ║╚═╝║ ║╔╗╔╝ ║║ ║║ ║║ ║║
 ║╚╗║ ║║ ║   ║╚══╗    ║╔═╗║ ║║║╚╗ ║╚═╝║ ║╚═╝║
 ╚═╝╚═╝╚═╝   ╚═══╝    ╚╝ ╚╝ ╚╝╚═╝ ╚═══╝ ╚═══╝
"""

    def get_banner(self, version: str, colored: bool = True) -> None:
        """Display full application banner."""
        logo = self.get_logo()
        if colored:
            text = Text()
            text.append(logo, style="bold blue")
            text.append(f"\nVersion {version}\n", style="bold cyan")
            self.console.print(text)
        else:
            self.console.print(logo)
            self.console.print(f"Version {version}\n")

    def get_loading_spinner(self) -> str:
        """Get loading spinner frames."""
        return ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def get_success_symbol(self) -> str:
        """Get success symbol."""
        return "✔"

    def get_error_symbol(self) -> str:
        """Get error symbol."""
        return "✘"

    def get_warning_symbol(self) -> str:
        """Get warning symbol."""
        return "⚠"

    def get_processing_art(self) -> list[str]:
        """Get ASCII art frames for processing animation."""
        return [
            """
   _______________
  /              /|
 /              / |
/_______________/  |
|  __________  |  |
|  |        |  |  |
|  |        |  |  |
|  |        |  |  |
|  |________|  | /
|______________|/
""",
            """
   _______________
  /              /|
 /   ________   / |
/___/_      |__/  |
|  __|      |  |  |
|  |        |  |  |
|  |        |  |  |
|  |        |  |  |
|  |________|  | /
|______________|/
""",
            """
   _______________
  /              /|
 /   ________   / |
/___/_      |__/  |
|  __|      |  |  |
|  | |      |  |  |
|  | |      |  |  |
|  | |      |  |  |
|  |_|______|  | /
|______________|/
"""
        ]

    def get_divider(self, char: str = "─", width: Optional[int] = None) -> str:
        """Get a divider line."""
        width = width or self.term_width
        return char * width

    def get_box(self, text: str, width: Optional[int] = None) -> str:
        """Get text in a box."""
        width = width or min(self.term_width - 4, max(len(line) for line in text.split('\n')) + 4)
        lines = text.split('\n')
        
        box = "╔" + "═" * (width - 2) + "╗\n"
        for line in lines:
            padding = " " * (width - 2 - len(line))
            box += f"║ {line}{padding} ║\n"
        box += "╚" + "═" * (width - 2) + "╝"
        
        return box

    def center_text(self, text: str) -> str:
        """Center text based on terminal width."""
        lines = text.split('\n')
        centered_lines = []
        for line in lines:
            padding = max(0, (self.term_width - len(line)) // 2)
            centered_lines.append(" " * padding + line)
        return '\n'.join(centered_lines)

    def get_progress_bar(self, width: Optional[int] = None) -> str:
        """Get ASCII progress bar template."""
        width = width or min(self.term_width - 10, 50)
        return f"[{{:<{width}}}] {{:>3}}%" 