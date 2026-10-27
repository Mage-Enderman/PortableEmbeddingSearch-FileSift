import sqlite3
import struct
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from core.config import DB_PATH
from core.chunker import Chunk


class IndexStore:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or DB_PATH)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        with self.get_connection() as conn:
            # Metadata table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

            # Files table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    status TEXT NOT NULL,
                    chunk_count INTEGER DEFAULT 0,
                    indexed_at REAL NOT NULL
                );
            """)

            # Chunks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    title TEXT NOT NULL,
                    loc_start INTEGER NOT NULL,
                    loc_end INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    vector BLOB NOT NULL,
                    FOREIGN KEY (file_id) REFERENCES files (id) ON DELETE CASCADE
                );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks (file_id);")

            # FTS5 full-text search table for exact BM25 keyword matching
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5 (
                    text,
                    title,
                    filename,
                    content='chunks',
                    content_rowid='id',
                    tokenize='porter unicode61 remove_diacritics 2'
                );
            """)

            # Triggers to keep FTS index synchronized with chunks table
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                    INSERT INTO fts_chunks(rowid, text, title, filename)
                    SELECT new.id, new.text, new.title, f.filename
                    FROM files f WHERE f.id = new.file_id;
                END;
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                    INSERT INTO fts_chunks(fts_chunks, rowid, text, title, filename)
                    VALUES('delete', old.id, old.text, old.title, '');
                END;
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
                    INSERT INTO fts_chunks(fts_chunks, rowid, text, title, filename)
                    VALUES('delete', old.id, old.text, old.title, '');
                    INSERT INTO fts_chunks(rowid, text, title, filename)
                    SELECT new.id, new.text, new.title, f.filename
                    FROM files f WHERE f.id = new.file_id;
                END;
            """)

    @staticmethod
    def vector_to_blob(vec: np.ndarray) -> bytes:
        """Serializes float32 array to binary bytes."""
        vec_f32 = np.ascontiguousarray(vec, dtype=np.float32)
        return vec_f32.tobytes()

    @staticmethod
    def blob_to_vector(blob: bytes) -> np.ndarray:
        """Deserializes binary bytes to float32 numpy array."""
        return np.frombuffer(blob, dtype=np.float32)

    def get_file(self, path: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM files WHERE path = ?", (path,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_indexed_paths(self) -> Dict[str, Tuple[float, int]]:
        """Returns map of {path: (mtime, size)} for all currently indexed files."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT path, mtime, size FROM files WHERE status = 'indexed'")
            return {row["path"]: (row["mtime"], row["size"]) for row in cursor.fetchall()}

    def record_indexed_file(
        self,
        path: str,
        filename: str,
        extension: str,
        size: int,
        mtime: float,
        chunks: List[Chunk],
        vectors: np.ndarray,
        indexed_at: float,
    ) -> int:
        """Inserts or updates file and all its chunks with vectors in a single transaction."""
        with self.get_connection() as conn:
            # Delete existing file record if present (cascades to chunks and triggers FTS cleanup)
            cursor = conn.execute("SELECT id FROM files WHERE path = ?", (path,))
            existing = cursor.fetchone()
            if existing:
                conn.execute("DELETE FROM files WHERE id = ?", (existing["id"],))

            # Insert new file row
            cursor = conn.execute("""
                INSERT INTO files (path, filename, extension, size, mtime, status, chunk_count, indexed_at)
                VALUES (?, ?, ?, ?, ?, 'indexed', ?, ?)
            """, (path, filename, extension, size, mtime, len(chunks), indexed_at))
            file_id = cursor.lastrowid

            # Insert chunks with binary vectors
            for idx, chunk in enumerate(chunks):
                vec_blob = self.vector_to_blob(vectors[idx])
                conn.execute("""
                    INSERT INTO chunks (file_id, chunk_index, text, title, loc_start, loc_end, label, vector)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    file_id,
                    chunk.chunk_index,
                    chunk.text,
                    chunk.title,
                    chunk.loc_start,
                    chunk.loc_end,
                    chunk.label,
                    vec_blob,
                ))

            return file_id

    def delete_files_not_in(self, active_paths: List[str]) -> int:
        """Removes records for files that no longer exist or were deselected."""
        if not active_paths:
            with self.get_connection() as conn:
                cursor = conn.execute("DELETE FROM files")
                return cursor.rowcount

        with self.get_connection() as conn:
            placeholders = ",".join(["?"] * len(active_paths))
            cursor = conn.execute(f"DELETE FROM files WHERE path NOT IN ({placeholders})", active_paths)
            return cursor.rowcount

    def delete_file(self, path: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM files WHERE path = ?", (path,))
            return cursor.rowcount > 0

    def get_stats(self) -> Dict[str, Any]:
        with self.get_connection() as conn:
            total_files = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            total_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            db_size_bytes = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0
            return {
                "total_files": total_files,
                "total_chunks": total_chunks,
                "db_size_mb": round(db_size_bytes / (1024 * 1024), 2),
            }

    def load_all_vectors(self) -> Tuple[np.ndarray, List[int]]:
        """Loads all vectors into memory matrix for fast cosine similarity scoring."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT id, vector FROM chunks ORDER BY id")
            rows = cursor.fetchall()
            if not rows:
                return np.empty((0, 0), dtype=np.float32), []

            chunk_ids = [r["id"] for r in rows]
            vectors = [self.blob_to_vector(r["vector"]) for r in rows]
            matrix = np.vstack(vectors)
            return matrix, chunk_ids

    def bm25_search(self, query_str: str, limit: int = 50) -> List[Tuple[int, float]]:
        """Runs SQLite FTS5 BM25 search over chunks."""
        import re
        # Sanitize query for FTS5 (split words/identifiers, keeping alpha, numeric, underscores)
        clean_terms = [t for t in re.split(r"[^\w]+", query_str) if len(t) >= 2]
        if not clean_terms:
            return []

        fts_query = " OR ".join([f'"{term}"*' for term in clean_terms])
        with self.get_connection() as conn:
            try:
                cursor = conn.execute("""
                    SELECT rowid, bm25(fts_chunks) AS score
                    FROM fts_chunks
                    WHERE fts_chunks MATCH ?
                    ORDER BY score
                    LIMIT ?
                """, (fts_query, limit))
                # Note: FTS5 bm25 returns negative numbers where smaller (more negative) is better match
                results = []
                for row in cursor.fetchall():
                    cid = row["rowid"]
                    # Convert to positive relevance score
                    raw_score = -row["score"]
                    results.append((cid, float(raw_score)))
                return results
            except sqlite3.OperationalError as e:
                print(f"[IndexStore] FTS5 query error: {e}")
                return []

    def get_chunk_details(self, chunk_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if not chunk_ids:
            return {}

        with self.get_connection() as conn:
            placeholders = ",".join(["?"] * len(chunk_ids))
            sql = f"""
                SELECT c.id, c.file_id, c.chunk_index, c.text, c.title, c.loc_start, c.loc_end, c.label,
                       f.path, f.filename, f.extension, f.size, f.mtime
                FROM chunks c
                JOIN files f ON f.id = c.file_id
                WHERE c.id IN ({placeholders})
            """
            cursor = conn.execute(sql, chunk_ids)
            result = {}
            for row in cursor.fetchall():
                result[row["id"]] = dict(row)
            return result
