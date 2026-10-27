---
type: architecture
title: Core Ingestion and Indexing Pipeline
description: End-to-end data processing pipeline covering crawler folder scanning, staggered batch scheduling, format extraction, adaptive chunking, and database persistence.
tags: [indexing, crawler, extractors, chunker, index-manager, pipeline]
verified:
  - by: openwiki/0.7.2
    at: 2026-10-27T03:41:19.738Z
sources:
  - id: openwiki-source-d2e0efb1e68df47595e3828a
    resource: repo://core/chunker.py
  - id: openwiki-source-21e1a0d3d45a09fb5ee9ed3e
    resource: repo://core/crawler.py
  - id: openwiki-source-80ca38d6314aa6659a7c03f5
    resource: repo://core/extractors.py
  - id: openwiki-source-0df87428a8e51c52d17e1ca8
    resource: repo://core/indexer.py
generated: { by: "antigravity", at: "2026-10-27T03:41:19.738Z" }
---

# Core Ingestion and Indexing Pipeline

FileSift provides a local, high-throughput ingestion and indexing pipeline designed to turn heterogeneous files—including source code, markdown notes, office documents, scanned PDFs, images, audio clips, and videos—into searchable semantic and lexical records.

```
+-----------------------------------------------------------------------------------+
|                                 Chosen Folders                                    |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| Crawler                                                                           |
|  - Directory traversal with exclusion pattern filtering                           |
|  - Change detection (mtime & file size comparison vs SQLite files table)          |
|  - Staggered round-robin scheduling (prioritizes small folders, prevents lag)     |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| Content Extractors & Adaptive Chunker                                             |
|  - Text/Code/Markdown (line-numbered segments)                                    |
|  - Office/PDF/HTML/RTF (structured paragraphs and page numbering)                |
|  - Fast numeric density classifier (is_mostly_numbers)                            |
|  - Chunking bounded to 1500 characters with 200 character overlap                 |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| Multimodal Ingestion & Embedding                                                  |
|  - EmbeddingGemma 2 inference engine (512d Matryoshka vectors)                    |
|  - Dense document task formatting ("title: {title} | text: {content}")            |
|  - Pure numeric chunks zero-vectored (routed solely to FTS5)                      |
|  - Image, audio slice (16kHz), and video frame extraction via PyAV                |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| IndexStore Persistence                                                            |
|  - SQLite WAL mode files & chunks tables                                          |
|  - FTS5 virtual table synchronized via SQLite insert/update/delete triggers       |
|  - Float32 vector BLOB serialization                                              |
+-----------------------------------------------------------------------------------+
```

---

## 1. Directory Traversal and Change Detection

The ingestion process starts within `core/crawler.py`. The `Crawler` scans user-configured directories listed in `config.chosen_folders`.

### Directory and File Filtering
- **Directory Exclusion**: During `os.walk`, subdirectories matching `config.excluded_patterns` (such as `.git`, `node_modules`, `__pycache__`, `.venv`, `.idea`, `dist`, `build`) are pruned in-place to prevent recursive traversal of dependency trees or system caches.
- **File Validation**: Files are checked against `config.allowed_extensions` and `config.max_file_size_mb` (default 25 MB). Zero-byte files or files exceeding the threshold are excluded from indexing.

### Differential Change Detection
The `detect_changes()` method inspects existing index records from SQLite via `store.get_all_indexed_paths()`, which maps known file paths to their indexed `(mtime, size)` tuples.
- **Added Files**: Any scanned file not present in the index map is marked for ingestion.
- **Modified Files**: If a file's current modified timestamp differs from `idx_mtime` by more than 1 millisecond (`abs(f.mtime - idx_mtime) > 0.001`) or if its byte size has changed, it is scheduled for re-indexing.
- **Deleted Files**: Paths recorded in the database that no longer exist on disk are gathered in `to_remove_paths` and immediately deleted from the SQLite database.
- **Unchanged Files**: Files whose metadata matches are preserved without redundant processing.

---

## 2. Staggered Scheduling Algorithm

To provide immediate search responsiveness across large file trees, `schedule_staggered()` organizes discovered files before ingestion begins:

1. **Folder Grouping**: Files are partitioned by their root chosen directory (`f.root_folder`).
2. **Size Sorting**: Inside each directory group, files are sorted ascending by size so lightweight files (text files, code, concise documents) complete rapidly.
3. **Folder Prioritization**: Folders are ordered by their file count ascending, so smaller directories finish indexing and become searchable first.
4. **Round-Robin Batch Interleaving**: The crawler pulls files in round-robin batches (default batch size of 5 files per folder) across all directory queues. This interleaving guarantees that larger folders cannot starve other directories from making visible progress.

---

## 3. Format Extraction and Chunking

Extracted text is processed by `core/extractors.py` and structured into `ExtractedSegment` instances:

- **Text and Code (`extract_text_file`)**: Reads UTF-8, UTF-8-sig, CP1252, or Latin-1 encodings and produces line-indexed segments.
- **PDF Documents (`extract_pdf_file`)**: Extracts text page-by-page using `pypdf`. For initial passes, PDFs over 30 pages extract the first 30 pages immediately, deferring remaining pages so indexing is not blocked. Scanned pages with embedded images are tagged for visual indexation.
- **DOCX Documents (`extract_docx_file`)**: Parses structured paragraphs via `python-docx`.
- **RTF, ODT, HTML**: Strips presentation markup to extract clean paragraph text.
- **Numeric Density Filtering**: `is_mostly_numbers()` checks if alphanumeric characters contain $\ge 35\%$ digits. Tables or numeric dumps are flagged as `is_numeric_export`.

### Adaptive Chunking
`core/chunker.py:chunk_file_segments()` converts segments into indexable `Chunk` units:
- Segments under 1,500 characters form a single chunk.
- Larger segments are split along line boundaries up to 1,500 characters with a 200-character overlap window.
- Each chunk preserves exact location boundaries (`loc_start`, `loc_end`) and formatted document prompts: `"title: {filename} | text: {chunk_text}"`.

---

## 4. Background Execution via IndexManager

The lifecycle is orchestrated by `core/indexer.py:IndexManager`, implemented as a singleton:

- **Thread Concurrency**: Indexing executes on a background daemon thread managed by `IndexManager._thread` guarded by a reentrant `threading.Lock`.
- **Progress Tracking**: `IndexingProgress` records status (`idle`, `scanning`, `loading_model`, `indexing`, `done`, `cancelled`, `error`), currently indexed file name, count of indexed files, percentage, and chunk count.
- **Cooperative Cancellation**: An internal `threading.Event` (`_cancel_flag`) is checked before processing each file, allowing clean termination from the UI or API.
- **Cache Refresh**: On completion, `indexer.on_index_complete` triggers `HybridSearcher.refresh_vector_cache()` to reload in-memory vector representations for fast vector cosine similarity.
