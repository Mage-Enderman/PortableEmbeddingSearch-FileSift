import os
import unittest
from core.crawler import Crawler, FileMetadata


class TestCrawlerFolderStaggering(unittest.TestCase):
    def test_schedule_staggered_prioritizes_small_folders(self):
        # Folder A has 2 small files
        files_a = [
            FileMetadata(path=f"/path/A/f{i}.txt", filename=f"f{i}.txt", extension=".txt", size=100 + i, mtime=1.0, root_folder="/path/A")
            for i in range(2)
        ]
        # Folder B has 12 files
        files_b = [
            FileMetadata(path=f"/path/B/f{i}.txt", filename=f"f{i}.txt", extension=".txt", size=500 + i, mtime=1.0, root_folder="/path/B")
            for i in range(12)
        ]
        # Folder C has 20 files
        files_c = [
            FileMetadata(path=f"/path/C/f{i}.txt", filename=f"f{i}.txt", extension=".txt", size=1000 + i, mtime=1.0, root_folder="/path/C")
            for i in range(20)
        ]

        all_files = files_b + files_c + files_a  # scrambled input order

        staggered = Crawler.schedule_staggered(all_files, batch_size=5)
        self.assertEqual(len(staggered), 2 + 12 + 20)

        norm_a = os.path.normpath("/path/A")
        norm_b = os.path.normpath("/path/B")
        norm_c = os.path.normpath("/path/C")

        # Folder A is the smallest (2 files). It should be completely scheduled in the first 2 slots!
        self.assertEqual(staggered[0].root_folder, norm_a)
        self.assertEqual(staggered[1].root_folder, norm_a)

        # Next should be Folder B (up to 5 files)
        b_batch = [f for f in staggered[2:7]]
        self.assertTrue(all(f.root_folder == norm_b for f in b_batch))

        # Next should be Folder C (up to 5 files)
        c_batch = [f for f in staggered[7:12]]
        self.assertTrue(all(f.root_folder == norm_c for f in c_batch))

        # Folder B gets another turn of 5
        b_batch2 = [f for f in staggered[12:17]]
        self.assertTrue(all(f.root_folder == norm_b for f in b_batch2))

    def test_sorts_files_by_size_within_folder(self):
        # 3 files with different sizes
        files = [
            FileMetadata(path="/path/A/large.pdf", filename="large.pdf", extension=".pdf", size=5000000, mtime=1.0, root_folder="/path/A"),
            FileMetadata(path="/path/A/tiny.txt", filename="tiny.txt", extension=".txt", size=50, mtime=1.0, root_folder="/path/A"),
            FileMetadata(path="/path/A/medium.docx", filename="medium.docx", extension=".docx", size=2000, mtime=1.0, root_folder="/path/A"),
        ]

        staggered = Crawler.schedule_staggered(files, batch_size=5)
        filenames = [f.filename for f in staggered]
        self.assertEqual(filenames, ["tiny.txt", "medium.docx", "large.pdf"])


if __name__ == "__main__":
    unittest.main()
