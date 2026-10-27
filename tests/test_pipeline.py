import os
import shutil
import tempfile
import unittest
import numpy as np
from pathlib import Path

from core.config import config
from core.crawler import Crawler
from core.extractors import extract_file_content
from core.chunker import chunk_file_segments
from core.index_store import IndexStore
from core.searcher import HybridSearcher


class MockEmbedder:
    """Mock embedder providing deterministic normalized vectors for testing."""
    def __init__(self, dim: int = 512):
        self.dim = dim

    def is_loaded(self):
        return True

    def embed_query(self, query: str, is_code: bool = False) -> np.ndarray:
        rng = np.random.RandomState(abs(hash(query)) % (2**31))
        vec = rng.randn(self.dim).astype(np.float32)
        return vec / np.linalg.norm(vec)

    def embed_documents(self, docs, batch_size=16) -> np.ndarray:
        vectors = []
        for d in docs:
            rng = np.random.RandomState(abs(hash(d)) % (2**31))
            vec = rng.randn(self.dim).astype(np.float32)
            vectors.append(vec / np.linalg.norm(vec))
        return np.vstack(vectors)


class TestFullPipeline(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.doc_dir = os.path.join(self.test_dir, "my_documents")
        os.makedirs(self.doc_dir, exist_ok=True)

        self.db_path = Path(self.test_dir) / "test_pipeline.sqlite"
        self.store = IndexStore(db_path=self.db_path)
        self.mock_embedder = MockEmbedder(dim=512)
        self.searcher = HybridSearcher(index_store=self.store, embedder=self.mock_embedder)

        # Create sample files
        self.file1 = os.path.join(self.doc_dir, "auth_service.py")
        with open(self.file1, "w", encoding="utf-8") as f:
            f.write(
                "import time\n"
                "def call_api_with_exponential_backoff(url, retries=5):\n"
                "    for attempt in range(retries):\n"
                "        try:\n"
                "            return request(url)\n"
                "        except ConnectionError:\n"
                "            time.sleep(2 ** attempt)\n"
            )

        self.file2 = os.path.join(self.doc_dir, "pet_policy.md")
        with open(self.file2, "w", encoding="utf-8") as f:
            f.write(
                "# Apartment Lease Pet Policy\n"
                "Tenants are allowed up to two domestic pets. A refundable pet deposit\n"
                "of $300 is required upon signing the lease agreement.\n"
            )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_end_to_end_pipeline(self):
        # 1. Extract & chunk file 1
        segs1 = extract_file_content(self.file1)
        chunks1 = chunk_file_segments(self.file1, segs1)
        vecs1 = self.mock_embedder.embed_documents([c.doc_prompt for c in chunks1])
        stat1 = os.stat(self.file1)
        self.store.record_indexed_file(
            path=self.file1,
            filename=Path(self.file1).name,
            extension=Path(self.file1).suffix,
            size=stat1.st_size,
            mtime=stat1.st_mtime,
            chunks=chunks1,
            vectors=vecs1,
            indexed_at=100.0,
        )

        # 2. Extract & chunk file 2
        segs2 = extract_file_content(self.file2)
        chunks2 = chunk_file_segments(self.file2, segs2)
        vecs2 = self.mock_embedder.embed_documents([c.doc_prompt for c in chunks2])
        stat2 = os.stat(self.file2)
        self.store.record_indexed_file(
            path=self.file2,
            filename=Path(self.file2).name,
            extension=Path(self.file2).suffix,
            size=stat2.st_size,
            mtime=stat2.st_mtime,
            chunks=chunks2,
            vectors=vecs2,
            indexed_at=100.0,
        )

        # 3. Reload cache and search
        self.searcher.refresh_vector_cache()

        # Search for exact code keyword "exponential_backoff"
        results = self.searcher.search("exponential_backoff")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].filename, "auth_service.py")
        self.assertIn("auth_service.py", results[0].path)

        # Search for keyword "pet deposit"
        results2 = self.searcher.search("pet deposit")
        self.assertGreater(len(results2), 0)
        self.assertEqual(results2[0].filename, "pet_policy.md")
        self.assertIn("pet", results2[0].snippet.lower())
        self.assertIn("deposit", results2[0].snippet.lower())

    def test_incremental_change_detection(self):
        # Index file1
        segs1 = extract_file_content(self.file1)
        chunks1 = chunk_file_segments(self.file1, segs1)
        vecs1 = self.mock_embedder.embed_documents([c.doc_prompt for c in chunks1])
        stat1 = os.stat(self.file1)
        self.store.record_indexed_file(
            path=self.file1,
            filename=Path(self.file1).name,
            extension=Path(self.file1).suffix,
            size=stat1.st_size,
            mtime=stat1.st_mtime,
            chunks=chunks1,
            vectors=vecs1,
            indexed_at=100.0,
        )

        crawler = Crawler(self.store)
        config.chosen_folders = [self.doc_dir]

        # 1. detect_changes with file2 not yet indexed
        to_index, to_remove, unchanged = crawler.detect_changes()
        to_index_paths = [f.path for f in to_index]
        unchanged_paths = [f.path for f in unchanged]

        # file1 should be unchanged, file2 should be to_index
        self.assertIn(os.path.normpath(self.file1), unchanged_paths)
        self.assertIn(os.path.normpath(self.file2), to_index_paths)
        self.assertEqual(len(to_remove), 0)

        # 2. Index file2 as well
        stat2 = os.stat(self.file2)
        segs2 = extract_file_content(self.file2)
        chunks2 = chunk_file_segments(self.file2, segs2)
        vecs2 = self.mock_embedder.embed_documents([c.doc_prompt for c in chunks2])
        self.store.record_indexed_file(
            path=self.file2,
            filename=Path(self.file2).name,
            extension=Path(self.file2).suffix,
            size=stat2.st_size,
            mtime=stat2.st_mtime,
            chunks=chunks2,
            vectors=vecs2,
            indexed_at=100.0,
        )

        # Both should now be unchanged
        to_index2, to_remove2, unchanged2 = crawler.detect_changes()
        self.assertEqual(len(to_index2), 0)
        self.assertEqual(len(unchanged2), 2)

        # 3. Modify 1 file: append a line to file1
        with open(self.file1, "a", encoding="utf-8") as f:
            f.write("\n# Modified comment line\n")

        # Now ONLY file1 should be in to_index, file2 must remain unchanged!
        to_index3, to_remove3, unchanged3 = crawler.detect_changes()
        self.assertEqual(len(to_index3), 1)
        self.assertEqual(to_index3[0].path, os.path.normpath(self.file1))
        self.assertEqual(len(unchanged3), 1)
        self.assertEqual(unchanged3[0].path, os.path.normpath(self.file2))


if __name__ == "__main__":
    unittest.main()
