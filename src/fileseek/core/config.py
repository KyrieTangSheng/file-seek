from pathlib import Path
from typing import Any, Dict, Optional, Union
import json
import os
from dataclasses import dataclass, asdict, field
from enum import Enum
import logging
import logging.handlers

class VectorStoreType(Enum):
    FAISS = "faiss"
    CHROMA = "chroma"

@dataclass
class StorageConfig:
    database_path: str = "~/.fileseek/fileseek.db"
    vector_store: str = "faiss"
    vector_store_path: str = "~/.fileseek/faiss/index.faiss"
    max_file_size: int = 10 * 1024 * 1024
    max_total_size: int = 1024 * 1024 * 1024
    compression: bool = True

@dataclass
class FileSeekConfig:
    """Configuration settings for FileSeek."""
    # Storage paths
    data_dir: str = "~/.fileseek"
    db_path: str = "~/.fileseek/fileseek.db"
    vector_store_path: str = "~/.fileseek/faiss/index.faiss"
    
    # Vector store settings
    vector_store_type: VectorStoreType = VectorStoreType.FAISS
    embedding_dimension: int = 768  # Default for many transformer models
    
    # Processing settings
    chunk_size: int = 1000
    chunk_overlap: int = 200
    batch_size: int = 32
    
    # OCR settings
    enable_ocr: bool = True
    ocr_languages: str = "eng"
    
    # Search settings
    default_search_limit: int = 5
    minimum_similarity: float = 0.7
    
    # Watcher settings
    enable_watcher: bool = False
    watch_interval: int = 60  # seconds
    
    storage: StorageConfig = field(default_factory=StorageConfig)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        config_dict = asdict(self)
        config_dict['vector_store_type'] = self.vector_store_type.value
        config_dict['storage'] = asdict(self.storage)
        return config_dict

