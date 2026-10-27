---
type: concept
title: Quickstart and System Overview
description: Entry point for FileSift, providing setup commands, CLI operations, configuration reference, architecture summary, and a task routing map across the wiki documentation.
tags: [quickstart, overview, filesift, cli, configuration, navigation]
verified:
  - by: openwiki/0.7.2
    at: 2026-10-27T03:41:19.738Z
sources:
  - id: openwiki-source-27ee44b17a928f4d359d8b25
    resource: repo://core/config.py
  - id: openwiki-source-833e692518af9eeaf8564cc6
    resource: repo://main.py
  - id: openwiki-source-e0ff12d798bbe1ac53358470
    resource: repo://run_browser.bat
  - id: openwiki-source-6e544147c49c8dd10f8d7dc8
    resource: repo://run.bat
generated: { by: "antigravity", at: "2026-10-27T03:41:19.738Z" }
---

# Quickstart and System Overview

**FileSift** is a portable, private, on-device multimodal semantic file search system. Powered by Google DeepMind's **EmbeddingGemma 2** multimodal model and SQLite FTS5 lexical indexing, FileSift allows searching personal files across documents, source code, images, audio clips, and video files using natural language or media inputs.

```
+-----------------------------------------------------------------------------------+
| User Interfaces                                                                   |
|  - Desktop Native Window (PyWebView / Edge App Mode via desktop.py)               |
|  - Web Browser Mode (FastAPI + Vanilla JS Spotlight UI)                           |
|  - Command Line Interface (CLI search and indexing via main.py)                   |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| FileSift Subsystems                                                               |
|  - Crawler & Pipeline: Discovers, staggers, and chunks file contents              |
|  - Embedding Engine: 512d Matryoshka representations for text, visual, & audio    |
|  - Hybrid Storage: SQLite WAL database with FTS5 lexical BM25 & vector BLOBs      |
|  - Hybrid Searcher: Reciprocal Rank Fusion (RRF) with negative concept steering   |
+-----------------------------------------------------------------------------------+
```

---

## 1. Quick Start

### Installation & Environment Setup
Double-click `setup.bat` or run:
```cmd
setup.bat
```
This prepares a local Python virtual environment in `.venv/` and installs dependencies specified in `requirements.txt`.

### Running FileSift
- **Desktop Window Mode**: Double-click `run.bat` (or execute `python desktop.py`). Launches a standalone desktop window using Edge Chromium (WebView2) or Edge App Mode.
- **Browser Mode**: Double-click `run_browser.bat` (or execute `python desktop.py --browser`), then navigate to `http://localhost:8501`.

### Command Line Operations (`main.py`)
FileSift includes CLI tools for automation and headless environments:
- **Run Indexing**:
  ```bash
  python main.py --index
  ```
- **Run Hybrid Search**:
  ```bash
  python main.py --search "payment error with exponential backoff"
  python main.py --search "sunset over the mountains" --kind images
  ```

---

## 2. Directory Structure and Portability

All runtime artifacts, downloaded model weights, and user configuration are isolated in the `./data/` folder, ensuring complete portability:

```
PortableEmbeddingSearch/
├── core/                  # Core search engine & indexing pipeline
│   ├── config.py          # AppConfig and default extensions/exclusions
│   ├── crawler.py         # Directory discovery and staggered scheduler
│   ├── extractors.py      # Format decoders (PDF, DOCX, Code, Media)
│   ├── chunker.py         # 1500-char adaptive text chunking
│   ├── embedder.py        # EmbeddingGemma 2 multimodal inference engine
│   ├── index_store.py     # SQLite schema, FTS5 triggers, vector BLOBs
│   └── searcher.py        # Hybrid RRF search & inverse concept steering
├── server/                # FastAPI service & spotlight frontend
│   ├── api.py             # REST endpoints (/api/search, /api/thumbnail, etc.)
│   └── static/            # Spotlight UI HTML, CSS, and JS
├── data/                  # 100% self-contained portable runtime data
│   ├── config.json        # User preferences & indexed directories
│   ├── index.sqlite       # Database storing metadata, text, and vector blobs
│   ├── thumbnails/        # Cached JPEG image/video frame previews
│   └── models/            # Downloaded EmbeddingGemma 2 weights (HF_HOME)
├── desktop.py             # Port discovery and WebView2/Edge app runner
├── main.py                # Unified CLI entrypoint
├── run.bat                # Windows desktop launcher
├── run_browser.bat        # Windows browser launcher
└── setup.bat              # Environment installation script
```

---

## 3. Configuration Reference (`data/config.json`)

User configurations are managed by `core/config.py:AppConfig`:

| Configuration Key | Default Value | Description |
|---|---|---|
| `chosen_folders` | `[]` | List of directory paths selected by the user for indexing. |
| `excluded_patterns` | `[".git", "node_modules", "__pycache__", ".venv", ...]` | Directory names skipped during recursive crawling. |
| `allowed_extensions` | 50+ extensions (`.txt`, `.py`, `.pdf`, `.webp`, `.mp4`, etc.) | Whitelist of file formats accepted for indexing. |
| `embedding_model` | `"google/embeddinggemma-2"` | HuggingFace model identifier. |
| `embedding_dim` | `512` | Matryoshka dimension truncation (256, 512, or 768). |
| `batch_size` | `16` | Document batch size during embedding generation. |
| `max_file_size_mb` | `25` | Maximum single-file size processed. |
| `device` | `"auto"` | Target compute device (`"auto"`, `"cuda"`, or `"cpu"`). |

---

## 4. Documentation Navigation Map

Follow the links below to explore specific subsystems:

- **[Core Ingestion and Indexing Pipeline](architecture/pipeline.md)**  
  Covers the crawler's directory scanning, differential change detection, staggered round-robin batch scheduling, format extraction (PDF, DOCX, Code, RTF), and adaptive chunking.

- **[EmbeddingGemma 2 Multimodal Inference Engine](embedding/multimodal.md)**  
  Covers the singleton engine lifecycle, FP32/BF16 device resolution, asymmetric query prompt prefixes, Matryoshka dimension truncation, and PyAV temporal sampling for audio and video streams.

- **[Index Storage and Hybrid Search Engine](storage/index-and-search.md)**  
  Covers the SQLite WAL database schema, automated FTS5 synchronization triggers, dense vector BLOB serialization, query modifier parsing, and Reciprocal Rank Fusion (RRF).

- **[FastAPI Service and Desktop Interface](interface/desktop-and-api.md)**  
  Covers REST endpoints, dynamic port allocation, PyWebView initialization with Edge App Mode fallback, and thumbnail caching.
