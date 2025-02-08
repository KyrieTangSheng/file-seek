from typing import List, Optional, Dict, Union
import numpy as np
from sentence_transformers import SentenceTransformer
from pathlib import Path
import torch
from tqdm import tqdm
import pickle
import logging

class TextChunker:
    """Handles text chunking for embedding generation."""
    def __init__(self, 
                 chunk_size: int = 1000, 
                 chunk_overlap: int = 200,
                 boundary_region_size: int = 200):
        """
        chunk_size: Maximum characters in a chunk.
        chunk_overlap: Overlap size in characters between consecutive chunks.
        boundary_region_size: Only look for sentence boundaries within the last 
                              N characters of each chunk (to avoid tiny chunks).
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.boundary_region_size = boundary_region_size

    def chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks with optional sentence boundary logic."""
        if not text:
            return []
        
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = start + self.chunk_size
            
            # If we're not at the very end, try to break at a sentence boundary
            if end < text_len:
                # We'll only look for sentence separators within the last
                # `boundary_region_size` characters of [start, end].
                chunk_slice = text[start:end]
                
                # The boundary region starts from chunk_size - boundary_region_size 
                # within this slice (but no less than 0).
                boundary_start = max(0, len(chunk_slice) - self.boundary_region_size)
                boundary_substring = chunk_slice[boundary_start:]
                
                # Look for the *last* occurrence of any sentence separator in that region.
                local_boundary_pos = -1
                chosen_sep_len = 0
                for sep in ['. ', '! ', '? ']:
                    pos = boundary_substring.rfind(sep)
                    if pos != -1 and pos > local_boundary_pos:
                        local_boundary_pos = pos
                        chosen_sep_len = len(sep)
                
                # If we found a separator near the end of the chunk, break at that boundary
                if local_boundary_pos != -1:
                    # Convert local_boundary_pos back to the absolute position in the text
                    actual_sep_pos = start + boundary_start + local_boundary_pos
                    # We add the length of the separator to keep it with the chunk
                    end = actual_sep_pos + chosen_sep_len
            
            # Add the chunk
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move to the next chunk start, accounting for overlap
            start = end - self.chunk_overlap

            # Safety net: if overlap makes us go backward or not advance, break to avoid infinite loop
            if start <= 0:
                break

        return chunks


