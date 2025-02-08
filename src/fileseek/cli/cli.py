from typing import Optional, List, Dict
import click
from pathlib import Path
import logging
from datetime import datetime
import time
import logging.handlers
import sys
import platform
from importlib.metadata import version

from fileseek.core.archivist import Archivist
from fileseek.core.config import ConfigManager
from fileseek.cli.ui_helpers import UIHelpers
from fileseek.cli.ascii_art import ASCIIArt
from fileseek.pipeline.file_detector import FileDetector
from fileseek.watchers.watchers import WatchManager, FileWatcher, WatcherEvent
from fileseek.core.system_deps import DependencyChecker

try:
    __version__ = version("fileseek")
except ImportError:
    __version__ = "unknown"

class FileSeekCLI:
    """FileSeek Command Line Interface."""
    
    def __init__(self):
        """Initialize CLI."""
        self.ui = UIHelpers()
        self.ascii = ASCIIArt()
        self.config = ConfigManager()
        self.archivist = None

    def initialize(self, config_path: Optional[str] = None):
        """Initialize the system."""
        try:
            # Display banner with version from package
            self.ascii.get_banner(__version__)
            
            # Initialize archivist
            self.archivist = Archivist(config_path)
            self.ui.print_success("System initialized successfully")
            
        except Exception as e:
            self.ui.print_error(f"Initialization failed: {e}")
            raise click.Abort()

# Create a UI helper instance
ui = UIHelpers()

@click.group()
@click.option('--config', '-c', type=click.Path(exists=True), help='Path to config file')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.version_option(version=__version__, prog_name="FileSeek")
@click.pass_context
def cli(ctx, config: Optional[str], verbose: bool):
    """FileSeek - Document Processing and Search System"""
    # Create CLI instance
    cli_instance = FileSeekCLI()
    ctx.obj = cli_instance
    
    # Check system dependencies
    checker = DependencyChecker()
    if not checker.check_dependencies(cli_instance.ui):
        raise click.Abort()
    
    # Initialize system with logging
    cli_instance.config.setup_logging(verbose)
    cli_instance.initialize(config)

@cli.command()
@click.argument('paths', nargs=-1, type=click.Path(exists=True))
@click.option('--recursive', '-r', is_flag=True, help='Process directories recursively')
@click.option('--dry-run', is_flag=True, help='Show which files would be processed without actually processing them')
@click.pass_obj
def process(cli: FileSeekCLI, paths: List[str], recursive: bool, dry_run: bool):
    """Process documents and add them to the archive."""
    try:
        file_detector = FileDetector()
        files_to_process = []
        
        # Get all files in target directories
        current_files = set()
        for path in paths:
            path = Path(path)
            if path.is_file():
                if file_detector.should_process_file(path):
                    current_files.add(path)
                    files_to_process.append(path)
            elif path.is_dir():
                glob_pattern = "**/*" if recursive else "*"
                for file_path in path.glob(glob_pattern):
                    if file_path.is_file() and file_detector.should_process_file(file_path):
                        current_files.add(file_path)
                        files_to_process.append(file_path)
                        
        # Get previously ingested files in these directories
        previous_files = set()
        for path in paths:
            path = Path(path)
            base_path = path if path.is_dir() else path.parent
            docs = cli.archivist.get_documents_in_directory(base_path, recursive)
            previous_files.update(Path(doc['path']) for doc in docs)
        
        # Find deleted files
        deleted_files = previous_files - current_files
        
        if not files_to_process and not deleted_files:
            cli.ui.print_warning("No changes detected")
            return
            
        # Show what would be processed
        if deleted_files:
            cli.ui.print_info(f"Found {len(deleted_files)} files to remove:")
            # for file in deleted_files:
            #     cli.ui.print_info(f"  - {file} (deleted)")
                
        if files_to_process:
            cli.ui.print_info(f"Found {len(files_to_process)} files to process:")
            # for file in files_to_process:
            #     cli.ui.print_info(f"  - {file}")
        
        if dry_run:
            return
            
        # Remove deleted files
        if deleted_files:
            with cli.ui.create_progress_bar() as progress:
                task = progress.add_task("Removing deleted files...", total=len(deleted_files))
                for file in deleted_files:
                    cli.archivist.remove_document(file)
                    progress.advance(task)
        
        # Process new/modified files
        if files_to_process:
            with cli.ui.create_progress_bar() as progress:
                task = progress.add_task("Processing files...", total=len(files_to_process))
                for file in files_to_process:
                    cli.archivist.ingest_file(file)
                    progress.advance(task)
                    
    except Exception as e:
        cli.ui.print_error(f"Processing failed: {e}")
        raise click.Abort()

