# FileSift • Portable Embedding Search

> **Describe it. Sift it out.**  
> Search the files on your computer by what's inside them, powered on-device by Google DeepMind's **EmbeddingGemma 2** multimodal embedding model. Inspired by [ARahim3/DigUp](https://github.com/ARahim3/DigUp).

---

## ⚡ Highlights

- **Natural Language & Multimodal Search:**
  - Search files using plain text descriptions (e.g. *"payment error with exponential backoff"*, *"sunset on the beach"*, *"pet policy clause"*).
  - **Search by Media Input:** Drop, upload, or paste (`Ctrl+V`) an **image, audio recording, or video clip** to find conceptually or visually similar files on your computer!
- **Photo Grid View & Previews:**
  - View results in a **Photo Grid** (⊞) or traditional **List View** (📑).
  - Real-time thumbnail generator displays instant previews for photos, screenshots, and video frames.
  - Full support for **WEBP, AVIF, JXL (JPEG XL), HEIC/HEIF, PNG, JPG, BMP, GIF, and TIFF**.
- **Google DeepMind's EmbeddingGemma 2:**
  - Uses `google/embeddinggemma-2` with official task prefixes (`task: search result | query: ...`) and 512d Matryoshka dimension truncation.
  - Native unified vector space across text, images, audio, and video.
- **Hybrid Search Engine:**
  - Combines dense semantic vector similarity with SQLite FTS5 (BM25) full-text keyword indexing via Reciprocal Rank Fusion (RRF).
- **Choose Folders to Index:**
  - Pick any directories to search. The background crawler monitors file changes (`mtime` and `size`) and incrementally re-indexes only modified files.
- **100% Portable & Private:**
  - Everything runs entirely on-device. All database files, user configurations, and model caches are kept in `./data/`.

---

## 🚀 Quick Start (Windows)

### 1. One-Click Launch
Double-click **`run.bat`** in the application folder.
- Sets up the portable environment automatically if needed.
- Opens FileSift in a standalone native desktop window.

### 2. Browser Mode
Double-click **`run_browser.bat`** (or navigate to `http://localhost:8501`).

---

## 🖼️ Photo Formats & Grid Mode

| Format | Supported? | Details |
|---|:---:|---|
| **WEBP** | ✅ Yes | Natively decoded and thumbnailed |
| **AVIF** | ✅ Yes | Enabled via `pillow-heif` and `pillow-avif-plugin` |
| **JXL (JPEG XL)** | ✅ Yes | Enabled via `pillow-jxl-plugin` |
| **HEIC / HEIF** | ✅ Yes | iPhone / camera high-efficiency formats |
| **PNG / JPG / BMP / GIF / TIFF** | ✅ Yes | Standard formats supported |

Click the **⊞ Grid View** button (or the **🖼 Images** filter chip) to display photos in a responsive masonry grid with thumbnail previews, dimensions, and match percentages.

---

## 🎙️ Multimodal Search Inputs (Image, Audio, Video)

You can query using media in 3 easy ways:
1. **Upload Button:** Click the **📷** camera icon in the search bar to choose an image, audio file, or video clip.
2. **Drag & Drop:** Drag any image, audio (`.wav`, `.mp3`), or video (`.mp4`, `.mov`) file directly onto the search window.
3. **Clipboard Paste:** Copy any image to your clipboard and press **Ctrl + V** anywhere in the app.

FileSift will embed the input with EmbeddingGemma 2 and retrieve matching files from your indexed folders.

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + F` or `/` | Focus search bar |
| `Ctrl + V` | Paste image from clipboard as search query |
| `↓` / `↑` | Move through ranked search results |
| `Enter` | Open selected file in its default Windows app |
| `Ctrl + Enter` | Reveal and highlight the file in Windows File Explorer |
| `Space` | Open quick preview drawer for the selected file |
| `Esc` | Clear query / Detach media / Close modal / Close drawer |

---

## 🗂️ Project Structure

```
PortableEmbeddingSearch/
├── core/
│   ├── config.py          # Portable settings & allowed extensions
│   ├── crawler.py         # Directory traversal & change detection
│   ├── extractors.py      # PDF, DOCX, Code, Markdown, AVIF/JXL/WEBP Images, Audio, Video
│   ├── chunker.py         # Adaptive semantic chunking
│   ├── embedder.py        # EmbeddingGemma 2 multimodal inference (text, image, audio, video)
│   ├── index_store.py     # SQLite store with FTS5 BM25 & vector blobs
│   └── searcher.py        # Hybrid search & vector search with RRF
├── server/
│   ├── api.py             # FastAPI REST endpoints (/api/search, /api/thumbnail, /api/search-media)
│   └── static/
│       ├── index.html     # FileSift Spotlight HTML UI (Grid toggle & multimodal input)
│       ├── style.css      # Glassmorphism dark theme & photo grid styling
│       └── app.js         # Interactive search, drag-and-drop & media query handling
├── data/                  # Portable runtime data
│   ├── config.json        # User preferences & chosen folders
│   ├── index.sqlite       # SQLite database & vectors
│   ├── thumbnails/        # Cached JPEG thumbnails
│   └── models/            # Downloaded EmbeddingGemma 2 weights
├── tests/                 # Unit and integration test suite
├── desktop.py             # Desktop window runner (Edge WebView2 / PyWebView)
├── main.py                # Unified CLI entrypoint
├── run.bat                # One-click Windows desktop launcher
├── run_browser.bat        # One-click browser launcher
├── setup.bat              # One-click setup script
└── pyproject.toml         # Project manifest
```
