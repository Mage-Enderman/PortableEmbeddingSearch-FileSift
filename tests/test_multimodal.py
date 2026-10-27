import io
import os
import shutil
import tempfile
import unittest
from PIL import Image
from fastapi.testclient import TestClient

from server.api import app
from core.extractors import IMAGE_EXTS, AUDIO_EXTS, VIDEO_EXTS


class TestMultimodalFeatures(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.test_dir = tempfile.mkdtemp()

        # Create a test image
        self.img_path = os.path.join(self.test_dir, "test_sample.png")
        img = Image.new("RGB", (200, 150), color=(50, 120, 200))
        img.save(self.img_path, format="PNG")

        # Create a test webp image
        self.webp_path = os.path.join(self.test_dir, "test_sample.webp")
        img.save(self.webp_path, format="WEBP")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_format_extensions_supported(self):
        self.assertIn(".webp", IMAGE_EXTS)
        self.assertIn(".avif", IMAGE_EXTS)
        self.assertIn(".jxl", IMAGE_EXTS)
        self.assertIn(".wav", AUDIO_EXTS)
        self.assertIn(".mp4", VIDEO_EXTS)

    def test_thumbnail_endpoint(self):
        # PNG thumbnail
        res_png = self.client.get(f"/api/thumbnail?path={self.img_path}&size=100")
        self.assertEqual(res_png.status_code, 200)
        self.assertEqual(res_png.headers["content-type"], "image/jpeg")

        # WEBP thumbnail
        res_webp = self.client.get(f"/api/thumbnail?path={self.webp_path}&size=100")
        self.assertEqual(res_webp.status_code, 200)
        self.assertEqual(res_webp.headers["content-type"], "image/jpeg")

        # Verify returned data is valid image
        thumb_img = Image.open(io.BytesIO(res_png.content))
        self.assertLessEqual(max(thumb_img.size), 100)

    def test_thumbnail_not_found(self):
        res = self.client.get("/api/thumbnail?path=C:/nonexistent_file_xyz.png")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
