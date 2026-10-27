import os
import unittest
from fastapi.testclient import TestClient
from server.api import app, config


class TestAPIEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_status(self):
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertEqual(data["status"], "online")
        self.assertIn("total_files", data)
        self.assertIn("total_chunks", data)
        self.assertIn("device", data)
        self.assertIn("cuda_available", data)

    def test_get_folders(self):
        response = self.client.get("/api/folders")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("chosen_folders", data)
        self.assertIn("excluded_patterns", data)

    def test_device_switch(self):
        # Read current device
        dev_res = self.client.get("/api/device")
        self.assertEqual(dev_res.status_code, 200)
        info = dev_res.json()
        self.assertIn("current_device", info)

        # Switch to CPU
        cpu_res = self.client.post("/api/device", json={"device": "cpu"})
        self.assertEqual(cpu_res.status_code, 200)
        self.assertEqual(cpu_res.json()["current_device"], "cpu")

        # Switch back to CUDA if available
        if info["cuda_available"]:
            gpu_res = self.client.post("/api/device", json={"device": "cuda"})
            self.assertEqual(gpu_res.status_code, 200)
            self.assertEqual(gpu_res.json()["current_device"], "cuda")

    def test_search_with_modifiers(self):
        res = self.client.get("/api/search?q=test+!json+-pdf")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("results", data)

    def test_open_folder_existing(self):
        from unittest.mock import patch
        readme_path = os.path.abspath("README.md")
        with patch("subprocess.Popen") as mock_popen:
            res = self.client.post("/api/open-folder", json={"path": readme_path})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], "revealed")
            mock_popen.assert_called_once()
            called_cmd = mock_popen.call_args[0][0]
            self.assertIn("explorer.exe /select,", called_cmd)


if __name__ == "__main__":
    unittest.main()
