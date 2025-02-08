from pathlib import Path
from typing import List, Optional, Union, Dict
import numpy as np
import faiss
import chromadb
from abc import ABC, abstractmethod
import logging

class VectorStore(ABC):
    """Abstract base class for vector storage implementations."""
    
    @abstractmethod
    def add_vectors(self, vectors: np.ndarray, ids: List[str], metadata: Optional[List[Dict]] = None) -> bool:
        """Add vectors to the store with associated IDs and optional metadata."""
        pass

    @abstractmethod
    def search(self, query_vector: np.ndarray, k: int = 5) -> tuple[List[str], List[float]]:
        """Search for similar vectors and return IDs and distances."""
        pass

    @abstractmethod
    def save(self) -> bool:
        """Save the vector store to disk."""
        pass

    @abstractmethod
    def load(self) -> bool:
        """Load the vector store from disk."""
        pass

class FAISSStore(VectorStore):
    """FAISS-based vector store implementation."""
    
    def __init__(self, dimension: int, index_path: str = "~/.neonarc/faiss/index.faiss"):
        self.dimension = dimension
        self.index_path = Path(index_path).expanduser()
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize FAISS index
        self.index = faiss.IndexFlatL2(dimension)
        self.id_map: Dict[int, str] = {}  # Maps FAISS internal IDs to our IDs
        
        # Load existing index if available
        if self.index_path.exists() and self.index_path.is_file():
            self.load()

    def add_vectors(self, vectors: np.ndarray, ids: List[str], metadata: Optional[List[Dict]] = None) -> bool:
        """Add vectors to FAISS index."""
        try:
            if len(vectors) != len(ids):
                logging.error(f"Vector count ({len(vectors)}) doesn't match ID count ({len(ids)})")
                return False
            
            if vectors.shape[1] != self.dimension:
                logging.error(f"Vector dimension mismatch: expected {self.dimension}, got {vectors.shape[1]}")
                return False
            
            logging.info(f"Adding {len(vectors)} vectors to store...")
            faiss.normalize_L2(vectors)  # Normalize vectors for cosine similarity
            self.index.add(vectors)
            
            # Map IDs
            start_idx = len(self.id_map)
            for i, chunk_id in enumerate(ids):
                self.id_map[start_idx + i] = chunk_id
            
            # Save after adding
            self.save()
            logging.info(f"Successfully added {len(vectors)} vectors")
            return True
        except Exception as e:
            logging.error(f"Error adding vectors to store: {str(e)}", exc_info=True)
            return False

    def search(self, query_vector: np.ndarray, k: int = 5) -> tuple[List[str], List[float]]:
        """Search for similar vectors in FAISS index."""
        # Ensure query vector is 2D
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        
        # Normalize query vector
        faiss.normalize_L2(query_vector)
        
        # Perform search
        distances, indices = self.index.search(query_vector, k)
        
        # Map internal IDs to document IDs
        doc_ids = [self.id_map.get(int(idx)) for idx in indices[0]]
        
        return doc_ids, distances[0].tolist()

    def save(self) -> bool:
        """Save FAISS index and ID mapping to disk."""
        try:
            # Save FAISS index
            faiss.write_index(self.index, str(self.index_path))
            
            # Save ID mapping
            mapping_path = self.index_path.with_suffix('.map')
            logging.info(f"Saving ID map with {len(self.id_map)} entries to {mapping_path}")
            with open(mapping_path, 'wb') as f:
                # Save as list of tuples for better serialization
                items = list(self.id_map.items())
                np.save(f, items)
            return True
        except Exception as e:
            logging.error(f"Error saving index: {str(e)}", exc_info=True)
            return False

    def load(self) -> bool:
        """Load FAISS index and ID mapping from disk."""
        try:
            # Load FAISS index
            self.index = faiss.read_index(str(self.index_path))
            
            # Load ID mapping
            mapping_path = self.index_path.with_suffix('.map')
            if mapping_path.exists():
                logging.info(f"Loading ID map from {mapping_path}")
                with open(mapping_path, 'rb') as f:
                    # Load items and ensure integer keys
                    items = np.load(f, allow_pickle=True)
                    self.id_map = {int(k): v for k, v in items}
                logging.info(f"Loaded ID map with {len(self.id_map)} entries")
            else:
                logging.warning(f"No ID mapping file found at {mapping_path}")
                self.id_map = {}
            return True
        except Exception as e:
            logging.error(f"Error loading index: {str(e)}", exc_info=True)
            return False

    def get_vector(self, chunk_id: str) -> Optional[np.ndarray]:
        """Get vector by chunk ID."""
        try:
            # Find the internal FAISS ID for this chunk
            for faiss_id, stored_chunk_id in self.id_map.items():
                if stored_chunk_id == chunk_id:
                    # Reconstruct vector from index
                    vector = np.zeros((1, self.dimension), dtype=np.float32)
                    self.index.reconstruct(int(faiss_id), vector.reshape(-1))
                    return vector
            return None
        except Exception as e:
            logging.error(f"Error getting vector: {str(e)}")
            return None
    
    def get_embedding(self, chunk_id: str) -> Optional[np.ndarray]:
        """Get embedding vector for a chunk ID."""
        try:
            # Find internal FAISS ID
            for faiss_id, stored_id in self.id_map.items():
                if stored_id == chunk_id:
                    # Get vector from index
                    vector = np.zeros((1, self.dimension), dtype=np.float32)
                    self.index.reconstruct(int(faiss_id), vector.reshape(-1))
                    return vector
            return None
        except Exception as e:
            logging.error(f"Error getting embedding: {str(e)}")
            return None

    def delete_embedding(self, chunk_id: str) -> bool:
        """Delete an embedding from the store."""
        try:
            # Find the FAISS ID for this chunk_id
            faiss_id = None
            for fid, cid in self.id_map.items():
                if cid == chunk_id:
                    faiss_id = fid
                    break
                
            if faiss_id is None:
                logging.warning(f"Chunk ID not found in vector store: {chunk_id}")
                return False
            
            # Remove from FAISS index
            if self.index.ntotal > 0:
                # Create mask of vectors to keep
                mask = np.ones(self.index.ntotal, dtype=bool)
                mask[faiss_id] = False
                
                # Get vectors to keep
                vectors = self.index.reconstruct_n(0, self.index.ntotal)
                kept_vectors = vectors[mask]
                
                # Reset index and add back kept vectors
                self.index.reset()
                if len(kept_vectors) > 0:
                    self.index.add(kept_vectors)
                    
                    # Rebuild id_map with updated indices
                    new_id_map = {}
                    current_id = 0
                    for old_id, cid in self.id_map.items():
                        if old_id != faiss_id:  # Skip the deleted vector
                            new_id_map[current_id] = cid
                            current_id += 1
                    self.id_map = new_id_map
            
            # Save updated store
            self.save()
            
            logging.info(f"Successfully deleted embedding for chunk: {chunk_id}")
            return True
        
        except Exception as e:
            logging.error(f"Failed to delete embedding {chunk_id}: {e}")
            return False

