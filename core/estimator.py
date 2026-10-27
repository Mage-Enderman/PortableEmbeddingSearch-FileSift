"""
Fast pre-indexing scanner and time/resource estimator.
Inspects folder metadata without loading models or heavy decoders,
calculating estimated file counts, processing durations, and database size.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional
from core.extractors import IMAGE_EXTS, AUDIO_EXTS, VIDEO_EXTS
from core.config import DEFAULT_EXCLUDED_PATTERNS


# Estimated processing seconds per unit
# (Calibrated based on benchmarks: GPU with CUDA vs CPU)
GPU_RATES = {
    "image": 0.08,        # ~12 images/sec with batching
    "pdf": 0.15,          # ~0.05s per page avg, typical 3-5 pages
    "doc": 0.04,          # text extraction + chunk embedding
    "code": 0.03,         # source code chunk embedding
    "video": 0.8,         # sample shots/keyframes + soundtrack
    "audio": 0.3,         # 30-sec sliding window audio embedding
}

CPU_RATES = {
    "image": 0.65,
    "pdf": 0.50,
    "doc": 0.15,
    "code": 0.12,
    "video": 3.5,
    "audio": 1.2,
}

DOC_EXTS = {".txt", ".md", ".markdown", ".rst", ".org", ".typ", ".rtf", ".odt", ".html", ".htm", ".docx", ".xlsx", ".ods", ".pptx", ".odp", ".csv", ".tsv"}
CODE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".scss", ".json", ".yaml", ".yml", ".toml", ".xml", ".sql", ".rs", ".go", ".c", ".cpp", ".h", ".hpp", ".cs", ".java", ".kt", ".swift", ".sh", ".bash", ".ps1", ".bat", ".cmd"}


def classify_extension(ext: str) -> str:
    ext = ext.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext == ".pdf":
        return "pdf"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in CODE_EXTS:
        return "code"
    if ext in DOC_EXTS:
        return "doc"
    return "other"


def get_standard_user_folders() -> List[Dict]:
    """Discovers standard user profile directories on Windows."""
    user_home = Path.home()
    standard_names = [
        ("Documents", "Documents"),
        ("Pictures", "Pictures"),
        ("Videos", "Videos"),
        ("Downloads", "Downloads"),
        ("Desktop", "Desktop"),
        ("Code", "Projects / Repos"),
    ]

    folders = []
    for dir_name, display_label in standard_names:
        candidate = user_home / dir_name
        if candidate.exists() and candidate.is_dir():
            folders.append({
                "path": str(candidate),
                "name": candidate.name,
                "label": display_label,
                "exists": True,
            })
    return folders


def estimate_folder_workload(
    folder_path: str,
    excluded_patterns: Optional[List[str]] = None,
    is_gpu: bool = True,
    max_files_scan: int = 25000,
) -> Dict:
    """
    Scans a folder rapidly to tally file types and estimate indexing time and index size.
    """
    path = Path(folder_path)
    if not path.exists() or not path.is_dir():
        return {
            "path": folder_path,
            "exists": False,
            "total_files": 0,
            "counts": {},
            "estimated_seconds": 0.0,
            "estimated_size_mb": 0.0,
        }

    excludes = set(excluded_patterns or DEFAULT_EXCLUDED_PATTERNS)
    counts = {"image": 0, "pdf": 0, "doc": 0, "code": 0, "video": 0, "audio": 0, "other": 0}
    total_scanned = 0
    total_bytes = 0

    rates = GPU_RATES if is_gpu else CPU_RATES

    try:
        for root, dirs, files in os.walk(str(path)):
            # Prune excluded directories
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".") and d not in excludes and not any(p in d for p in excludes)
            ]

            for f in files:
                if f.startswith("."):
                    continue
                ext = os.path.splitext(f)[1]
                category = classify_extension(ext)
                if category != "other":
                    counts[category] += 1
                    total_scanned += 1
                    try:
                        total_bytes += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass

                if total_scanned >= max_files_scan:
                    break
            if total_scanned >= max_files_scan:
                break
    except Exception as e:
        print(f"[Estimator] Scan error for {folder_path}: {e}")

    # Estimate time
    estimated_seconds = sum(counts[cat] * rates.get(cat, 0.05) for cat in counts)

    # Estimate SQLite index size (~8KB per chunk/vector, avg 1.5 chunks per file)
    estimated_chunks = (
        counts["image"] * 1
        + counts["pdf"] * 4
        + counts["doc"] * 3
        + counts["code"] * 2
        + counts["video"] * 5
        + counts["audio"] * 4
    )
    estimated_size_mb = (estimated_chunks * 8.5) / 1024.0

    return {
        "path": str(path),
        "exists": True,
        "total_files": total_scanned,
        "counts": counts,
        "estimated_seconds": round(estimated_seconds, 1),
        "estimated_size_mb": round(estimated_size_mb, 1),
    }
