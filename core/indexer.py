import time
import os
import threading
import numpy as np
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path
from core.config import config
from core.crawler import Crawler
from core.extractors import (
    extract_file_content,
    extract_pdf_file,
    IMAGE_EXTS,
    AUDIO_EXTS,
    VIDEO_EXTS,
    format_timestamp,
)
from core.chunker import chunk_file_segments, Chunk
from core.embedder import EmbeddingGemmaEngine
from core.index_store import IndexStore


class IndexingProgress:
    def __init__(self):
        self.status = "idle"  # idle, scanning, indexing, done, error, cancelled
        self.current_file = ""
        self.files_indexed = 0
        self.total_files = 0
        self.chunks_created = 0
        self.start_time = 0.0
        self.error_message = ""

    def to_dict(self) -> Dict[str, Any]:
        elapsed = round(time.time() - self.start_time, 1) if self.start_time > 0 else 0
        pct = int((self.files_indexed / self.total_files) * 100) if self.total_files > 0 else (100 if self.status == "done" else 0)
        return {
            "status": self.status,
            "current_file": self.current_file,
            "files_indexed": self.files_indexed,
            "total_files": self.total_files,
            "progress_pct": min(100, max(0, pct)),
            "chunks_created": self.chunks_created,
            "elapsed_seconds": elapsed,
            "error_message": self.error_message,
        }