class ChromaStore(VectorStore):
    """Chroma-based vector store implementation."""
    
    def __init__(self, collection_name: str = "neonarc", path: str = "~/.neonarc/chroma"):
        self.path = Path(path).expanduser()
        self.path.mkdir(parents=True, exist_ok=True)
        
        # Initialize Chroma client
        self.client = chromadb.PersistentClient(path=str(self.path))
        self.collection = self.client.get_or_create_collection(collection_name)

    def add_vectors(self, vectors: np.ndarray, ids: List[str], metadata: Optional[List[Dict]] = None) -> bool:
        """Add vectors to Chroma collection."""
        try:
            # Convert vectors to list format
            embeddings = vectors.tolist()
            
            # Add documents to collection
            self.collection.add(
                embeddings=embeddings,
                ids=ids,
                metadatas=metadata if metadata else [{} for _ in ids]
            )
            return True
        except Exception as e:
            print(f"Error adding vectors: {e}")
            return False

    def search(self, query_vector: np.ndarray, k: int = 5) -> tuple[List[str], List[float]]:
        """Search for similar vectors in Chroma collection."""
        try:
            # Ensure query vector is in correct format
            if query_vector.ndim == 1:
                query_vector = query_vector.reshape(1, -1)
            
            # Perform search
            results = self.collection.query(
                query_embeddings=query_vector.tolist(),
                n_results=k
            )
            
            return results['ids'][0], results['distances'][0]
        except Exception as e:
            print(f"Error searching vectors: {e}")
            return [], []

    def save(self) -> bool:
        """Save is automatic in Chroma."""
        return True

    def load(self) -> bool:
        """Load is automatic in Chroma."""
        return True

def create_vector_store(store_type: str = "faiss", **kwargs) -> VectorStore:
    """Factory function to create vector store instances."""
    if store_type.lower() == "faiss":
        return FAISSStore(**kwargs)
    elif store_type.lower() == "chroma":
        return ChromaStore(**kwargs)
    else:
        raise ValueError(f"Unsupported vector store type: {store_type}") 