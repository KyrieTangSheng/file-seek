from typing import Dict, List, Optional, Union
import shutil
import platform
import subprocess
from pathlib import Path
import logging

class SystemDependency:
    def __init__(self, 
                 name: str, 
                 check_cmd: Union[str, List[str]], 
                 packages: Dict[str, List[str]]):
        self.name = name
        self.check_cmd = check_cmd if isinstance(check_cmd, list) else [check_cmd]
        self.packages = packages
        
class DependencyChecker:
    """Check and validate system dependencies."""
    
    def __init__(self):
        self.os = self._get_os()
        self.dependencies = [
            SystemDependency(
                name="Tesseract",
                check_cmd="tesseract --version",
                packages={
                    "ubuntu": ["tesseract-ocr"],
                    "fedora": ["tesseract"],
                    "macos": ["tesseract"],
                    "windows": ["tesseract-ocr"]
                }
            ),
            SystemDependency(
                name="Poppler",
                check_cmd=[
                    "pdftoppm -version",
                    "pdftoppm --version",
                    "pdftocairo -v",
                    "pdfinfo -v"
                ],
                packages={
                    "ubuntu": ["poppler-utils"],
                    "fedora": ["poppler-utils"],
                    "macos": ["poppler"],
                    "windows": ["poppler"]
                }
            ),
            SystemDependency(
                name="libmagic",
                check_cmd="file --version",
                packages={
                    "ubuntu": ["libmagic1"],
                    "fedora": ["file-libs"],
                    "macos": ["libmagic"],
                    "windows": ["libmagic"]
                }
            )
        ]

    def _get_os(self) -> str:
        """Detect operating system."""
        system = platform.system().lower()
        if system == "linux":
            # Check common distributions
            try:
                with open("/etc/os-release") as f:
                    content = f.read().lower()
                    if "ubuntu" in content:
                        return "ubuntu"
                    elif "fedora" in content:
                        return "fedora"
            except FileNotFoundError:
                pass
            return "linux"
        elif system == "darwin":
            return "macos"
        elif system == "windows":
            return "windows"
        return "unknown"

    def _check_dependency(self, dep: SystemDependency) -> bool:
        """Check if a dependency is installed."""
        for cmd in dep.check_cmd:
            try:
                # First check if the binary exists
                binary = cmd.split()[0]
                if shutil.which(binary) is None:
                    logging.debug(f"Binary {binary} not found in PATH")
                    continue
                
                # Try running the version check
                result = subprocess.run(
                    cmd.split(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True
                )
                logging.debug(f"Successfully ran {cmd}")
                return True
            except subprocess.SubprocessError as e:
                logging.debug(f"Failed to run {cmd}: {e}")
            except FileNotFoundError as e:
                logging.debug(f"File not found for {cmd}: {e}")
            except Exception as e:
                logging.debug(f"Unexpected error checking {cmd}: {e}")
        return False

    def get_install_command(self, dep: SystemDependency) -> Optional[str]:
        """Get installation command for the current OS."""
        if self.os not in dep.packages:
            return None
            
        packages = dep.packages[self.os]
        if self.os == "ubuntu":
            return f"sudo apt-get install {' '.join(packages)}"
        elif self.os == "fedora":
            return f"sudo dnf install {' '.join(packages)}"
        elif self.os == "macos":
            return f"brew install {' '.join(packages)}"
        elif self.os == "windows":
            return f"choco install {' '.join(packages)}"
        return None

    def check_dependencies(self, ui) -> bool:
        """Check all dependencies and show installation instructions."""
        all_installed = True
        missing_deps = []

        for dep in self.dependencies:
            if not self._check_dependency(dep):
                all_installed = False
                missing_deps.append(dep)

        if not all_installed:
            ui.print_error("\nMissing system dependencies:")
            for dep in missing_deps:
                ui.print_error(f"\n{dep.name} is not installed")
                install_cmd = self.get_install_command(dep)
                if install_cmd:
                    ui.print_info(f"To install on {self.os}, run:")
                    ui.print_info(f"  {install_cmd}")
                else:
                    ui.print_info(f"Please install {dep.name} for your operating system")

            if self.os == "windows":
                ui.print_info("\nOn Windows, you may need to:")
                ui.print_info("1. Install Chocolatey package manager first")
                ui.print_info("2. Run commands in an administrator PowerShell")
            
            return False
        return True 