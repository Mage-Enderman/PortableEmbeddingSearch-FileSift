import os
import shutil
import tempfile
import numpy as np
from pathlib import Path
import unittest

from core.extractors import ExtractedSegment, extract_file_content
from core.chunker import chunk_file_segments, Chunk
from core.index_store import IndexStore
from core.searcher import HybridSearcher, SearchResult


class TestExtractorsAndChunker(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_text_extractor(self):
        sample_path = os.path.join(self.test_dir, "sample.py")
        code_content = (
            "def calculate_total(items):\n"
            "    # Calculate sum of items\n"
            "    return sum(item.price for item in items)\n"
        )
        with open(sample_path, "w", encoding="utf-8") as f:
            f.write(code_content)

        segments = extract_file_content(sample_path)
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].loc_start, 1)
        self.assertEqual(segments[0].loc_end, 3)
        self.assertIn("calculate_total", segments[0].text)

    def test_chunker_prompt_format(self):
        segments = [
            ExtractedSegment(text="Line 1\nLine 2\nLine 3", loc_start=1, loc_end=3, label="Lines 1-3")
        ]
        chunks = chunk_file_segments("sample.py", segments)
        self.assertEqual(len(chunks), 1)
        self.assertTrue(chunks[0].doc_prompt.startswith("title: sample.py | text:"))
        self.assertIn("Line 1", chunks[0].doc_prompt)


class TestIndexStoreAndFTS5(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test_index.sqlite"
        self.store = IndexStore(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_vector_blob_roundtrip(self):
        vec = np.random.randn(512).astype(np.float32)
        blob = self.store.vector_to_blob(vec)
        restored = self.store.blob_to_vector(blob)
        np.testing.assert_allclose(vec, restored, rtol=1e-5)

    def test_file_and_fts_indexing(self):
        chunks = [
            Chunk(
                chunk_index=0,
                text="The refund policy requires receipt within 30 days of purchase.",
                title="policy.md",
                loc_start=1,
                loc_end=5,
                label="Lines 1-5",
                doc_prompt="title: policy.md | text: The refund policy requires receipt within 30 days of purchase.",
            ),
            Chunk(
                chunk_index=1,
                text="Authentication tokens expire after 24 hours. Refresh token flow.",
                title="policy.md",
                loc_start=6,
                loc_end=10,
                label="Lines 6-10",
                doc_prompt="title: policy.md | text: Authentication tokens expire after 24 hours.",
            )
        ]
        vectors = np.random.randn(2, 512).astype(np.float32)
        # Normalize vectors
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

        fid = self.store.record_indexed_file(
            path="C:/docs/policy.md",
            filename="policy.md",
            extension=".md",
            size=1024,
            mtime=123456.0,
            chunks=chunks,
            vectors=vectors,
            indexed_at=123456.0,
        )
        self.assertGreater(fid, 0)

        # Test BM25 keyword search
        bm25_res = self.store.bm25_search("refund receipt")
        self.assertGreater(len(bm25_res), 0)
        top_cid = bm25_res[0][0]
        details = self.store.get_chunk_details([top_cid])
        self.assertIn("refund policy", details[top_cid]["text"])

    def test_highlighted_snippet(self):
        text = "DeepMind released EmbeddingGemma 2 for semantic retrieval across local files."
        snippet = HybridSearcher.create_highlighted_snippet(text, "EmbeddingGemma")
        self.assertIn("<mark>EmbeddingGemma</mark>", snippet)


if __name__ == "__main__":
    unittest.main()
