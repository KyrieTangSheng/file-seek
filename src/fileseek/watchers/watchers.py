from typing import List, Dict, Set, Optional, Callable, Union
from pathlib import Path
import time
import logging
from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileCreatedEvent,
    FileModifiedEvent,
    FileDeletedEvent
)
from threading import Lock, Event
from queue import Queue
import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from fileseek.pipeline.file_detector import FileDetector

@dataclass
class WatcherEvent:
    """Represents a file system event."""
    event_type: str
    path: Path
    timestamp: datetime
    is_directory: bool

class EventBuffer:
    """Buffers and deduplicates file system events."""
    
    def __init__(self, debounce_seconds: float = 2.0):
        """Initialize event buffer."""
        self.events: Dict[Path, WatcherEvent] = {}
        self.lock = Lock()
        self.debounce_seconds = debounce_seconds
        self.last_processed = datetime.now()

    def add_event(self, event: WatcherEvent):
        """Add event to buffer."""
        with self.lock:
            existing = self.events.get(event.path)
            if not existing or existing.timestamp < event.timestamp:
                self.events[event.path] = event

    def get_events(self) -> List[WatcherEvent]:
        """Get and clear buffered events."""
        now = datetime.now()
        if now - self.last_processed < timedelta(seconds=self.debounce_seconds):
            return []
            
        with self.lock:
            events = list(self.events.values())
            self.events.clear()
            self.last_processed = now
            return events

class FileWatcher(FileSystemEventHandler):
    """Watches directories for file changes."""
    
    def __init__(self,
                 callback: Callable[[WatcherEvent], None],
                 patterns: Optional[List[str]] = None,
                 ignore_patterns: Optional[List[str]] = None,
                 ignore_directories: bool = True,
                 case_sensitive: bool = True):
        """Initialize file watcher."""
        super().__init__()
        self.callback = callback
        self.patterns = patterns
        self.ignore_patterns = ignore_patterns or []
        self.ignore_directories = ignore_directories
        self.case_sensitive = case_sensitive
        
        self.observer = Observer()
        self.watch_paths: Set[Path] = set()
        self.event_buffer = EventBuffer()
        self.running = Event()
        self.processing_queue: Queue = Queue()
        self.file_detector = FileDetector()

    def start(self):
        """Start watching."""
        if not self.watch_paths:
            raise ValueError("No paths to watch")
            
        self.running.set()
        self.observer.start()
        
        # Start event processing
        self._process_events()
        
        logging.info("File watcher started")

    def stop(self):
        """Stop watching."""
        self.running.clear()
        self.observer.stop()
        self.observer.join()
        logging.info("File watcher stopped")

    def add_watch(self, path: Union[str, Path], recursive: bool = True):
        """Add a directory to watch."""
        path = Path(path)
        if not path.exists():
            raise ValueError(f"Path does not exist: {path}")
            
        if not path.is_dir():
            raise ValueError(f"Path is not a directory: {path}")
            
        self.watch_paths.add(path)
        self.observer.schedule(self, str(path), recursive=recursive)
        logging.info(f"Added watch for {path}")

    def remove_watch(self, path: Union[str, Path]):
        """Remove a watched directory."""
        path = Path(path)
        if path in self.watch_paths:
            self.watch_paths.remove(path)
            for watch in self.observer.watches.copy():
                if Path(watch.path) == path:
                    self.observer.unschedule(watch)
                    logging.info(f"Removed watch for {path}")
                    break

    def _should_process_path(self, path: Path) -> bool:
        """Check if path should be processed."""
        # Check if path matches patterns
        if self.patterns:
            matched = any(path.match(pattern) for pattern in self.patterns)
            if not matched:
                return False
                
        # Check if path matches ignore patterns
        if self.ignore_patterns:
            ignored = any(path.match(pattern) for pattern in self.ignore_patterns)
            if ignored:
                return False
                
        return True

    def _process_events(self):
        """Process buffered events."""
        while self.running.is_set():
            events = self.event_buffer.get_events()
            for event in events:
                try:
                    self.callback(event)
                except Exception as e:
                    logging.error(f"Error processing event: {e}")
            time.sleep(0.1)

    def on_created(self, event: FileCreatedEvent):
        """Handle file creation event."""
        if event.is_directory and self.ignore_directories:
            return
            
        path = Path(event.src_path)
        if not self._should_process_path(path):
            return
            
        if not event.is_directory:
            if self.file_detector.should_process_file(path):
                self.event_buffer.add_event(WatcherEvent(
                    event_type="created",
                    path=path,
                    timestamp=datetime.now(),
                    is_directory=event.is_directory
                ))

    def on_modified(self, event: FileModifiedEvent):
        """Handle file modification event."""
        if event.is_directory and self.ignore_directories:
            return
            
        path = Path(event.src_path)
        if not self._should_process_path(path):
            return
            
        self.event_buffer.add_event(WatcherEvent(
            event_type="modified",
            path=path,
            timestamp=datetime.now(),
            is_directory=event.is_directory
        ))

    def on_deleted(self, event: FileDeletedEvent):
        """Handle file deletion event."""
        if event.is_directory and self.ignore_directories:
            return
            
        path = Path(event.src_path)
        if not self._should_process_path(path):
            return
            
        self.event_buffer.add_event(WatcherEvent(
            event_type="deleted",
            path=path,
            timestamp=datetime.now(),
            is_directory=event.is_directory
        ))

class WatchManager:
    """Manages multiple file watchers."""
    
    def __init__(self):
        """Initialize watch manager."""
        self.watchers: Dict[str, FileWatcher] = {}
        self.running = False

    def add_watcher(self,
                   name: str,
                   paths: List[Union[str, Path]],
                   callback: Callable[[WatcherEvent], None],
                   patterns: Optional[List[str]] = None,
                   ignore_patterns: Optional[List[str]] = None,
                   recursive: bool = True):
        """Add a new watcher."""
        if name in self.watchers:
            raise ValueError(f"Watcher {name} already exists")
            
        watcher = FileWatcher(
            callback=callback,
            patterns=patterns,
            ignore_patterns=ignore_patterns
        )
        
        for path in paths:
            watcher.add_watch(path, recursive=recursive)
            
        self.watchers[name] = watcher
        
        if self.running:
            watcher.start()

    def remove_watcher(self, name: str):
        """Remove a watcher."""
        if name in self.watchers:
            watcher = self.watchers.pop(name)
            if self.running:
                watcher.stop()

    def start(self):
        """Start all watchers."""
        self.running = True
        for watcher in self.watchers.values():
            watcher.start()

    def stop(self):
        """Stop all watchers."""
        self.running = False
        for watcher in self.watchers.values():
            watcher.stop()

    def get_watched_paths(self) -> Dict[str, Set[Path]]:
        """Get all watched paths."""
        return {
            name: watcher.watch_paths.copy()
            for name, watcher in self.watchers.items()
        }

    def is_path_watched(self, path: Union[str, Path]) -> bool:
        """Check if a path is being watched."""
        path = Path(path)
        for watcher in self.watchers.values():
            if any(path in watch_path.parents or path == watch_path
                  for watch_path in watcher.watch_paths):
                return True
        return False 