class IndexManager:
    _instance: Optional["IndexManager"] = None

    def __init__(self):
        self.store = IndexStore()
        self.crawler = Crawler(self.store)
        self.embedder = EmbeddingGemmaEngine.get_instance()
        self.progress = IndexingProgress()
        self._cancel_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.on_index_complete: Optional[Callable[[], None]] = None

    @classmethod
    def get_instance(cls) -> "IndexManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start_indexing(self, full_reindex: bool = False) -> bool:
        with self._lock:
            if self.is_running():
                return False

            self._cancel_flag.clear()
            self._thread = threading.Thread(
                target=self._run_indexing,
                args=(full_reindex,),
                daemon=True,
            )
            self._thread.start()
            return True

    def cancel_indexing(self) -> None:
        self._cancel_flag.set()

    def _run_indexing(self, full_reindex: bool) -> None:
        self.progress.status = "scanning"
        self.progress.start_time = time.time()
        self.progress.files_indexed = 0
        self.progress.chunks_created = 0
        self.progress.error_message = ""

        try:
            # 1. Clean up or prepare
            if full_reindex:
                self.store.delete_files_not_in([])

            # 2. Change detection
            to_index, to_remove, unchanged = self.crawler.detect_changes()

            # Clean removed files from database
            for p in to_remove:
                self.store.delete_file(p)

            self.progress.total_files = len(to_index)
            if not to_index:
                self.progress.status = "done"
                if self.on_index_complete:
                    self.on_index_complete()
                return

            # Ensure model is ready before processing files
            self.progress.status = "loading_model"
            self.embedder.load_model()

            # 3. Process files
            self.progress.status = "indexing"
            deferred_long_pdfs: List[Any] = []

            for idx, file_meta in enumerate(to_index):
                if self._cancel_flag.is_set():
                    self.progress.status = "cancelled"
                    return

                folder_tag = Path(file_meta.root_folder).name if file_meta.root_folder else ""
                self.progress.current_file = f"[{folder_tag}] {file_meta.filename}" if folder_tag else file_meta.filename
                try:
                    # Special handling for PDFs: first 30 pages right away
                    if file_meta.extension == ".pdf":
                        from pypdf import PdfReader
                        try:
                            pdf_reader = PdfReader(file_meta.path)
                            num_pages = len(pdf_reader.pages)
                            if num_pages > 30:
                                deferred_long_pdfs.append((file_meta, num_pages))
                                # Only extract first 30 pages right away
                                segments = extract_pdf_file(file_meta.path, max_pages=30)
                            else:
                                segments = extract_pdf_file(file_meta.path, max_pages=5000)
                        except Exception:
                            segments = extract_file_content(file_meta.path)
                    else:
                        segments = extract_file_content(file_meta.path)

                    chunks = chunk_file_segments(file_meta.path, segments)
                    all_chunks: List[Chunk] = []
                    all_vectors: List[np.ndarray] = []

                    # Process text chunks
                    if chunks:
                        # Separate numeric-only chunks from semantic chunks
                        semantic_indices = [i for i, c in enumerate(chunks) if not c.is_numeric_export]
                        doc_prompts = [chunks[i].doc_prompt for i in semantic_indices]

                        if doc_prompts:
                            sem_vectors = self.embedder.embed_documents(doc_prompts, batch_size=config.batch_size)
                        else:
                            sem_vectors = np.empty((0, self.embedder.dim), dtype=np.float32)

                        sem_map = {idx_pos: sem_vectors[j] for j, idx_pos in enumerate(semantic_indices)}
                        for i, chunk in enumerate(chunks):
                            all_chunks.append(chunk)
                            if chunk.is_numeric_export:
                                # Matched by exact text in SQLite FTS5 only
                                all_vectors.append(np.zeros(self.embedder.dim, dtype=np.float32))
                            else:
                                all_vectors.append(sem_map[i])

                    # Multimodal embedding for visual/audio/video files
                    if file_meta.extension in IMAGE_EXTS:
                        try:
                            img_vec = self.embedder.embed_image(file_meta.path)
                            img_chunk = Chunk(
                                chunk_index=len(all_chunks),
                                text=f"Image photo: {file_meta.filename}",
                                title=file_meta.filename,
                                loc_start=1,
                                loc_end=1,
                                label="Visual Content",
                                doc_prompt=f"title: {file_meta.filename} | text: Image photo visual content",
                            )
                            all_chunks.append(img_chunk)
                            all_vectors.append(img_vec)
                        except Exception as e:
                            print(f"[IndexManager] Error embedding image {file_meta.path}: {e}")

                    elif file_meta.extension in AUDIO_EXTS:
                        try:
                            # Audio of any length: overlapping 30-second windows pointing to moments
                            windows = self.embedder.extract_audio_windows(file_meta.path, window_sec=30.0, hop_sec=15.0)
                            for start_sec, end_sec, samples in windows:
                                aud_vec = self.embedder.embed_audio_slice(samples)
                                time_str = format_timestamp(start_sec)
                                dur_str = format_timestamp(end_sec - start_sec)
                                aud_chunk = Chunk(
                                    chunk_index=len(all_chunks),
                                    text=f"Audio: {file_meta.filename} at {time_str} ({dur_str})",
                                    title=file_meta.filename,
                                    loc_start=int(start_sec),
                                    loc_end=int(end_sec),
                                    label=f"▶ {time_str}",
                                    doc_prompt=f"title: {file_meta.filename} | text: Audio recording at {time_str}",
                                )
                                all_chunks.append(aud_chunk)
                                all_vectors.append(aud_vec)
                        except Exception as e:
                            print(f"[IndexManager] Error embedding audio {file_meta.path}: {e}")

                    elif file_meta.extension in VIDEO_EXTS:
                        try:
                            # Video of any length: frames every few seconds + soundtrack in 30s windows
                            frames = self.embedder.extract_video_frames(file_meta.path, interval_sec=3.0, max_frames=60)
                            for pts_sec, frame_img in frames:
                                f_vec = self.embedder.embed_image(frame_img)
                                time_str = format_timestamp(pts_sec)
                                vid_chunk = Chunk(
                                    chunk_index=len(all_chunks),
                                    text=f"Video scene: {file_meta.filename} at {time_str}",
                                    title=file_meta.filename,
                                    loc_start=int(pts_sec),
                                    loc_end=int(pts_sec + 3),
                                    label=f"🎬 {time_str}",
                                    doc_prompt=f"title: {file_meta.filename} | text: Video scene at {time_str}",
                                )
                                all_chunks.append(vid_chunk)
                                all_vectors.append(f_vec)

                            # Soundtrack as audio windows
                            sound_windows = self.embedder.extract_audio_windows(file_meta.path, window_sec=30.0, hop_sec=15.0)
                            for start_sec, end_sec, samples in sound_windows:
                                aud_vec = self.embedder.embed_audio_slice(samples)
                                time_str = format_timestamp(start_sec)
                                trk_chunk = Chunk(
                                    chunk_index=len(all_chunks),
                                    text=f"Video soundtrack: {file_meta.filename} at {time_str}",
                                    title=file_meta.filename,
                                    loc_start=int(start_sec),
                                    loc_end=int(end_sec),
                                    label=f"🎵 {time_str}",
                                    doc_prompt=f"title: {file_meta.filename} | text: Video soundtrack at {time_str}",
                                )
                                all_chunks.append(trk_chunk)
                                all_vectors.append(aud_vec)
                        except Exception as e:
                            print(f"[IndexManager] Error embedding video {file_meta.path}: {e}")

                    # Store in database if chunks exist
                    if all_chunks and all_vectors:
                        vectors_matrix = np.vstack(all_vectors)
                        self.store.record_indexed_file(
                            path=file_meta.path,
                            filename=file_meta.filename,
                            extension=file_meta.extension,
                            size=file_meta.size,
                            mtime=file_meta.mtime,
                            chunks=all_chunks,
                            vectors=vectors_matrix,
                            indexed_at=time.time(),
                        )
                        self.progress.chunks_created += len(all_chunks)

                except Exception as e:
                    print(f"[IndexManager] Error processing {file_meta.path}: {e}")

                self.progress.files_indexed += 1

            # 4. Deferred indexing for remaining pages of long PDFs
            if deferred_long_pdfs and not self._cancel_flag.is_set():
                print(f"[IndexManager] Processing deferred pages for {len(deferred_long_pdfs)} long PDFs...")
                for file_meta, total_pg in deferred_long_pdfs:
                    if self._cancel_flag.is_set():
                        break
                    try:
                        self.progress.current_file = f"{file_meta.filename} (pages 31-{min(5000, total_pg)})"
                        full_segments = extract_pdf_file(file_meta.path, max_pages=5000)
                        if len(full_segments) > 30:
                            rem_segments = full_segments[30:]
                            rem_chunks = chunk_file_segments(file_meta.path, rem_segments)
                            if rem_chunks:
                                sem_indices = [i for i, c in enumerate(rem_chunks) if not c.is_numeric_export]
                                doc_prompts = [rem_chunks[i].doc_prompt for i in sem_indices]
                                sem_vecs = self.embedder.embed_documents(doc_prompts, batch_size=config.batch_size) if doc_prompts else np.empty((0, self.embedder.dim), dtype=np.float32)

                                sem_map = {idx_pos: sem_vecs[j] for j, idx_pos in enumerate(sem_indices)}
                                deferred_vecs = []
                                for i, chunk in enumerate(rem_chunks):
                                    if chunk.is_numeric_export:
                                        deferred_vecs.append(np.zeros(self.embedder.dim, dtype=np.float32))
                                    else:
                                        deferred_vecs.append(sem_map[i])

                                # Append to existing file record
                                existing = self.store.get_file(file_meta.path)
                                if existing:
                                    # Fetch existing chunks to update file record with combined set
                                    with self.store.get_connection() as conn:
                                        rows = conn.execute("SELECT * FROM chunks WHERE file_id = ? ORDER BY chunk_index", (existing["id"],)).fetchall()
                                        combined_chunks = []
                                        combined_vecs = []
                                        for r in rows:
                                            combined_chunks.append(
                                                Chunk(
                                                    chunk_index=r["chunk_index"],
                                                    text=r["text"],
                                                    title=r["title"],
                                                    loc_start=r["loc_start"],
                                                    loc_end=r["loc_end"],
                                                    label=r["label"],
                                                    doc_prompt=f"title: {r['title']} | text: {r['text']}",
                                                )
                                            )
                                            combined_vecs.append(self.store.blob_to_vector(r["vector"]))

                                        # Re-index remaining chunks starting from end of existing
                                        start_idx = len(combined_chunks)
                                        for offset, c in enumerate(rem_chunks):
                                            c.chunk_index = start_idx + offset
                                            combined_chunks.append(c)
                                            combined_vecs.append(deferred_vecs[offset])

                                        self.store.record_indexed_file(
                                            path=file_meta.path,
                                            filename=file_meta.filename,
                                            extension=file_meta.extension,
                                            size=file_meta.size,
                                            mtime=file_meta.mtime,
                                            chunks=combined_chunks,
                                            vectors=np.vstack(combined_vecs),
                                            indexed_at=time.time(),
                                        )
                                        self.progress.chunks_created += len(rem_chunks)
                    except Exception as e:
                        print(f"[IndexManager] Error processing deferred pages for {file_meta.path}: {e}")

            self.progress.status = "done"
            print(f"[IndexManager] Indexing complete: {self.progress.files_indexed} files, {self.progress.chunks_created} chunks.")

            if self.on_index_complete:
                self.on_index_complete()

        except Exception as e:
            self.progress.status = "error"
            self.progress.error_message = str(e)
            print(f"[IndexManager] Fatal error during indexing: {e}")
