from pathlib import Path
from typing import Optional, List, Dict, Union, Tuple
import logging
import tempfile
from dataclasses import dataclass
import pytesseract
from PIL import Image
import pdf2image
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import subprocess
import sys
import platform

@dataclass
class OCRResult:
    """Results from OCR processing."""
    text: str
    confidence: float
    language: str
    page_number: Optional[int] = None
    bounding_boxes: Optional[List[Dict]] = None

class ImagePreprocessor:
    """Handles image preprocessing for better OCR results."""
    
    @staticmethod
    def preprocess(image: Image.Image) -> Image.Image:
        """Preprocess image for better OCR results."""
        try:
            # Convert to grayscale
            if image.mode != 'L':
                image = image.convert('L')
            
            # Increase contrast
            import cv2
            import numpy as np
            img_array = np.array(image)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            img_array = clahe.apply(img_array)
            
            # Denoise
            img_array = cv2.fastNlMeansDenoising(img_array)
            
            # Convert back to PIL Image
            return Image.fromarray(img_array)
            
        except Exception as e:
            logging.warning(f"Image preprocessing failed: {e}")
            return image

class OCRProcessor:
    """Handles OCR processing for images and PDFs."""
    
    @staticmethod
    def check_tesseract_installation() -> Tuple[bool, str]:
        """Check if Tesseract is installed and return installation instructions if not."""
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True, "Tesseract is installed"
        except Exception:
            os_type = platform.system().lower()
            if os_type == 'linux':
                instructions = (
                    "To install Tesseract OCR on Linux:\n"
                    "sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-eng"
                )
            elif os_type == 'darwin':
                instructions = (
                    "To install Tesseract OCR on macOS:\n"
                    "brew install tesseract"
                )
            elif os_type == 'windows':
                instructions = (
                    "To install Tesseract OCR on Windows:\n"
                    "1. Download installer from: https://github.com/UB-Mannheim/tesseract/wiki\n"
                    "2. Run the installer\n"
                    "3. Add Tesseract to system PATH"
                )
            else:
                instructions = "Please install Tesseract OCR for your operating system"
            
            return False, instructions

    def __init__(self, 
                 languages: Union[str, List[str]] = 'eng',
                 tesseract_path: Optional[str] = None,
                 preprocess_images: bool = True,
                 confidence_threshold: float = 60.0,
                 max_workers: int = 4):
        """Initialize OCR processor."""
        self.languages = ','.join(languages) if isinstance(languages, list) else languages
        self.preprocess_images = preprocess_images
        self.confidence_threshold = confidence_threshold
        self.max_workers = max_workers

        # Check Tesseract installation
        is_installed, instructions = self.check_tesseract_installation()
        if not is_installed:
            raise RuntimeError(
                "Tesseract OCR is required but not installed.\n\n"
                f"{instructions}\n\n"
                "Alternatively, you can:\n"
                "1. Disable OCR in config: neonarc config set ocr.enabled false\n"
                "2. Use text-only mode for PDFs\n"
                "3. Skip image processing"
            )
        
        # Configure Tesseract path if provided
        if tesseract_path:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            
        # Initialize preprocessor
        self.preprocessor = ImagePreprocessor()
        logging.info(f"OCR Processor initialized with languages: {self.languages}")

    def process_image(self, image_path: Union[str, Path]) -> Optional[OCRResult]:
        """Process a single image file."""
        try:
            # Load image
            image = Image.open(image_path)
            
            # Preprocess if enabled
            if self.preprocess_images:
                image = self.preprocessor.preprocess(image)
            
            # Perform OCR
            ocr_data = pytesseract.image_to_data(
                image,
                lang=self.languages,
                output_type=pytesseract.Output.DICT
            )
            
            # Extract text and confidence
            text_parts = []
            confidences = []
            boxes = []
            
            for i, conf in enumerate(ocr_data['conf']):
                if conf > self.confidence_threshold:
                    text_parts.append(ocr_data['text'][i])
                    confidences.append(conf)
                    
                    # Store bounding box
                    boxes.append({
                        'text': ocr_data['text'][i],
                        'conf': conf,
                        'left': ocr_data['left'][i],
                        'top': ocr_data['top'][i],
                        'width': ocr_data['width'][i],
                        'height': ocr_data['height'][i]
                    })
            
            # Calculate average confidence
            avg_confidence = np.mean(confidences) if confidences else 0.0
            
            return OCRResult(
                text=' '.join(text_parts),
                confidence=avg_confidence,
                language=self.languages,
                bounding_boxes=boxes
            )
            
        except Exception as e:
            logging.error(f"Error processing image {image_path}: {e}")
            return None

    def process_pdf(self, 
                   pdf_path: Union[str, Path],
                   show_progress: bool = True) -> List[OCRResult]:
        """Process a PDF file."""
        try:
            # Convert PDF to images
            images = pdf2image.convert_from_path(pdf_path)
            
            results = []
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Create temporary directory for images
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Save images to temporary files
                    temp_images = []
                    for i, image in enumerate(images):
                        temp_path = Path(temp_dir) / f"page_{i}.png"
                        image.save(temp_path)
                        temp_images.append(temp_path)
                    
                    # Process images in parallel
                    futures = [
                        executor.submit(self._process_pdf_page, path, i)
                        for i, path in enumerate(temp_images)
                    ]
                    
                    # Collect results
                    for future in tqdm(futures, 
                                     desc="Processing PDF pages",
                                     disable=not show_progress):
                        result = future.result()
                        if result:
                            results.append(result)
            
            return results
            
        except Exception as e:
            logging.error(f"Error processing PDF {pdf_path}: {e}")
            return []

    def _process_pdf_page(self, image_path: Path, page_number: int) -> Optional[OCRResult]:
        """Process a single PDF page."""
        result = self.process_image(image_path)
        if result:
            result.page_number = page_number
        return result

    def process_file(self, file_path: Union[str, Path], **kwargs) -> Optional[str]:
        """Process a file with OCR, falling back to text extraction if possible."""
        try:
            # Try OCR first
            return super().process_file(file_path, **kwargs)
        except Exception as e:
            logging.warning(f"OCR failed: {e}, attempting fallback text extraction")
            
            # Fallback for PDFs: Try pdfplumber
            if str(file_path).lower().endswith('.pdf'):
                try:
                    import pdfplumber
                    with pdfplumber.open(file_path) as pdf:
                        return "\n".join(page.extract_text() for page in pdf.pages)
                except Exception as pdf_error:
                    logging.error(f"Fallback PDF extraction failed: {pdf_error}")
            
            return None

    @staticmethod
    def get_supported_languages() -> List[str]:
        """Get list of supported languages."""
        try:
            return pytesseract.get_languages()
        except Exception as e:
            logging.error(f"Error getting supported languages: {e}")
            return ['eng']  # Return default if can't get language list

    @staticmethod
    def is_available() -> bool:
        """Check if OCR is available on the system."""
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False 