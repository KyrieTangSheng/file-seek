import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
import json
from datetime import datetime

class DBManager:
    def __init__(self, db_path: str = "~/.neonarc/neonarc.db"):
        """Initialize database connection and create tables if they don't exist."""
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = self._create_connection()
        self._init_tables()

    def _create_connection(self) -> sqlite3.Connection:
        """Create and return a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable row name access
        return conn

    def _init_tables(self):
        """Initialize database tables."""
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    mime_type TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    embedding_file TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents(id),
                    UNIQUE (document_id, chunk_index)
                );

                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def add_document(self, path: str, file_hash: str, mime_type: str, 
                    metadata: Optional[Dict] = None) -> int:
        """Add a new document to the database."""
        with self.conn:
            cursor = self.conn.execute("""
                INSERT INTO documents (path, filename, file_hash, mime_type, metadata)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    file_hash = excluded.file_hash,
                    mime_type = excluded.mime_type,
                    metadata = excluded.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (
                str(Path(path).absolute()),
                Path(path).name,
                file_hash,
                mime_type,
                json.dumps(metadata) if metadata else None
            ))
            return cursor.fetchone()[0]

    def get_document(self, doc_id: int) -> Optional[Dict]:
        """Retrieve a document by its ID."""
        cursor = self.conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_document_by_path(self, path: str) -> Optional[Dict]:
        """Retrieve a document by its path."""
        cursor = self.conn.execute(
            "SELECT * FROM documents WHERE path = ?", 
            (str(Path(path).absolute()),)
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def add_embedding(self, document_id: int, chunk_index: int, 
                     chunk_text: str, embedding_file: str) -> int:
        """Add an embedding for a document chunk."""
        with self.conn:
            cursor = self.conn.execute("""
                INSERT INTO embeddings 
                (document_id, chunk_index, chunk_text, embedding_file)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(document_id, chunk_index) DO UPDATE SET
                    chunk_text = excluded.chunk_text,
                    embedding_file = excluded.embedding_file
                RETURNING id
            """, (document_id, chunk_index, chunk_text, embedding_file))
            return cursor.fetchone()[0]

    def get_document_embeddings(self, document_id: int) -> List[Dict]:
        """Get all embeddings for a document."""
        cursor = self.conn.execute(
            "SELECT * FROM embeddings WHERE document_id = ? ORDER BY chunk_index",
            (document_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def set_config(self, key: str, value: str):
        """Set a configuration value."""
        with self.conn:
            self.conn.execute("""
                INSERT INTO config (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, value))

    def get_config(self, key: str) -> Optional[str]:
        """Get a configuration value."""
        cursor = self.conn.execute(
            "SELECT value FROM config WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def close(self):
        """Close the database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_all_documents(self) -> List[Dict]:
        """Get all documents in the archive."""
        cursor = self.conn.execute("SELECT * FROM documents")
        return [dict(row) for row in cursor.fetchall()]

    def delete_document(self, document_id: int) -> bool:
        """Delete a document from the database."""
        with self.conn:
            self.conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        return True

    def delete_document_embeddings(self, document_id: int) -> bool:
        """Delete all embeddings for a document."""
        with self.conn:
            self.conn.execute("DELETE FROM embeddings WHERE document_id = ?", (document_id,))
        return True
