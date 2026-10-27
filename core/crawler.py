import os
from pathlib import Path
from collections import deque
from typing import List, Dict, Tuple, Set, Optional
from core.config import config
from core.index_store import IndexStore


class FileMetadata:
    def __init__(
        self,
        path: str,
        filename: str,
        extension: str,
        size: int,
        mtime: float,
        root_folder: str = "",
    ):
        self.path = os.path.normpath(path)
        self.filename = filename
        self.extension = extension
        self.size = size
        self.mtime = mtime
        self.root_folder = os.path.normpath(root_folder) if root_folder else os.path.dirname(self.path)

    def __repr__(self):
        return f"<FileMeta {self.filename} ({self.size} bytes) in {self.root_folder}>"


class Crawler:
    def __init__(self, index_store: Optional[IndexStore] = None):
        self.store = index_store or IndexStore()

    def should_skip_dir(self, dir_name: str) -> bool:
        """Determines if a directory should be skipped."""
        for pattern in config.excluded_patterns:
            if pattern.lower() == dir_name.lower():
                return True
            if dir_name.startswith(".") and pattern.startswith("."):
                return True
        return False

    def is_allowed_file(self, filename: str, size: int) -> bool:
        """Validates file extension and size constraints."""
        max_bytes = config.max_file_size_mb * 1024 * 1024
        if size > max_bytes or size == 0:
            return False

        ext = Path(filename).suffix.lower()
        return ext in [e.lower() for e in config.allowed_extensions]

    def scan_chosen_folders(self) -> List[FileMetadata]:
        """Recursively scans all folders in chosen_folders, tagging each file with its root chosen folder."""
        discovered: List[FileMetadata] = []
        seen_paths: Set[str] = set()

        for folder in config.chosen_folders:
            folder_path = Path(folder)
            if not folder_path.exists() or not folder_path.is_dir():
                continue

            norm_root = os.path.normpath(str(folder_path))
            for root, dirs, files in os.walk(folder_path, topdown=True):
                # Filter directories in-place to avoid descending into ignored folders
                dirs[:] = [d for d in dirs if not self.should_skip_dir(d)]

                for f in files:
                    full_path = os.path.normpath(os.path.join(root, f))
                    if full_path in seen_paths:
                        continue

                    try:
                        stat = os.stat(full_path)
                        if self.is_allowed_file(f, stat.st_size):
                            seen_paths.add(full_path)
                            discovered.append(
                                FileMetadata(
                                    path=full_path,
                                    filename=f,
                                    extension=Path(f).suffix.lower(),
                                    size=stat.st_size,
                                    mtime=stat.st_mtime,
                                    root_folder=norm_root,
                                )
                            )
                    except (PermissionError, OSError):
                        continue

        return discovered

    @staticmethod
    def schedule_staggered(files: List[FileMetadata], batch_size: int = 5) -> List[FileMetadata]:
        """
        Prioritizes smaller folders and staggers indexing across all folders:
        1. Groups files by their root chosen folder.
        2. Sorts files within each folder by size (smaller, quick files first).
        3. Sorts folders by file count so smaller folders are front-loaded and finish fast.
        4. Interleaves files across all folders in round-robin batches so every folder
           makes steady progress and is searchable immediately without starvation.
        """
        if not files:
            return []

        by_folder: Dict[str, List[FileMetadata]] = {}
        for f in files:
            by_folder.setdefault(f.root_folder, []).append(f)

        # Sort files within each folder by size ascending (smaller, faster files first)
        for fld, f_list in by_folder.items():
            f_list.sort(key=lambda x: x.size)

        # Sort folders by number of files ascending (smaller folders first)
        sorted_folders = sorted(by_folder.keys(), key=lambda k: len(by_folder[k]))
        queues = {k: deque(by_folder[k]) for k in sorted_folders}

        staggered: List[FileMetadata] = []
        while any(queues.values()):
            for fld in sorted_folders:
                q = queues[fld]
                if not q:
                    continue
                # Take up to batch_size files from this folder
                take_count = min(batch_size, len(q))
                for _ in range(take_count):
                    staggered.append(q.popleft())

        return staggered

    def detect_changes(self) -> Tuple[List[FileMetadata], List[str], List[FileMetadata]]:
        """
        Compares disk state with SQLite index store.
        Returns: (staggered_to_index, to_remove_paths, unchanged)
        """
        disk_files = self.scan_chosen_folders()
        indexed_files = self.store.get_all_indexed_paths()

        to_index: List[FileMetadata] = []
        unchanged: List[FileMetadata] = []
        disk_paths_set: Set[str] = set()

        for f in disk_files:
            disk_paths_set.add(f.path)
            if f.path not in indexed_files:
                to_index.append(f)
            else:
                idx_mtime, idx_size = indexed_files[f.path]
                # Compare modified time and size
                if abs(f.mtime - idx_mtime) > 0.001 or f.size != idx_size:
                    to_index.append(f)
                else:
                    unchanged.append(f)

        to_remove_paths = [p for p in indexed_files if p not in disk_paths_set]

        # Prioritize smaller folders and stagger across all folders
        staggered_to_index = self.schedule_staggered(to_index, batch_size=5)
        return staggered_to_index, to_remove_paths, unchanged
