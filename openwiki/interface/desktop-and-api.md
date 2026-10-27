---
type: concept
title: FastAPI Service and Desktop Interface
description: Architecture of the FastAPI HTTP service, REST endpoints, thumbnail generator, desktop window initialization via PyWebView and Edge App Mode, and web frontend interactions.
tags: [fastapi, desktop, webview, edge, thumbnails, rest-api, spotlight-ui]
verified:
  - by: openwiki/0.7.2
    at: 2026-10-27T03:41:19.738Z
sources:
  - id: openwiki-source-a601820994003952e250337a
    resource: repo://desktop.py
  - id: openwiki-source-364834e1e8d420191514fe75
    resource: repo://server/api.py
generated: { by: "antigravity", at: "2026-10-27T03:41:19.738Z" }
---

# FastAPI Service and Desktop Interface

FileSift pairs a local FastAPI HTTP backend with a lightweight desktop container that runs either as an embedded desktop window (via `pywebview` or Microsoft Edge App Mode) or directly in any modern web browser.

```
+-----------------------------------------------------------------------------------+
| Desktop Entrypoint (desktop.py)                                                  |
|  - Dynamic port binding (8501..8550) via socket probing                           |
|  - Background daemon thread runs uvicorn (server.api:app)                         |
|  - Embedded PyWebView (edgechromium GUI) or Edge App Mode (--app=http://...)     |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| FastAPI Service (server/api.py)                                                   |
|  - GET  /api/status            -> Hardware, device, index stats, progress        |
|  - GET  /api/device            -> GPU/CPU memory & device info                   |
|  - POST /api/device            -> Dynamic device migration                       |
|  - GET  /api/folders           -> List chosen folders and file counts            |
|  - POST /api/folders/add       -> Register folder and trigger crawler            |
|  - POST /api/folders/browse    -> Native Windows folder picker (Tkinter)         |
|  - GET  /api/search            -> Natural language hybrid RRF search             |
|  - POST /api/search-media      -> Multimodal query upload with inverse concepts   |
|  - GET  /api/thumbnail         -> Cached Lanczos thumbnail extraction            |
|  - POST /api/open-file         -> Launch default Windows application             |
|  - POST /api/open-folder       -> Reveal & highlight file in Windows Explorer     |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| Web Frontend (server/static/)                                                     |
|  - Spotlight-style search bar with camera upload and clipboard paste (Ctrl+V)    |
|  - Toggleable Photo Grid (masonry) and traditional ranked list views              |
|  - Side preview drawer and direct Windows Explorer interaction                   |
+-----------------------------------------------------------------------------------+
```

---

## 1. Desktop Window and Server Lifecycle

Execution begins in `desktop.py`:

### Dynamic Port Discovery (`find_free_port`)
The server probes `127.0.0.1` starting at port 8501 across 50 consecutive ports using TCP socket connects. Once an unbound port is secured, `uvicorn.run(app, host="127.0.0.1", port=port)` starts inside a dedicated background daemon thread.

### Embedded GUI and Fallback Launchers
1. **PyWebView**: Attempts to instantiate an embedded native window using the Edge Chromium (WebView2) runtime (`webview.create_window`, `gui="edgechromium"`).
2. **Edge App Mode Fallback (`launch_edge_app`)**: If `pywebview` is unavailable or fails initialization, the script searches standard installation paths for `msedge.exe` (in `ProgramFiles`, `ProgramFiles(x86)`, and `LocalAppData`) and launches Edge with the flags:
   ```cmd
   msedge.exe --app=http://127.0.0.1:{port} --window-size=860,740
   ```
   This presents the UI without address bars, tabs, or browser chrome, behaving as a native Windows utility.
3. **Browser Mode (`--browser`)**: When passed via CLI or `run_browser.bat`, the app opens the default browser using Python's `webbrowser.open(url)`.

---

## 2. REST API Endpoints

The API is exposed via FastAPI in `server/api.py`:

### Index and Folder Management
- `GET /api/folders`: Queries SQLite to return each configured directory, validation status, and indexed file count.
- `POST /api/folders/browse`: Opens a native Windows directory selector dialog via an invisible, topmost Tkinter root window, preventing manual path entry errors.
- `POST /api/folders/add`: Appends the normalized folder to `AppConfig` and starts background indexing if the indexer is idle.
- `POST /api/folders/remove`: Removes the directory and deletes all associated indexed file records and vectors from the database, followed by a searcher vector cache reload.
- `GET /api/index/progress`: Streams current file status, processed count, percentage, and chunk metrics to the UI progress bar.

### Query and Search Endpoints
- `GET /api/search`: Accepts text query string `q`, filter `kind` (`all`, `docs`, `code`, `notes`, `images`), and limit count. Runs full hybrid Reciprocal Rank Fusion.
- `POST /api/search-media`: Handles multipart file uploads (image, audio, or video). Computes the 512d query vector and supports optional negative media/concepts (`neg_file` or `neg_query`) and file extension exclusion filters.
- `POST /api/search-media-path`: Executes vector search using an already-indexed or on-disk local media file path.

### Media Streaming and Thumbnail Cache
- `GET /api/thumbnail`: Employs a deterministic caching scheme in `data/thumbnails/{hash}_{timestamp}_{mtime}_{size}.jpg`.
  - For image formats, it loads through Pillow and generates a Lanczos-resampled JPEG.
  - For video files, it decodes via PyAV to extract the exact frame closest to the specified `timestamp`.
  - Serves cached images with HTTP `Cache-Control: public, max-age=86400`.
- `GET /api/stream-media`: Streams audio and video containers directly to the client with appropriate MIME headers (`video/mp4`, `audio/wav`, etc.) for in-browser preview playback.

---

## 3. Desktop Shell Integration

### File Opening (`/api/open-file`)
Uses `os.startfile(path)` to delegate opening the document to whatever default Windows program is registered for the extension (e.g. VS Code, Word, Photos, Media Player).

### Explorer Reveal (`/api/open-folder`)
Rather than passing tokenized lists through `subprocess.Popen` (which can suffer from argument mangling under Windows list2cmdline rules), FileSift passes a literal command string:
```python
subprocess.Popen(f'explorer.exe /select,"{path}"')
```
This causes Windows File Explorer to open the parent folder and pre-highlight the target file without triggering default library fallbacks.
