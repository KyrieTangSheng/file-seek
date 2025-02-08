from pathlib import Path
from typing import Optional, Dict, List, Set, Tuple, Union
import mimetypes
import magic
import chardet
import logging
from dataclasses import dataclass
import os
import json
from fileseek.core.config import ConfigManager
from datetime import datetime

@dataclass
class FileInfo:
    """Information about a detected file."""
    path: Path
    mime_type: str
    encoding: Optional[str]
    size: int
    is_binary: bool
    can_read: bool
    metadata: Dict

class FileTypeHandler:
    """Base class for file type handlers."""
    
    def __init__(self):
        self.supported_types: Set[str] = set()

    def can_handle(self, mime_type: str) -> bool:
        """Check if this handler can process the file type."""
        return mime_type in self.supported_types

    def extract_metadata(self, file_path: Path) -> Dict:
        """Extract metadata from file. Override in subclasses."""
        return {}

class TextFileHandler:
    """Handler for text files."""
    
    def __call__(self, file_path: Path) -> Dict:
        """Process a text file."""
        return {
            'type': 'text',
            'extension': file_path.suffix.lower(),
            'size': file_path.stat().st_size,
            'modified': datetime.fromtimestamp(file_path.stat().st_mtime)
        }

class PDFFileHandler(FileTypeHandler):
    """Handler for PDF files."""
    
    def __init__(self):
        super().__init__()
        self.supported_types = {'application/pdf'}

    def extract_metadata(self, file_path: Path) -> Dict:
        """Extract metadata from PDF file."""
        metadata = {}
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                metadata = {
                    'page_count': len(pdf.pages),
                    'author': pdf.metadata.get('Author'),
                    'creator': pdf.metadata.get('Creator'),
                    'producer': pdf.metadata.get('Producer'),
                    'created': pdf.metadata.get('CreationDate'),
                    'modified': pdf.metadata.get('ModDate')
                }
        except Exception as e:
            logging.error(f"Error extracting PDF metadata: {e}")
        return metadata

class FileProcessingError(Exception):
    """Base exception for file processing errors."""
    pass

class FileSizeError(FileProcessingError):
    """Raised when file size exceeds limits."""
    pass

class FileTypeError(FileProcessingError):
    """Raised for unsupported file types."""
    pass

class FileValidationResult:
    is_valid: bool
    error: Optional[str] = None
    
class FileValidator:
    """Separate class for file validation logic."""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        
    def validate(self, path: Path) -> FileValidationResult:
        """Run all validation checks."""
        # Size check
        if not self._check_size(path):
            return FileValidationResult(False, "File too large")
            
        # Extension check
        if not self._check_extension(path):
            return FileValidationResult(False, "Unsupported extension")
            
        return FileValidationResult(True)