class EmbeddingGenerator:
    """Generates embeddings for text using transformer models."""
    
    def __init__(self, 
                 model_name: str = "all-MiniLM-L6-v2",
                 batch_size: int = 64,
                 max_workers: int = 4,
                 cache_dir: Optional[Path] = None,
                 chunk_size: int = 2000,
                 chunk_overlap: int = 100,
                 boundary_region_size: int = 200):
        """
        model_name: Model name for SentenceTransformer.
        batch_size: Embedding batch size.
        max_workers: Reserved for concurrency or parallel usage if needed.
        cache_dir: Where to store cached embeddings (optional).
        chunk_size: Number of characters in each chunk (max).
        chunk_overlap: Number of characters of overlap between chunks.
        boundary_region_size: Only look for sentence boundaries within the 
                              last N characters of each chunk.
        """
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.cache_dir = cache_dir
        
        # Initialize chunker
        self.chunker = TextChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            boundary_region_size=boundary_region_size
        )
        
        # Initialize model
        self.model = SentenceTransformer(model_name)
        self.embedding_dimension = self.model.get_sentence_embedding_dimension()
        
        # Enable GPU if available
        if torch.cuda.is_available():
            self.model = self.model.to('cuda')
            self.batch_size = batch_size * 2  # Optionally double batch size for GPU
            logging.info(f"Using GPU for embedding generation with batch size {self.batch_size}")
        
        # Initialize cache
        self.cache = {}
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_cache()

    def _load_cache(self):
        """Load embedding cache from disk."""
        if self.cache_dir:
            cache_file = self.cache_dir / f"embedding_cache_{self.model_name}.pkl"
            if cache_file.exists():
                with open(cache_file, 'rb') as f:
                    self.cache = pickle.load(f)

    def _save_cache(self):
        """Save embedding cache to disk."""
        if self.cache_dir:
            cache_file = self.cache_dir / f"embedding_cache_{self.model_name}.pkl"
            with open(cache_file, 'wb') as f:
                pickle.dump(self.cache, f)

    def _generate_batch_embeddings(self, chunks: List[str]) -> np.ndarray:
        """Generate embeddings for a batch of chunks, using cache if available."""
        embeddings = []
        uncached_chunks = []
        uncached_indices = []
        
        # Check cache first
        for i, chunk in enumerate(chunks):
            cache_key = hash(chunk)
            if cache_key in self.cache:
                embeddings.append(self.cache[cache_key])
            else:
                uncached_chunks.append(chunk)
                uncached_indices.append(i)
        
        # Generate embeddings for uncached chunks
        if uncached_chunks:
            with torch.no_grad():
                batch_embeddings = self.model.encode(
                    uncached_chunks,
                    batch_size=self.batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True
                )
            
            # Update cache
            for i, chunk in enumerate(uncached_chunks):
                cache_key = hash(chunk)
                self.cache[cache_key] = batch_embeddings[i]
                embeddings.append(batch_embeddings[i])
        
        return np.array(embeddings)

    def process_document(self, 
                        text: str, 
                        metadata: Optional[Dict] = None,
                        show_progress: bool = True) -> tuple[np.ndarray, List[str], List[Dict]]:
        """Process a document and return embeddings, chunks, and metadata."""
        # Chunk the text
        chunks = self.chunker.chunk_text(text)
        if not chunks:
            return np.array([]), [], []
        
        # Process all chunks in one go if possible
        if len(chunks) <= self.batch_size:
            embeddings = self._generate_batch_embeddings(chunks)
        else:
            # Process chunks in batches
            embeddings = []
            total_batches = (len(chunks) + self.batch_size - 1) // self.batch_size
            
            with tqdm(total=total_batches, disable=not show_progress) as pbar:
                for i in range(0, len(chunks), self.batch_size):
                    batch = chunks[i:i + self.batch_size]
                    batch_embeddings = self._generate_batch_embeddings(batch)
                    embeddings.extend(batch_embeddings)
                    pbar.update(1)
            
            embeddings = np.array(embeddings)
        
        # Prepare chunk metadata
        chunk_metadata = []
        for i, chunk in enumerate(chunks):
            chunk_meta = {
                'chunk_index': i,
                'chunk_size': len(chunk),
                'chunk_start': text.find(chunk)
            }
            if metadata:
                chunk_meta.update(metadata)
            chunk_metadata.append(chunk_meta)
        
        # Save cache periodically (for example, every 1000 additions)
        if self.cache_dir and (len(self.cache) % 1000) == 0:
            self._save_cache()
            
        return embeddings, chunks, chunk_metadata

    def get_embedding_dimension(self) -> int:
        """Return the dimension of the embeddings."""
        return self.embedding_dimension

    @staticmethod
    def list_available_models() -> List[str]:
        """List available embedding models."""
        return [
            "all-MiniLM-L6-v2",         # Fast, good quality
            "all-mpnet-base-v2",       # Higher quality, slower
            "multi-qa-MiniLM-L6-v2",   # Optimized for QA
            "all-distilroberta-v1",    # Good balance of speed/quality
            # Add more models as needed
        ]

    def __call__(self, texts: Union[str, List[str]], **kwargs) -> np.ndarray:
        """Convenience method to generate embeddings."""
        if isinstance(texts, str):
            texts = [texts]
        return self.generate_embeddings(texts, **kwargs)

    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        Example convenience method for generating embeddings on a list of texts
        (without chunking). 
        """
        # Check cache first for each text
        embeddings = []
        uncached_texts = []
        uncached_indices = []

        for i, t in enumerate(texts):
            cache_key = hash(t)
            if cache_key in self.cache:
                embeddings.append(self.cache[cache_key])
            else:
                uncached_texts.append(t)
                uncached_indices.append(i)

        if uncached_texts:
            with torch.no_grad():
                batch_embeddings = self.model.encode(
                    uncached_texts,
                    batch_size=self.batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True
                )
            for i, t in enumerate(uncached_texts):
                cache_key = hash(t)
                self.cache[cache_key] = batch_embeddings[i]
                embeddings.append(batch_embeddings[i])

        return np.array(embeddings)