class ConfigManager:
    """Manages FileSeek configuration."""
    
    def __init__(self, db_manager=None):
        self.config = FileSeekConfig()
        self.db_manager = db_manager
        self.default_config = DEFAULT_CONFIG
        self._load_config()
        logging.info("ConfigManager initialized with default config")

    def _load_config(self):
        """Load configuration from all sources."""
        # First load default config values
        default_storage = self.default_config.get('storage', {})
        self.config.storage.max_file_size = default_storage.get('max_file_size', self.config.storage.max_file_size)
        
        # Load from environment variables
        self._load_from_env()
        
        # Load from database if available
        if self.db_manager:
            self._load_from_db()
        
        # Expand all paths to absolute paths
        self._expand_paths()
        
        logging.info(f"Loaded config with paths: \n"
                    f"DB: {self.config.db_path}\n"
                    f"Vector Store: {self.config.vector_store_path}")

    def _load_from_env(self):
        """Load configuration from environment variables."""
        for field in self.config.__dataclass_fields__:
            env_var = f"FILESEEK_{field.upper()}"
            if env_var in os.environ:
                value = os.environ[env_var]
                # Convert value to appropriate type
                field_type = type(getattr(self.config, field))
                if field_type == bool:
                    value = value.lower() in ('true', '1', 'yes')
                elif field_type == int:
                    value = int(value)
                elif field_type == float:
                    value = float(value)
                elif field == 'vector_store_type':
                    value = VectorStoreType(value.lower())
                setattr(self.config, field, value)

    def _load_from_db(self):
        """Load configuration from database."""
        stored_config = self.db_manager.get_config()
        if stored_config:
            self.config = stored_config

    def _expand_paths(self):
        """Expand all path configurations."""
        # Expand FileSeekConfig paths
        self.config.data_dir = str(Path(self.config.data_dir).expanduser().absolute())
        self.config.db_path = str(Path(self.config.db_path).expanduser().absolute())
        self.config.vector_store_path = str(Path(self.config.vector_store_path).expanduser().absolute())
        
        # Expand StorageConfig paths
        self.config.storage.database_path = str(Path(self.config.storage.database_path).expanduser().absolute())
        self.config.storage.vector_store_path = str(Path(self.config.storage.vector_store_path).expanduser().absolute())

    def save(self):
        """Save current configuration to database."""
        if self.db_manager:
            config_dict = self.config.to_dict()
            self.db_manager.set_config('app_config', json.dumps(config_dict))

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation."""
        try:
            # First check FileSeekConfig
            parts = key.split('.')
            if len(parts) == 1:
                return getattr(self.config, key)
            elif parts[0] == 'storage':
                return getattr(self.config.storage, parts[1])
            
            # If not found, check DEFAULT_CONFIG
            value = self.default_config
            for part in parts:
                value = value[part]
            return value
        except (KeyError, AttributeError) as e:
            logging.warning(f"Config key '{key}' not found, using default: {default}")
            return default

    def set(self, key: str, value: Any):
        """Set configuration value."""
        if hasattr(self.config, key):
            if key == 'vector_store_type':
                value = VectorStoreType(value)
            setattr(self.config, key, value)
            self.save()
        else:
            raise ValueError(f"Unknown configuration key: {key}")

    def update(self, config_dict: Dict[str, Any]):
        """Update multiple configuration values."""
        for key, value in config_dict.items():
            self.set(key, value)

    def reset(self):
        """Reset configuration to defaults."""
        self.config = FileSeekConfig()
        self._expand_paths()
        self.save()

    def validate(self) -> bool:
        """Validate current configuration."""
        try:
            # Check if paths are valid
            Path(self.config.data_dir).expanduser()
            Path(self.config.db_path).expanduser()
            Path(self.config.vector_store_path).expanduser()
            
            # Validate numeric values
            assert self.config.chunk_size > 0
            assert self.config.chunk_overlap >= 0
            assert self.config.chunk_overlap < self.config.chunk_size
            assert self.config.batch_size > 0
            assert 0 <= self.config.minimum_similarity <= 1
            assert self.config.watch_interval > 0
            
            return True
        except Exception as e:
            print(f"Configuration validation failed: {e}")
            return False 

    def setup_logging(self, verbose: bool = False):
        """Configure logging system-wide."""
        # Create logs directory
        log_path = Path(self.get("logging.file.path")).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG if verbose else self.get("logging.level"))

        # Clear any existing handlers
        root_logger.handlers.clear()

        # File handler
        if self.get("logging.file.enabled"):
            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=self.get("logging.file.max_size"),
                backupCount=self.get("logging.file.backup_count")
            )
            file_handler.setLevel(self.get("logging.file.level"))
            file_handler.setFormatter(logging.Formatter(self.get("logging.format")))
            root_logger.addHandler(file_handler)

        # Console handler
        if self.get("logging.console.enabled"):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(
                logging.DEBUG if verbose else self.get("logging.console.level")
            )
            console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            root_logger.addHandler(console_handler)

DEFAULT_CONFIG = {
    "storage": {
        "database_path": "~/.fileseek/fileseek.db", # Use absolute path with ~/.fileseek/
        "vector_store": "faiss",
        "vector_store_path": "~/.fileseek/faiss/index.faiss",
        "max_file_size": 20 * 1024 * 1024, # 20MB per file
        "max_total_size": 1 * 1024 * 1024 * 1024, # 1GB total
        "compression": True
        },
    "embedding": {
        "model": "all-MiniLM-L6-v2",
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "batch_size": 32
    },
    "processing": {
        "supported_extensions": [
            # Documents
            ".pdf",  # PDF documents
            ".doc", ".docx",  # Word documents
            ".txt",  # Text files
            ".rtf",  # Rich text
            
            # Notes and Writing
            ".md",  # Markdown
            ".org",  # Org mode
            ".tex",  # LaTeX
            ".pages",  # Apple Pages
            
            # Presentations
            ".ppt", ".pptx",  # PowerPoint
            ".key",  # Keynote
            
            # Spreadsheets
            ".xlsx", ".xls",  # Excel
            ".numbers",  # Apple Numbers
            
            # Other text formats
            ".epub",  # E-books
            ".odt",  # OpenDocument text
            ".rst"  # reStructuredText
        ],
        
        "excluded_patterns": [
            # System and hidden files
            ".*",  # Hidden files
            "*~",  # Backup files
            "*.tmp",  # Temporary files
            "*.temp",
            "*.log",
            "*.cache",
            "*.DS_Store",
            
            # Build and configuration
            "*.conf",
            "*.config",
            "*.cfg",
            "*.ini",
            "*.lock",
            "package.json",
            "*.yaml", "*.yml",  # Configuration files
            
            # Development files
            "*.py", "*.js", "*.cpp", "*.h",  # Source code
            "*.pyc", "*.pyo", "*.pyd",  # Python bytecode
            "*.so", "*.dll", "*.dylib",  # Libraries
            
            # VCS directories
            ".git/*",
            ".svn/*",
            ".hg/*",
            
            # Build directories
            "node_modules/*",
            "build/*",
            "dist/*",
            "__pycache__/*",
            "*.egg-info/*"
        ],
        
        "excluded_directories": [
            # System directories
            "/bin", "/sbin", "/usr",
            "/etc", "/var", "/tmp",
            "Library", "Applications",
            
            # Common non-document directories
            "Downloads",
            ".cache",
            ".local",
            ".config",
            "Pictures",
            "Music",
            "Videos",
            ".DS_Store",
            
            # Development directories
            "node_modules",
            "venv",
            ".virtualenv",
            ".env",
            ".git"
        ],
        
        "recommended_paths": [
            "~/Documents",
            "~/Desktop",
            "~/Work",
            "~/Projects/docs",
            "~/Research",
            "~/Notes",
            "~/Dropbox/Documents",  # Common cloud storage
            "~/Google Drive/Documents",
            "~/OneDrive/Documents"
        ],
        
        "max_workers": 4,
        "ocr_languages": ["eng"],
        "ocr_timeout": 300,  # 5 minutes
        "max_image_size": 4096,  # max pixels in any dimension
        "max_pdf_pages": 1000
    },
    "monitoring": {
        "watch_interval": 1.0,  # seconds
        "debounce_delay": 2.0,  # seconds
        "max_queue_size": 1000
    },
    "ocr": {
        "enabled": True,  # Make OCR optional
        "languages": ["eng"],  # Default to English
        "preprocess_images": True,
        "confidence_threshold": 60,  # Minimum confidence score 0-100
        "tesseract_path": None  # Will use system installation if None
    },
    "search": {
        "minimum_similarity": 0.7,  # Add minimum similarity threshold
        "max_results": 10,
        "rerank_results": True
    },
    "logging": {
        "level": "INFO",
        "file": {
            "enabled": True,
            "path": "~/.fileseek/logs/fileseek.log",
            "max_size": 1024 * 1024,  # 1MB
            "backup_count": 5,
            "level": "DEBUG"
        },
        "console": {
            "enabled": True,
            "level": "WARNING"  # Only show warnings and errors to users
        },
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    }
} 