class FileDetector:
    """Detects and analyzes files for processing."""
    
    def __init__(self, config: Optional[ConfigManager] = None):
        self.config = config or ConfigManager()
        self.supported_extensions = self.config.get('processing.supported_extensions')
        self.excluded_patterns = self.config.get('processing.excluded_patterns')
        self.excluded_directories = self.config.get('processing.excluded_directories')
        self.max_file_size = self.config.get('storage.max_file_size')
        
        # Initialize mime types
        mimetypes.init()
        
        # Initialize handlers
        self.handlers = {
            'text': TextFileHandler(),
            'application/pdf': PDFFileHandler()
        }
        
        logging.info("FileDetector initialized")

    def detect_file(self, file_path: Union[str, Path]) -> Optional[FileInfo]:
        """Detect and analyze a file."""
        try:
            path = Path(file_path)
            logging.info(f"Detecting file: {path}")
            
            # Basic checks
            if not path.exists():
                logging.error(f"File not found: {path}")
                return None
            
            if not path.is_file():
                logging.error(f"Not a file: {path}")
                return None
            
            # Check if we can read the file
            can_read = os.access(path, os.R_OK)
            if not can_read:
                logging.error(f"Cannot read file: {path}")
                return None
            
            # Check file size
            size = path.stat().st_size
            if size > self.max_file_size:
                logging.error(f"File too large: {path} ({size/1024/1024:.1f}MB > {self.max_file_size/1024/1024:.1f}MB)")
                return None
            
            # Check if extension is supported
            if path.suffix.lower() not in self.supported_extensions:
                logging.error(f"Unsupported file extension: {path.suffix}")
                return None
            
            # Detect mime type
            mime_type = self._detect_mime_type(path)
            if not mime_type:
                logging.error(f"Could not determine mime type: {path}")
                return None
            
            logging.info(f"File passed all checks: {path}")
            logging.info(f"Mime type: {mime_type}")
            
            # Detect if file is binary
            is_binary = self._is_binary_file(path)
            
            # Detect encoding for text files
            encoding = None
            if not is_binary:
                encoding = self._detect_encoding(path)
            
            # Extract metadata
            metadata = self._extract_metadata(path, mime_type)
            
            return FileInfo(
                path=path,
                mime_type=mime_type,
                encoding=encoding,
                size=size,
                is_binary=is_binary,
                can_read=can_read,
                metadata=metadata
            )
            
        except Exception as e:
            logging.error(f"Error detecting file {file_path}: {e}")
            return None

    def _validate_file(self, file_path: Union[str, Path]) -> bool:
        """Validate the file."""
        path = Path(file_path)
        if not path.exists():
            logging.error(f"File not found: {path}")
            return False
        if not path.is_file():
            logging.error(f"Not a file: {path}")
            return False
        return True

    def _check_file_size(self, file_path: Union[str, Path]) -> bool:
        """Check if the file size is within the allowed limits."""
        path = Path(file_path)
        if path.stat().st_size > self.max_file_size:
            logging.error(f"File too large: {path} ({path.stat().st_size/1024/1024:.1f}MB > {self.max_file_size/1024/1024:.1f}MB)")
            return False
        return True

    def _detect_mime_type(self, file_path: Path) -> Optional[str]:
        """Detect mime type of file."""
        try:
            # Try using python-magic first
            mime_type = magic.from_file(str(file_path), mime=True)
            
            # Fall back to mimetypes if needed
            if not mime_type or mime_type == 'application/octet-stream':
                mime_type = mimetypes.guess_type(file_path)[0]
                
            return mime_type
            
        except Exception as e:
            logging.error(f"Error detecting mime type: {e}")
            return None

    def _is_binary_file(self, file_path: Path) -> bool:
        """Check if file is binary."""
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(1024)
                return b'\0' in chunk
        except Exception:
            return True

    def _detect_encoding(self, file_path: Path) -> Optional[str]:
        """Detect text file encoding."""
        try:
            with open(file_path, 'rb') as f:
                raw_content = f.read()
                result = chardet.detect(raw_content)
                return result['encoding']
        except Exception as e:
            logging.error(f"Error detecting encoding: {e}")
            return None

    def _extract_metadata(self, file_path: Path, mime_type: str) -> Dict:
        """Extract metadata using appropriate handler."""
        metadata = {
            'filename': file_path.name,
            'extension': file_path.suffix,
            'modified_time': file_path.stat().st_mtime,
            'created_time': file_path.stat().st_ctime,
        }
        
        # Find appropriate handler
        for supported_types, handler in self.handlers.items():
            if mime_type in supported_types:
                try:
                    handler_metadata = handler.extract_metadata(file_path)
                    metadata.update(handler_metadata)
                except Exception as e:
                    logging.error(f"Error in handler metadata extraction: {e}")
                    
        return metadata

    def get_supported_types(self) -> Set[str]:
        """Get all supported mime types."""
        supported = set()
        for types in self.handlers.keys():
            supported.update(types)
        return supported 

    def should_process_file(self, path: Path) -> bool:
        """Determine if a file should be processed."""
        # Check if file exists and is readable
        if not path.is_file() or not os.access(path, os.R_OK):
            return False

        # Check if file is in excluded directory
        for excluded_dir in self.excluded_directories:
            if excluded_dir in path.parts:
                return False

        # Check file extension
        if path.suffix.lower() not in self.supported_extensions:
            return False

        # Check against excluded patterns
        for pattern in self.excluded_patterns:
            if path.match(pattern):
                return False
        
        # Check file size
        try:
            if path.stat().st_size > self.max_file_size:
                logging.warning(f"File {path} exceeds maximum size limit of {self.max_file_size/1024/1024:.1f}MB")
                return False
        except OSError as e:
            logging.error(f"Error checking file size for {path}: {e}")
            return False

        return True