@cli.command()
@click.argument('query')
@click.option('--limit', '-l', type=int, default=5, help='Maximum number of results')
@click.option('--context', '-c', is_flag=True, help='Show document context')
@click.pass_obj
def search(cli: FileSeekCLI, query: str, limit: int, context: bool):
    """Search the archive."""
    try:
        results = cli.archivist.search(query, limit=limit)
        
        if not results:
            cli.ui.print_warning("No results found")
            return
        
        # Display results
        headers = ["ID", "Score", "Document", "Content"]
        rows = []
        
        # Calculate reasonable content width based on terminal size
        term_width = cli.ui.console.width
        id_width = 4
        score_width = 6
        content_width = min(100, term_width // 3)  # Limit content to 1/3 of terminal width
        doc_width = term_width - (id_width + score_width + content_width + 10)  # Account for padding
        
        def trim_path(path: str, max_width: int) -> str:
            """Trim path from the front, keeping the end part."""
            if len(path) <= max_width:
                return path
            return "..." + path[-(max_width-3):]
        
        for result in results:
            content = result.chunk_text
            if len(content) > content_width:
                content = content[:content_width-3] + "..."
                
            doc_path = str(result.document_path)
            doc_path = trim_path(doc_path, doc_width)
                
            rows.append([
                str(result.document_id),
                f"{result.score:.2f}",
                doc_path,
                content
            ])
        
        cli.ui.display_table(
            headers, 
            rows, 
            title="Search Results",
            column_widths={
                "ID": id_width,
                "Score": score_width,
                "Document": doc_width,
                "Content": content_width
            }
        )
        
        # Show context if requested
        if context:
            for result in results:
                cli.ui.print_header(f"Context for {result.document_path}")
                context_chunks = cli.archivist.get_document_context(
                    result.document_id,
                    result.chunk_id
                )
                for chunk in context_chunks:
                    cli.ui.display_markdown(chunk)
                
    except Exception as e:
        cli.ui.print_error(f"Search failed: {e}")
        raise click.Abort()

@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('-n', '--num-results', default=5, help='Number of results to return')
@click.pass_obj
def similar(cli: FileSeekCLI, file_path: str, num_results: int):
    """Find similar documents to the given file."""
    try:
        # Get document ID from path
        file_path = Path(file_path).absolute()
        doc = cli.archivist.db_manager.get_document_by_path(str(file_path))
        
        if not doc:
            cli.ui.print_error(f"File not found in archive: {file_path}")
            cli.ui.print_info("Try processing the file first using 'fileseek process'")
            return
        
        # Search for similar documents
        results = cli.archivist.get_similar(doc['id'], limit=num_results)
        
        if not results:
            cli.ui.print_warning("No similar documents found")
            return
            
        # Display results using the same format as search
        headers = ["ID", "Score", "Document", "Content"]
        rows = []
        
        # Calculate reasonable content width based on terminal size
        term_width = cli.ui.console.width
        id_width = 4
        score_width = 6
        content_width = min(100, term_width // 3)
        doc_width = term_width - (id_width + score_width + content_width + 10)
        
        for result in results:
            content = result.chunk_text
            if len(content) > content_width:
                content = content[:content_width-3] + "..."
                
            doc_path = str(result.document_path)
            doc_path = cli.ui._trim_path(doc_path, doc_width)
                
            rows.append([
                str(result.document_id),
                f"{result.score:.2f}",
                doc_path,
                content
            ])
            
        cli.ui.display_table(
            headers,
            rows,
            title="Similar Documents",
            column_widths={
                "ID": id_width,
                "Score": score_width,
                "Document": doc_width,
                "Content": content_width
            }
        )
        
    except Exception as e:
        cli.ui.print_error(f"Error finding similar documents: {e}")
        raise click.Abort()

@cli.command()
@click.pass_obj
def status(cli: FileSeekCLI):
    """Show system status."""
    try:
        status = cli.archivist.get_status()
        
        # Display component status
        headers = ["Component", "Status", "Details"]
        rows = []
        
        for component, details in status.items():
            rows.append([
                component,
                "✓" if details.get('available', True) else "✗",
                str(details)
            ])
        
        cli.ui.display_table(
            headers,
            rows,
            title="System Status"
        )
        
    except Exception as e:
        cli.ui.print_error(f"Status check failed: {e}")
        raise click.Abort()

@cli.command()
@click.option('--export-path', '-e', type=click.Path(), help='Export configuration to file')
@click.pass_obj
def config(cli: FileSeekCLI, export_path: Optional[str]):
    """Show or export configuration."""
    try:
        if export_path:
            cli.config.export_config(export_path)
            cli.ui.print_success(f"Configuration exported to {export_path}")
        else:
            # Display current configuration
            config_dict = cli.config.to_dict()
            
            for section, values in config_dict.items():
                cli.ui.print_header(section)
                for key, value in values.items():
                    cli.ui.console.print(f"{key}: {value}")
                
    except Exception as e:
        cli.ui.print_error(f"Configuration operation failed: {e}")
        raise click.Abort()

@cli.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--recursive', '-r', is_flag=True, help='Validate directory recursively')
@click.pass_obj
def validate(cli: FileSeekCLI, path: str, recursive: bool):
    """Validate processing results for a path."""
    try:
        path = Path(path).absolute()
        paths_to_validate = []
        
        # Collect paths
        if path.is_file():
            paths_to_validate.append(path)
        elif path.is_dir():
            glob_pattern = "**/*" if recursive else "*"
            paths_to_validate.extend([p for p in path.glob(glob_pattern) if p.is_file()])
            
        if not paths_to_validate:
            cli.ui.print_warning("No files found to validate")
            return
            
        cli.ui.print_info(f"Found {len(paths_to_validate)} files to validate")
        
        # Track statistics
        total_docs = 0
        total_chunks = 0
        
        # Check database records
        file_detector = FileDetector()
        cli.ui.print_info("\n=== Database Records ===")
        for file_path in paths_to_validate:
            doc = cli.archivist.db_manager.get_document_by_path(str(file_path))
            if doc and file_detector.should_process_file(file_path):
                total_docs += 1
                embeddings = cli.archivist.db_manager.get_document_embeddings(doc['id'])
                total_chunks += len(embeddings)
                cli.ui.print_info(f"\nDocument: {file_path}")
                cli.ui.print_info(f"  ID: {doc['id']}")
                cli.ui.print_info(f"  Chunks: {len(embeddings)}")
                if embeddings:
                    cli.ui.print_info("  Sample first chunk:")
                    cli.ui.print_info(f"    Text: {embeddings[0]['chunk_text'][:100]}...")
            else:
                cli.ui.print_warning(f"No record found: {file_path}")
                
        # Show summary
        cli.ui.print_info("\n=== Summary ===")
        cli.ui.print_info(f"Total files checked: {len(paths_to_validate)}")
        cli.ui.print_info(f"Files found in database: {total_docs}")
        cli.ui.print_info(f"Total chunks: {total_chunks}")
        
        # Check vector store
        cli.ui.print_info("\n=== Vector Store Status ===")
        total_vectors = cli.archivist.vector_store.index.ntotal
        cli.ui.print_info(f"Total vectors in store: {total_vectors}")
        
        # Verify vector count matches chunk count
        if total_vectors != total_chunks:
            cli.ui.print_warning(
                f"Vector count mismatch: {total_vectors} vectors vs {total_chunks} chunks"
            )
        else:
            cli.ui.print_success("Vector count matches chunk count")
            
    except Exception as e:
        cli.ui.print_error(f"Validation failed: {e}")
        raise click.Abort()

@cli.command()
@click.option('--sort', '-s', type=click.Choice(['date', 'name', 'chunks']), default='date', 
              help='Sort by date, name or chunk count')
@click.option('--reverse', '-r', is_flag=True, help='Reverse sort order')
@click.pass_obj
def list(cli: FileSeekCLI, sort: str, reverse: bool):
    """List all documents in the archive."""
    try:
        # Get all documents
        docs = cli.archivist.db_manager.get_all_documents()
        
        if not docs:
            cli.ui.print_warning("No documents found in archive")
            return
            
        # Enhance document info with chunk counts
        enhanced_docs = []
        for doc in docs:
            chunks = cli.archivist.db_manager.get_document_embeddings(doc['id'])
            enhanced_docs.append({
                **doc,
                'chunk_count': len(chunks)
            })
            
        # Sort documents
        if sort == 'date':
            enhanced_docs.sort(key=lambda x: x['created_at'], reverse=not reverse)
        elif sort == 'name':
            enhanced_docs.sort(key=lambda x: Path(x['path']).name, reverse=reverse)
        else:  # chunks
            enhanced_docs.sort(key=lambda x: x['chunk_count'], reverse=not reverse)
            
        # Display results
        headers = ["ID", "Document", "Created", "Chunks"]
        rows = []
        
        for doc in enhanced_docs:
            created = datetime.fromisoformat(doc['created_at']).strftime('%Y-%m-%d %H:%M')
            rows.append([
                str(doc['id']),
                str(doc['path']),
                created,
                str(doc['chunk_count'])
            ])
            
        cli.ui.display_table(
            headers,
            rows,
            title="Archived Documents"
        )
        
        # Show summary
        cli.ui.print_info(f"\nTotal documents: {len(enhanced_docs)}")
        total_chunks = sum(doc['chunk_count'] for doc in enhanced_docs)
        cli.ui.print_info(f"Total chunks: {total_chunks}")
        
    except Exception as e:
        cli.ui.print_error(f"List operation failed: {e}")
        raise click.Abort()

@cli.command()
@click.argument('paths', nargs=-1, type=click.Path(exists=True))
@click.option('--recursive', '-r', is_flag=True, help='Watch directories recursively')
@click.option('--patterns', '-p', multiple=True, help='File patterns to watch (e.g. *.pdf)')
@click.pass_obj
def watch(cli: FileSeekCLI, paths: List[str], recursive: bool, patterns: List[str]):
    """Watch directories for changes and process new/modified files."""
    try:
        if not paths:
            cli.ui.print_error("No paths specified")
            return
        
        file_detector = FileDetector()
        def handle_event(event: WatcherEvent):
            """Handle file system events."""
            try:
                if event.event_type in ['created', 'modified']:
                    # Skip if path is a directory
                    if event.is_directory:
                        return
                    # Skip if file matches excluded patterns
                    if any(event.path.match(pattern) for pattern in cli.config.get('processing.excluded_patterns', [])):
                        return
                    
                    # Validate file using FileDetector
                    if not file_detector.should_process_file(event.path):
                        return
                    
                    cli.ui.print_info(f"Processing changed file: {event.path}")
                    cli.archivist.ingest_file(event.path)
                    
                elif event.event_type == 'deleted':
                    if event.is_directory:
                        return
                    cli.ui.print_info(f"Removing deleted file from archive: {event.path}")
                    cli.archivist.remove_document(event.path)
                
            except Exception as e:
                cli.ui.print_error(f"Event handling failed: {e}")
        
        # Create watch manager
        watch_manager = WatchManager()
        
        # Get excluded patterns from config with correct path
        excluded_patterns = cli.config.get('processing.excluded_patterns', [])
        
        # Add watcher with paths and callback
        watch_manager.add_watcher(
            name='default',
            paths=paths,
            callback=handle_event,
            patterns=patterns if patterns else None,
            ignore_patterns=excluded_patterns,
            recursive=recursive
        )
        
        # Start watching
        try:
            watch_manager.start()
            cli.ui.print_info("Watching for changes (Press Ctrl+C to stop)...")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            cli.ui.print_info("\nStopping file watcher...")
            watch_manager.stop()
            
    except Exception as e:
        cli.ui.print_error(f"Watch failed: {e}")
        raise click.Abort()

@cli.command()
def version():
    """Show detailed version information"""
    click.echo(f"""
FileSeek Version Information:
----------------------------
Version: {__version__}
Python: {sys.version.split()[0]}
Platform: {platform.platform()}
    """)

def main():
    """Main entry point for the CLI."""
    try:
        cli(obj=None)
    except Exception as e:
        logging.error(f"Unhandled error: {e}")
        raise click.Abort()

if __name__ == '__main__':
    main() 