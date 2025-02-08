from typing import List, Dict, Optional, Union, Tuple
from pathlib import Path
import hashlib
import mimetypes
from datetime import datetime
import logging
import json

from storage.db_manager import DBManager
from storage.vector_store import create_vector_store, VectorStore
from pipeline.embedding_module import EmbeddingGenerator
from core.search_service import SearchService, SearchResult
from core.config import ConfigManager, NeonArcConfig
from pipeline.pipeline import ProcessingPipeline

class Archivist:
    """Core coordinator for the NeonArc system."""
    
    def __init__(self, config: Optional[ConfigManager] = None):
        """Initialize the Archivist system."""
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Initialize configuration
        self.config = config or ConfigManager()
        
        # Create storage directories
        storage_path = Path(self.config.get('storage.database_path')).parent
        vector_store_path = Path(self.config.get('storage.vector_store_path')).parent
        
        storage_path.mkdir(parents=True, exist_ok=True)
        vector_store_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        try:
            # Initialize database
            self.db_manager = DBManager(
                db_path=self.config.get('storage.database_path')
            )
            
            # Initialize vector store with full path
            self.vector_store = create_vector_store(
                store_type=self.config.get('storage.vector_store'),
                dimension=384,  # Default for all-MiniLM-L6-v2
                index_path=self.config.get('storage.vector_store_path')  # Pass full path including filename
            )
            
            # Initialize embedding generator
            self.embedding_generator = EmbeddingGenerator(
                model_name=self.config.get('embedding.model'),
                chunk_size=self.config.get('embedding.chunk_size'),
                chunk_overlap=self.config.get('embedding.chunk_overlap'),
                batch_size=self.config.get('embedding.batch_size')
            )
            
            # Initialize pipeline with progress callback
            self.pipeline = ProcessingPipeline(
                config=self.config,
                max_workers=self.config.get('processing.max_workers', 4),
                progress_callback=lambda x: logging.info(f"Processing progress: {x*100:.0f}%")
            )
            
            # Initialize search service
            self.search_service = SearchService(
                self.db_manager,
                self.vector_store,
                self.embedding_generator,
                min_score=self.config.get('minimum_similarity')
            )
            
            logging.info("Archivist system initialized successfully")
            
        except Exception as e:
            logging.error(f"Error initializing components: {e}")
            raise

    def ingest_file(self, 
                    file_path: Union[str, Path], 
                    metadata: Optional[Dict] = None) -> bool:
        """Ingest a file into the archive."""
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                logging.error(f"File not found: {file_path}")
                return False
                
            # Generate file hash
            file_hash = self._hash_file(file_path)
            
            # Check if file already exists and is unchanged
            existing_doc = self.db_manager.get_document_by_path(str(file_path))
            if existing_doc and existing_doc['file_hash'] == file_hash:
                logging.info(f"File unchanged: {file_path}")
                return True
                
            # Process document using pipeline
            processing_result = self.pipeline.process_file(file_path)
            content = processing_result.text_content
            chunks = processing_result.chunks
            embeddings = processing_result.embeddings
            
            if not content:
                logging.error(f"No content extracted from file: {file_path}")
                return False
                
            # Store document in database
            doc_id = self.db_manager.add_document(
                str(file_path),
                file_hash,
                mimetypes.guess_type(file_path)[0] or 'application/octet-stream',
                metadata
            )
            
            # Store embeddings
            chunk_ids = []
            for i, (embedding, chunk) in enumerate(zip(embeddings, chunks)):
                chunk_id = f"{doc_id}_{i}"
                chunk_ids.append(chunk_id)
                
                # Store chunk text and metadata
                self.db_manager.add_embedding(doc_id, i, chunk, chunk_id)
            
            # Add to vector store
            self.vector_store.add_vectors(embeddings, chunk_ids)
            
            logging.info(f"Successfully ingested: {file_path}")
            return True
            
        except Exception as e:
            logging.error(f"Error ingesting file {file_path}: {e}")
            return False

    def search(self, 
               query: str, 
               limit: int = None, 
               filters: Optional[Dict] = None) -> List[SearchResult]:
        """Search the archive."""
        try:
            if limit is None:
                limit = self.config.get('default_search_limit')
                
            return self.search_service.search(query, limit, filters)
            
        except Exception as e:
            logging.error(f"Search error: {e}")
            return []

    def get_similar(self, 
                    document_id: int, 
                    limit: int = None) -> List[SearchResult]:
        """Find similar documents."""
        try:
            if limit is None:
                limit = self.config.get('default_search_limit')
                
            return self.search_service.similar_documents(document_id, limit)
            
        except Exception as e:
            logging.error(f"Error finding similar documents: {e}")
            return []

    def get_document_info(self, document_id: int) -> Optional[Dict]:
        """Get document information."""
        try:
            return self.db_manager.get_document(document_id)
        except Exception as e:
            logging.error(f"Error getting document info: {e}")
            return None

    def _hash_file(self, file_path: Path) -> str:
        """Generate hash for a file."""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _read_file(self, file_path: Path) -> Optional[str]:
        """Read file content."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            logging.error(f"Unable to read file as text: {file_path}")
            return None
        except Exception as e:
            logging.error(f"Error reading file {file_path}: {e}")
            return None

    def cleanup(self):
        """Cleanup resources."""
        try:
            self.db_manager.close()
            self.vector_store.save()
            logging.info("Cleanup completed successfully")
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")

    def remove_document(self, document_path: Union[str, Path]) -> bool:
        """Remove a document and its embeddings from the archive."""
        try:
            # Get document info
            doc = self.db_manager.get_document_by_path(str(document_path))
            if not doc:
                logging.warning(f"Document not found for deletion: {document_path}")
                return False
            
            document_id = doc['id']
            
            # Get embeddings to remove from vector store
            embeddings = self.db_manager.get_document_embeddings(document_id)
            
            # Remove from vector store
            for embedding in embeddings:
                chunk_id = f"{document_id}_{embedding['chunk_index']}"
                self.vector_store.delete_embedding(chunk_id)
            
            # Remove from database
            self.db_manager.delete_document_embeddings(document_id)
            self.db_manager.delete_document(document_id)
            
            logging.info(f"Removed document from archive: {document_path}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to remove document {document_path}: {e}")
            return False

    def get_documents_in_directory(self, directory: Union[str, Path], recursive: bool = False) -> List[Dict]:
        """Get all documents in a directory."""
        directory = Path(directory).resolve()
        docs = self.db_manager.get_all_documents()
        
        # Filter documents in target directory
        result = []
        for doc in docs:
            print(f"Doc: {doc}")
            doc_path = Path(doc['path']).resolve()
            try:
                # Check if document is in target directory
                if recursive:
                    is_target = directory in doc_path.parents or directory == doc_path.parent
                else:
                    is_target = directory == doc_path.parent
                    
                if is_target:
                    result.append(doc)
            except Exception:
                # Skip invalid paths
                continue
            
        return result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup() 