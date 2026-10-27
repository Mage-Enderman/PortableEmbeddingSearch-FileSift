import pytest
import os
import tempfile
from pathlib import Path
from core.estimator import classify_extension, estimate_folder_workload, get_standard_user_folders
from core.opener import open_result_at, get_detected_editor
from core.indexer import IndexManager


def test_classify_extension():
    assert classify_extension(".png") == "image"
    assert classify_extension(".webp") == "image"
    assert classify_extension(".pdf") == "pdf"
    assert classify_extension(".mp4") == "video"
    assert classify_extension(".wav") == "audio"
    assert classify_extension(".py") == "code"
    assert classify_extension(".docx") == "doc"
    assert classify_extension(".unknownxyz") == "other"


def test_get_standard_user_folders():
    folders = get_standard_user_folders()
    assert isinstance(folders, list)
    # On Windows, at least Documents or Desktop or Downloads should exist in user profile
    for f in folders:
        assert "path" in f
        assert "name" in f
        assert Path(f["path"]).exists()


def test_estimate_folder_workload():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "img1.jpg").write_bytes(b"dummy image")
        (tmp_path / "notes.txt").write_text("dummy text")
        (tmp_path / "script.py").write_text("print('hello')")

        workload = estimate_folder_workload(str(tmp_path), is_gpu=True)
        assert workload["exists"] is True
        assert workload["total_files"] == 3
        assert workload["counts"]["image"] == 1
        assert workload["counts"]["doc"] == 1
        assert workload["counts"]["code"] == 1
        assert workload["estimated_seconds"] > 0
        assert workload["estimated_size_mb"] >= 0


def test_indexer_pause_and_resume():
    mgr = IndexManager.get_instance()
    mgr.pause_indexing()
    assert mgr.is_paused() is True
    assert mgr.progress.is_paused is True

    mgr.resume_indexing()
    assert mgr.is_paused() is False
    assert mgr.progress.is_paused is False


def test_open_result_at_nonexistent():
    # Should safely return False for non-existent file
    assert open_result_at("C:\\non_existent_folder_xyz_123\\test.txt") is False
