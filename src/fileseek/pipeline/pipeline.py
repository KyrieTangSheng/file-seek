from typing import List, Dict, Optional, Union, Callable, Protocol, TypeVar, Generic, Any
from pathlib import Path
import logging
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import sys

from fileseek.pipeline.file_detector import FileDetector, FileInfo
from fileseek.pipeline.ocr_module import OCRProcessor, OCRResult
from fileseek.pipeline.embedding_module import EmbeddingGenerator
from fileseek.core.config import ConfigManager

class ProcessingStatus(Enum):
    """Status of document processing."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

T = TypeVar('T')

class ProcessingHandler(Protocol, Generic[T]):
    def can_handle(self, mime_type: str) -> bool: ...
    def process(self, file_info: FileInfo) -> T: ...

@dataclass
class ProcessingResult(Generic[T]):
    file_info: Optional[FileInfo]
    status: ProcessingStatus
    result: Optional[T] = None
    error: Optional[str] = None
    text_content: Optional[str] = None
    embeddings: Optional[Any] = None
    metadata: Optional[Dict] = None
    chunks: Optional[List[str]] = None
    chunk_metadata: Optional[List[Dict]] = None

class ProcessingPipeline:
    """Coordinates document processing pipeline."""
    
    def __init__(self,
                 config: ConfigManager,
                 max_workers: int = 4,
                 progress_callback: Optional[Callable] = None,
                 file_detector: Optional[FileDetector] = None,
                 embedding_generator: Optional[EmbeddingGenerator] = None):
        """Initialize the processing pipeline."""
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        logging.info("=== Starting ProcessingPipeline Initialization ===")
        logging.info(f"Max workers: {max_workers}")
        logging.info(f"Progress callback present: {progress_callback is not None}")
        
        self.config = config
        self.max_workers = max_workers
        self.progress_callback = progress_callback
        
        # Initialize components
        logging.info("Creating FileDetector...")
        self.file_detector = file_detector or FileDetector(config)
        
        logging.info("Creating EmbeddingGenerator...")
        self.embedding_generator = embedding_generator or EmbeddingGenerator(
            model_name=config.get('embedding.model'),
            chunk_size=config.get('embedding.chunk_size'),
            chunk_overlap=config.get('embedding.chunk_overlap'),
            batch_size=config.get('embedding.batch_size')
        )
        
        # Initialize OCR if enabled
        self.ocr_processor = None
        if self.config.get('ocr.enabled', False):
            try:
                self.ocr_processor = OCRProcessor(
                    languages=self.config.get('ocr.languages', ['eng']),
                    preprocess_images=self.config.get('ocr.preprocess_images', True),
                    confidence_threshold=self.config.get('ocr.confidence_threshold', 60),
                    tesseract_path=self.config.get('ocr.tesseract_path'),
                    max_workers=self.max_workers
                )
                logging.info("OCR processor initialized successfully")
            except Exception as e:
                error_msg = f"OCR initialization failed: {e}. PDF and image processing will not be available."
                logging.error(error_msg)
                raise RuntimeError(error_msg)
        
        logging.info("=== ProcessingPipeline Initialization Complete ===")

    def process_file(self, file_path: Union[str, Path]) -> ProcessingResult:
        """Process a single file through the pipeline."""
        logging.info(f"\n=== Starting Processing for {file_path} ===")
        try:
            # Detect file
            logging.info("Step 1: File Detection")
            file_info = self.file_detector.detect_file(file_path)
            if not file_info:
                logging.error("File detection failed - returning error result")
                return ProcessingResult(
                    file_info=None,
                    status=ProcessingStatus.FAILED,
                    error="File detection failed"
                )
            logging.info(f"File detected successfully: {file_info.mime_type}")
            
            # Extract text content
            logging.info("Step 2: Text Extraction")
            text_content = self._extract_text(file_info)
            if not text_content:
                logging.error("Text extraction failed - returning error result")
                return ProcessingResult(
                    file_info=file_info,
                    status=ProcessingStatus.FAILED,
                    error="Text extraction failed"
                )
            logging.info(f"Text extracted successfully: {len(text_content)} characters")
            
            # Generate embeddings
            logging.info("Step 3: Embedding Generation")
            try:
                logging.info("Calling embedding_generator.process_document...")
                result = self.embedding_generator.process_document(
                    text_content,
                    metadata=file_info.metadata,
                    show_progress=bool(self.progress_callback)
                )
                
                if not result:
                    logging.error("Embedding generation returned None")
                    return ProcessingResult(
                        file_info=file_info,
                        status=ProcessingStatus.FAILED,
                        error="Embedding generation failed: returned None"
                    )
                
                logging.info(f"Got result from process_document: {type(result)}")
                logging.info(f"Result length: {len(result) if result else 'N/A'}")
                
                if len(result) != 3:
                    logging.error(f"Unexpected result format: {result}")
                    return ProcessingResult(
                        file_info=file_info,
                        status=ProcessingStatus.FAILED,
                        error=f"Invalid embedding generation result: expected 3 items, got {len(result)}"
                    )
                    
                embeddings, chunks, chunk_metadata = result  # Unpack the tuple correctly
                
                logging.info(f"Unpacked result - embeddings shape: {embeddings.shape if hasattr(embeddings, 'shape') else 'N/A'}")
                logging.info(f"Chunks: {len(chunks)}, Metadata: {len(chunk_metadata)}")
                
                if embeddings.size == 0 or len(embeddings) == 0:
                    logging.error("No embeddings generated")
                    return ProcessingResult(
                        file_info=file_info,
                        status=ProcessingStatus.FAILED,
                        error="No embeddings generated"
                    )
                    
            except Exception as e:
                logging.error(f"Error during embedding generation: {str(e)}", exc_info=True)
                return ProcessingResult(
                    file_info=file_info,
                    status=ProcessingStatus.FAILED,
                    error=f"Embedding generation failed: {str(e)}"
                )
            
            # Update metadata
            metadata = {
                **file_info.metadata,
                'chunk_count': len(chunks),
                'embedding_model': self.embedding_generator.model_name,
                'embedding_dimension': self.embedding_generator.embedding_dimension
            }
            
            logging.info("=== Processing Completed Successfully ===")
            return ProcessingResult(
                file_info=file_info,
                status=ProcessingStatus.COMPLETED,
                text_content=text_content,
                embeddings=embeddings,
                chunks=chunks,
                chunk_metadata=chunk_metadata,
                metadata=metadata
            )
            
        except Exception as e:
            logging.error(f"Unexpected error processing file {file_path}: {str(e)}", exc_info=True)
            return ProcessingResult(
                file_info=file_info if 'file_info' in locals() else None,
                status=ProcessingStatus.FAILED,
                error=str(e)
            )

    def process_batch(self, 
                     file_paths: List[Union[str, Path]],
                     show_progress: bool = True) -> List[ProcessingResult]:
        """Process multiple files in parallel."""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all files for processing
            future_to_path = {
                executor.submit(self.process_file, path): path
                for path in file_paths
            }
            
            # Process results as they complete
            iterator = tqdm(
                future_to_path.items(),
                total=len(file_paths),
                desc="Processing files",
                disable=not show_progress
            )
            
            for future, path in iterator:
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Update progress
                    if self.progress_callback:
                        self.progress_callback(path, result.status)
                        
                except Exception as e:
                    logging.error(f"Error processing {path}: {e}")
                    results.append(ProcessingResult(
                        file_info=None,
                        status=ProcessingStatus.FAILED,
                        error=str(e)
                    ))
        
        return results

    def _extract_text(self, file_info: FileInfo) -> Optional[str]:
        """Extract text from a file."""
        try:
            mime_type = file_info.mime_type
            
            # Handle PDFs
            if mime_type == 'application/pdf':
                # Try native text extraction first
                try:
                    import pdfplumber
                    with pdfplumber.open(file_info.path) as pdf:
                        text = "\n".join(page.extract_text() for page in pdf.pages)
                        if text.strip():
                            logging.info(f"Successfully extracted text from PDF using pdfplumber: {file_info.path}")
                            return text
                        logging.info("PDF appears to be scanned or contains no text layer")
                except Exception as e:
                    logging.warning(f"PDF text extraction failed: {e}")

                # Try OCR if available and needed
                if self.ocr_processor:
                    try:
                        text = self.ocr_processor.process_file(file_info.path)
                        if text:
                            logging.info(f"Successfully extracted text from PDF using OCR: {file_info.path}")
                            return text
                    except Exception as e:
                        logging.error(f"OCR processing failed: {e}")
                else:
                    logging.warning(
                        "OCR is not available. Some PDFs may not be processed correctly.\n"
                        "To enable OCR support:\n"
                        "1. Install Tesseract OCR for your system\n"
                        "2. Enable OCR: fileseek config set ocr.enabled true"
                    )
            
            # Handle images
            elif mime_type in ['image/jpeg', 'image/png', 'image/tiff']:
                if self.ocr_processor:
                    try:
                        text = self.ocr_processor.process_file(file_info.path)
                        if text:
                            logging.info(f"Successfully extracted text from image using OCR: {file_info.path}")
                            return text
                    except Exception as e:
                        logging.error(f"OCR processing failed: {e}")
                else:
                    logging.warning(
                        f"Skipping image file {file_info.path}: OCR not available\n"
                        "To enable image text extraction:\n"
                        "1. Install Tesseract OCR for your system\n"
                        "2. Enable OCR: fileseek config set ocr.enabled true"
                    )
                
            # Handle text files
            elif mime_type.startswith('text/'):
                try:
                    with open(file_info.path, 'r', encoding='utf-8') as f:
                        text = f.read()
                        logging.info(f"Successfully read text file: {file_info.path}")
                        return text
                except UnicodeDecodeError:
                    # Try to detect encoding
                    import chardet
                    with open(file_info.path, 'rb') as f:
                        raw = f.read()
                        encoding = chardet.detect(raw)['encoding']
                    with open(file_info.path, 'r', encoding=encoding) as f:
                        text = f.read()
                        logging.info(f"Successfully read text file with {encoding} encoding: {file_info.path}")
                        return text
                
            else:
                logging.warning(f"Unsupported mime type: {mime_type} for file: {file_info.path}")
                return None
                
        except Exception as e:
            logging.error(f"Error extracting text from {file_info.path}: {e}")
            return None

    def get_supported_types(self) -> List[str]:
        """Get list of supported file types."""
        return list(self.file_detector.get_supported_types())

    def get_pipeline_status(self) -> Dict:
        """Get current status of pipeline components."""
        return {
            'file_detector': {
                'max_file_size': self.file_detector.max_file_size,
                'supported_types': len(self.file_detector.get_supported_types())
            },
            'ocr_processor': {
                'available': self.ocr_processor is not None and self.ocr_processor.is_available(),
                'languages': self.ocr_processor.languages if self.ocr_processor else None
            },
            'embedding_generator': {
                'model': self.embedding_generator.model_name,
                'dimension': self.embedding_generator.embedding_dimension
            }
        } 