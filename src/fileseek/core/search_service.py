from typing import List, Dict, Optional, Union, Tuple
import numpy as np
from dataclasses import dataclass
from pathlib import Path
import logging

from fileseek.pipeline.embedding_module import EmbeddingGenerator
from fileseek.storage.vector_store import VectorStore
from fileseek.storage.db_manager import DBManager

@dataclass
class SearchResult:
    """Represents a single search result."""
    document_id: int
    chunk_id: str
    chunk_text: str
    score: float
    metadata: Dict
    document_path: str
    
    def to_dict(self) -> Dict:
        """Convert search result to dictionary."""
        return {
            'document_id': self.document_id,
            'chunk_id': self.chunk_id,
            'chunk_text': self.chunk_text,
            'score': self.score,
            'metadata': self.metadata,
            'document_path': self.document_path
        }

class SearchService:
    """Handles document search operations."""
    
    def __init__(self, 
                 db_manager: DBManager,
                 vector_store: VectorStore,
                 embedding_generator: EmbeddingGenerator,
                 min_score: float = 0.7):
        """Initialize search service."""
        self.db_manager = db_manager
        self.vector_store = vector_store
        self.embedding_generator = embedding_generator
        self.min_score = min_score

    def search(self, 
              query: str, 
              limit: int = 5, 
              filters: Optional[Dict] = None,
              return_raw: bool = False) -> Union[List[SearchResult], Tuple[List[SearchResult], np.ndarray]]:
        """
        Search for similar content.
        
        Args:
            query: Search query text
            limit: Maximum number of results to return
            filters: Optional filters to apply
            return_raw: Whether to return raw vectors
        """
        try:
            # Get embeddings and search
            query_embedding = self.embedding_generator.generate_embeddings(query)
            chunk_ids, scores = self.vector_store.search(query_embedding, k=limit)
            
            results = []
            for chunk_id, score in zip(chunk_ids, scores):
                if score < self.min_score:
                    continue
                    
                doc_id, chunk_idx = self._parse_chunk_id(chunk_id)
                doc = self.db_manager.get_document(doc_id)
                if not doc:
                    continue
                    
                if filters and not self._apply_filters(doc, filters):
                    continue
                
                chunk_data = self.db_manager.get_document_embeddings(doc_id)
                if not chunk_data or chunk_idx >= len(chunk_data):
                    continue
                    
                chunk = chunk_data[chunk_idx]
                
                result = SearchResult(
                    document_id=doc_id,
                    chunk_id=chunk_id,
                    chunk_text=chunk['chunk_text'],
                    score=float(score),
                    metadata=doc.get('metadata', {}),
                    document_path=doc['path']
                )
                results.append(result)
                
                if len(results) >= limit:
                    break
            
            if return_raw:
                return results, query_embedding
            return results
            
        except Exception as e:
            logging.error(f"Search failed: {e}")
            if return_raw:
                return [], None
            return []

    def _parse_chunk_id(self, chunk_id: str) -> Tuple[int, int]:
        """Parse document ID and chunk index from chunk ID."""
        try:
            doc_id, chunk_idx = chunk_id.split('_')
            return int(doc_id), int(chunk_idx)
        except:
            return -1, -1

    def _apply_filters(self, document: Dict, filters: Dict) -> bool:
        """Apply metadata filters to document."""
        doc_metadata = document.get('metadata', {})
        
        for key, value in filters.items():
            if key not in doc_metadata:
                return False
            
            if isinstance(value, (list, tuple)):
                if doc_metadata[key] not in value:
                    return False
            elif doc_metadata[key] != value:
                return False
                
        return True

    def similar_documents(self, 
                         document_id: int, 
                         limit: int = 5) -> List[SearchResult]:
        """Find documents similar to a given document."""
        # Get document embeddings
        chunk_data = self.db_manager.get_document_embeddings(document_id)
        if not chunk_data:
            return []
            
        # Use first chunk as query
        chunk = chunk_data[0]
        chunk_id = f"{document_id}_0"
        
        # Get embedding from vector store
        embedding = self.vector_store.get_embedding(chunk_id)
        if embedding is None:
            logging.error(f"Could not find embedding for chunk {chunk_id}")
            return []
        
        # Search using the embedding - get extra results to allow for filtering
        chunk_ids, scores = self.vector_store.search(
            embedding,
            k=limit ** 2  # Get more results to allow for filtering
        )
        
        # Process results
        results = []
        for chunk_id, score in zip(chunk_ids, scores):
            doc_id, chunk_idx = self._parse_chunk_id(chunk_id)
            
            # Skip chunks from the same document
            if doc_id == document_id:
                continue
                
            doc = self.db_manager.get_document(doc_id)
            if not doc:
                continue
                
            chunk_data = self.db_manager.get_document_embeddings(doc_id)
            if not chunk_data or chunk_idx >= len(chunk_data):
                continue
                
            chunk = chunk_data[chunk_idx]
            
            result = SearchResult(
                document_id=doc_id,
                chunk_id=chunk_id,
                chunk_text=chunk['chunk_text'],
                score=float(score),
                metadata=doc.get('metadata', {}),
                document_path=doc['path']
            )
            results.append(result)
            
            # Stop once we have enough results
            if len(results) >= limit:
                break
        
        return results

    def get_document_context(self, 
                           chunk_id: str, 
                           context_size: int = 2) -> List[str]:
        """Get surrounding chunks for context."""
        doc_id, chunk_idx = self._parse_chunk_id(chunk_id)
        
        chunk_data = self.db_manager.get_document_embeddings(doc_id)
        if not chunk_data:
            return []
            
        # Calculate context range
        start_idx = max(0, chunk_idx - context_size)
        end_idx = min(len(chunk_data), chunk_idx + context_size + 1)
        
        # Get chunk texts
        return [chunk_data[i]['chunk_text'] for i in range(start_idx, end_idx)] 