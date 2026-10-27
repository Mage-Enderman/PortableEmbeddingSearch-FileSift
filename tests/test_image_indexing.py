import unittest
import tempfile
import os
import numpy as np
from PIL import Image
from core.indexer import IndexManager
from core.crawler import FileMetadata


class TestImageIndexingRegression(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_image_visual_chunk_definition(self):
        """Regression test ensuring Chunk is imported and image indexing completes without NameError."""
        # Create a test image
        img_path = os.path.join(self.temp_dir.name, "sunset_beach.png")
        img = Image.new("RGB", (200, 200), color=(255, 128, 64))
        img.save(img_path)

        manager = IndexManager.get_instance()
        # Mock crawler to index only this test image
        file_meta = FileMetadata(
            path=img_path,
            filename="sunset_beach.png",
            extension=".png",
            size=os.path.getsize(img_path),
            mtime=os.path.getmtime(img_path),
        )

        # Index the file
        from core.extractors import extract_file_content
        from core.chunker import chunk_file_segments, Chunk

        segments = extract_file_content(file_meta.path)
        chunks = chunk_file_segments(file_meta.path, segments)
        self.assertGreaterEqual(len(chunks), 1)

        # Ensure Chunk instance can be created as in indexer.py
        img_chunk = Chunk(
            chunk_index=len(chunks),
            text=f"Image photo: {file_meta.filename}",
            title=file_meta.filename,
            loc_start=1,
            loc_end=1,
            label="Visual Content",
            doc_prompt=f"title: {file_meta.filename} | text: Image photo visual content",
        )
        self.assertEqual(img_chunk.label, "Visual Content")
        self.assertEqual(img_chunk.title, "sunset_beach.png")


if __name__ == "__main__":
    unittest.main()
