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
import os

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

class BaseOCRProcessor:
    """Base class for OCR processing."""
    
    def process_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """Process a file and return extracted text."""
        raise NotImplementedError("Subclasses must implement process_file")

class OCRProcessor(BaseOCRProcessor):
    """OCR processor implementation."""
    
    def __init__(self, languages: List[str] = ['eng'],
                 preprocess_images: bool = True,
                 confidence_threshold: int = 60,
                 tesseract_path: Optional[str] = None,
                 max_workers: int = 4):
        """Initialize OCR processor."""
        self.languages = languages
        self.preprocess_images = preprocess_images
        self.confidence_threshold = confidence_threshold
        self.max_workers = max_workers
        
        # Check system dependencies
        self._check_dependencies()
        
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            
        # Verify tesseract installation
        try:
            pytesseract.get_languages()
        except Exception as e:
            raise RuntimeError(f"Tesseract not properly configured: {e}")

    def _check_dependencies(self):
        """Check if all required system dependencies are installed."""
        # Check poppler installation
        try:
            from pdf2image.exceptions import PDFPageCountError, PDFInfoNotInstalledError
            # Try to run pdftoppm -v (part of poppler-utils)
            result = subprocess.run(['pdftoppm', '-v'], 
                                  capture_output=True, 
                                  text=True)
            if result.returncode != 0:
                raise RuntimeError("poppler-utils not found")
        except FileNotFoundError:
            os_specific_instructions = {
                'Linux': 'sudo apt-get install poppler-utils',
                'Darwin': 'brew install poppler',
                'Windows': 'Download and install poppler from: http://blog.alivate.com.au/poppler-windows/'
            }
            os_name = platform.system()
            install_cmd = os_specific_instructions.get(os_name, 
                'Please install poppler-utils for your operating system')
            
            raise RuntimeError(
                f"PDF processing requires poppler-utils to be installed.\n"
                f"Installation command for your system ({os_name}):\n"
                f"{install_cmd}"
            )

    def process_file(self, file_path: Union[str, Path]) -> Optional[str]:
        """Process a file with OCR."""
        try:
            file_path = Path(file_path)
            
            # Handle PDFs
            if file_path.suffix.lower() == '.pdf':
                return self._process_pdf(file_path)
                
            # Handle images
            elif file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']:
                return self._process_image(file_path)
                
            return None
            
        except Exception as e:
            logging.error(f"OCR processing failed: {e}", exc_info=True)
            return None

    def _process_pdf(self, file_path: Path) -> Optional[str]:
        """Process a PDF file."""
        try:
            # Convert PDF to images
            images = pdf2image.convert_from_path(file_path)
            
            # Process each page
            texts = []
            for img in images:
                text = pytesseract.image_to_string(img, lang='+'.join(self.languages))
                if text.strip():
                    texts.append(text)
                    
            return '\n\n'.join(texts) if texts else None
            
        except Exception as e:
            logging.error(f"PDF OCR failed: {e}")
            return None

    def _process_image(self, file_path: Path) -> Optional[str]:
        """Process an image file."""
        try:
            # Open and process image
            with Image.open(file_path) as img:
                text = pytesseract.image_to_string(img, lang='+'.join(self.languages))
                return text if text.strip() else None
                
        except Exception as e:
            logging.error(f"Image OCR failed: {e}")
            return None

    def process_image(self, image_path: Union[str, Path]) -> Optional[OCRResult]:
        """Process a single image file."""
        try:
            # Load image
            image = Image.open(image_path)
            
            # Preprocess if enabled
            if self.preprocess_images:
                image = ImagePreprocessor.preprocess(image)
            
            # Perform OCR
            ocr_data = pytesseract.image_to_data(
                image,
                lang='+'.join(self.languages),
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
                language='+'.join(self.languages),
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