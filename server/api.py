import io
import os
import shutil
import tempfile
import subprocess
import threading
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, Query, HTTPException, Body, File, UploadFile, Response, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image

from core.config import config, APP_ROOT, DATA_DIR
from core.index_store import IndexStore
from core.embedder import EmbeddingGemmaEngine
from core.indexer import IndexManager
from core.searcher import HybridSearcher
from core.extractors import IMAGE_EXTS, AUDIO_EXTS, VIDEO_EXTS

# Thumbnail cache directory
THUMBNAILS_DIR = DATA_DIR / "thumbnails"
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)


app = FastAPI(title="FileSift Semantic Search", version="0.1.0")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core singletons
index_store = IndexStore()
embedder = EmbeddingGemmaEngine.get_instance()
searcher = HybridSearcher(index_store, embedder)
indexer = IndexManager.get_instance()

# Refresh searcher vectors whenever indexing finishes
indexer.on_index_complete = searcher.refresh_vector_cache

STATIC_DIR = Path(__file__).resolve().parent / "static"


# Request / Response Models
class FolderRequest(BaseModel):
    path: str


class DeviceRequest(BaseModel):
    device: str  # "cuda", "cpu", or "auto"


class SearchParams(BaseModel):
    q: str
    kind: Optional[str] = "all"
    limit: Optional[int] = 30


@app.get("/api/status")
def get_status():
    db_stats = index_store.get_stats()
    dev_info = embedder.get_device_info()
    return {
        "status": "online",
        "model_name": config.embedding_model,
        "model_loaded": embedder.is_loaded(),
        "embedding_dim": config.embedding_dim,
        "device": dev_info["current_device"],
        "preferred_device": dev_info["preferred_device"],
        "cuda_available": dev_info["cuda_available"],
        "gpu_name": dev_info["gpu_name"],
        "vram_gb": dev_info["vram_gb"],
        "total_files": db_stats["total_files"],
        "total_chunks": db_stats["total_chunks"],
        "db_size_mb": db_stats["db_size_mb"],
        "indexing_running": indexer.is_running(),
    }


@app.get("/api/device")
def get_device():
    return embedder.get_device_info()


@app.post("/api/device")
def set_device(req: DeviceRequest):
    new_device = embedder.switch_device(req.device)
    return {
        "status": "updated",
        "current_device": new_device,
        "info": embedder.get_device_info(),
    }


@app.get("/api/folders")
def get_folders():
    folders_info = []
    with index_store.get_connection() as conn:
        for f in config.chosen_folders:
            p = Path(f)
            exists = p.exists() and p.is_dir()
            prefix = os.path.normpath(f)
            row = conn.execute("SELECT COUNT(*) FROM files WHERE path LIKE ?", (f"{prefix}%",)).fetchone()
            file_count = row[0] if row else 0
            folders_info.append({
                "path": f,
                "name": p.name or f,
                "exists": exists,
                "file_count": file_count,
            })

    return {
        "chosen_folders": folders_info,
        "excluded_patterns": config.excluded_patterns,
    }


@app.post("/api/folders/add")
def add_folder(req: FolderRequest):
    path = os.path.normpath(req.path.strip())
    if not os.path.exists(path) or not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="Directory path does not exist.")

    added = config.add_folder(path)
    if not added:
        return {"status": "already_exists", "path": path}

    # Start background incremental indexing
    if not indexer.is_running():
        indexer.start_indexing(full_reindex=False)

    return {"status": "added", "path": path}


@app.post("/api/folders/remove")
def remove_folder(req: FolderRequest):
    removed = config.remove_folder(req.path)
    if not removed:
        raise HTTPException(status_code=404, detail="Folder was not found in chosen folders.")

    # Remove files under this folder from index
    all_indexed = index_store.get_all_indexed_paths()
    removed_path = os.path.normpath(req.path)
    for p in all_indexed:
        if p.startswith(removed_path):
            index_store.delete_file(p)

    searcher.refresh_vector_cache()
    return {"status": "removed", "path": req.path}


@app.post("/api/folders/browse")
def browse_folder():
    """Opens a native Windows folder selector dialog."""
    selected_folder = ""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        selected_folder = filedialog.askdirectory(title="Choose a Folder to Index")
        root.destroy()
    except Exception as e:
        print(f"[API] Error opening folder dialog: {e}")

    if selected_folder:
        norm = os.path.normpath(selected_folder)
        return {"path": norm, "cancelled": False}
    return {"path": "", "cancelled": True}


@app.post("/api/index/start")
def start_indexing(full_reindex: bool = False):
    if indexer.is_running():
        return {"status": "already_running"}

    started = indexer.start_indexing(full_reindex=full_reindex)
    return {"status": "started" if started else "failed"}


@app.post("/api/index/cancel")
def cancel_indexing():
    indexer.cancel_indexing()
    return {"status": "cancellation_requested"}


@app.get("/api/index/progress")
def get_index_progress():
    return indexer.progress.to_dict()


@app.get("/api/search")
def search(
    q: str = Query(..., min_length=1),
    kind: str = Query("all"),
    limit: int = Query(25, ge=1, le=100),
):
    try:
        results = searcher.search(query=q, kind_filter=kind, limit=limit)
        return {
            "query": q,
            "kind": kind,
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/thumbnail")
def get_thumbnail(path: str = Query(...), size: int = Query(320), timestamp: Optional[float] = Query(None)):
    """Generates and caches an image or video frame thumbnail at specific timestamp, converting to JPEG."""
    file_path = os.path.normpath(path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    ext = Path(file_path).suffix.lower()
    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        mtime = 0

    ts_part = f"_t{int(timestamp)}" if timestamp is not None else ""
    cache_filename = f"{abs(hash(file_path))}{ts_part}_{int(mtime)}_{size}.jpg"
    cache_path = THUMBNAILS_DIR / cache_filename

    if cache_path.exists():
        return FileResponse(cache_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    img = None
    try:
        if ext in IMAGE_EXTS:
            with Image.open(file_path) as im:
                img = im.convert("RGB")
        elif ext in VIDEO_EXTS:
            import av
            with av.open(file_path) as container:
                stream = next((s for s in container.streams if s.type == "video"), None)
                if stream:
                    target = timestamp if timestamp is not None else 0.0
                    for frame in container.decode(stream):
                        pts = float(frame.pts * stream.time_base) if frame.pts is not None else 0.0
                        if pts >= target:
                            img = frame.to_image().convert("RGB")
                            break
                    if img is None and container.streams.video:
                        # Fallback to very first frame
                        container.seek(0)
                        for frame in container.decode(stream):
                            img = frame.to_image().convert("RGB")
                            break
    except Exception as e:
        print(f"[Thumbnail] Error generating thumbnail for {file_path}: {e}")

    if img is None:
        raise HTTPException(status_code=400, detail="Cannot generate thumbnail for this file type")

    try:
        img.thumbnail((size, size), Image.Resampling.LANCZOS)
        img.save(str(cache_path), format="JPEG", quality=85)
        return FileResponse(cache_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save thumbnail: {e}")


@app.get("/api/stream-media")
def stream_media(path: str = Query(...)):
    """Streams media file for in-browser playback."""
    file_path = os.path.normpath(path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    ext = Path(file_path).suffix.lower()
    media_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
    }
    mtype = media_types.get(ext, "application/octet-stream")
    return FileResponse(file_path, media_type=mtype)


@app.post("/api/search-media")
async def search_media(
    file: UploadFile = File(...),
    neg_file: Optional[UploadFile] = File(None),
    neg_query: Optional[str] = Form(None),
    exclude_exts: Optional[str] = Form(None),
    kind: str = Query("all"),
    limit: int = Query(30, ge=1, le=100),
):
    """Searches across indexed files using an uploaded media query, with support for negative/inverse media or text concepts."""
    ext = Path(file.filename or "").suffix.lower()
    temp_dir = DATA_DIR / "temp_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"query_{os.getpid()}_{file.filename}"
    neg_temp_file = None

    try:
        with open(temp_file, "wb") as f:
            shutil.copyfileobj(file.file, f)

        media_type = "unknown"
        if ext in IMAGE_EXTS:
            media_type = "image"
            query_vector = embedder.embed_image(temp_file)
        elif ext in AUDIO_EXTS:
            media_type = "audio"
            query_vector = embedder.embed_audio(temp_file)
        elif ext in VIDEO_EXTS:
            media_type = "video"
            query_vector = embedder.embed_video(temp_file)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported media query extension: {ext}. Allowed: Images, Audio, Video"
            )

        # Handle negative / inverse media or text
        neg_vector = None
        if neg_file and neg_file.filename:
            neg_ext = Path(neg_file.filename).suffix.lower()
            neg_temp_file = temp_dir / f"neg_{os.getpid()}_{neg_file.filename}"
            with open(neg_temp_file, "wb") as f:
                shutil.copyfileobj(neg_file.file, f)

            if neg_ext in IMAGE_EXTS:
                neg_vector = embedder.embed_image(neg_temp_file)
            elif neg_ext in AUDIO_EXTS:
                neg_vector = embedder.embed_audio(neg_temp_file)
            elif neg_ext in VIDEO_EXTS:
                neg_vector = embedder.embed_video(neg_temp_file)
        elif neg_query and neg_query.strip():
            neg_vector = embedder.embed_query(neg_query.strip(), is_code=False)

        # Excluded extensions
        excl_set = set()
        if exclude_exts:
            for item in re.split(r"[,\s]+", exclude_exts.strip()):
                clean_item = item.lstrip("!-").strip().lower()
                if clean_item:
                    excl_set.add(f".{clean_item}" if not clean_item.startswith(".") else clean_item)

        results = searcher.search_by_vector(
            query_vector=query_vector,
            negative_vector=neg_vector,
            excluded_extensions=excl_set,
            kind_filter=kind,
            limit=limit,
        )
        return {
            "query_type": "media",
            "media_type": media_type,
            "filename": file.filename,
            "has_inverse": neg_vector is not None,
            "kind": kind,
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }
    except Exception as e:
        print(f"[API] Search media error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for p in (temp_file, neg_temp_file):
            if p and p.exists():
                try:
                    os.remove(p)
                except OSError:
                    pass


@app.post("/api/search-media-path")
def search_media_path(req: FolderRequest, kind: str = Query("all"), limit: int = Query(30)):
    """Searches using an existing local media file path."""
    file_path = os.path.normpath(req.path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Media file not found")

    ext = Path(file_path).suffix.lower()
    if ext in IMAGE_EXTS:
        media_type = "image"
        query_vector = embedder.embed_image(file_path)
    elif ext in AUDIO_EXTS:
        media_type = "audio"
        query_vector = embedder.embed_audio(file_path)
    elif ext in VIDEO_EXTS:
        media_type = "video"
        query_vector = embedder.embed_video(file_path)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported media format: {ext}")

    results = searcher.search_by_vector(query_vector, kind_filter=kind, limit=limit)
    return {
        "query_type": "media",
        "media_type": media_type,
        "filename": Path(file_path).name,
        "kind": kind,
        "count": len(results),
        "results": [r.to_dict() for r in results],
    }


@app.post("/api/open-file")
def open_file(req: FolderRequest):
    """Opens file in default Windows application."""
    path = os.path.normpath(req.path)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        os.startfile(path)
        return {"status": "opened", "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open file: {e}")


@app.post("/api/open-folder")
def open_folder(req: FolderRequest):
    """Reveals file in Windows File Explorer without triggering Documents fallback."""
    path = os.path.normpath(req.path)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found.")

    try:
        if os.path.isfile(path):
            # Pass formatted string to CreateProcess directly without Python list2cmdline quote mangling
            subprocess.Popen(f'explorer.exe /select,"{path}"')
        else:
            subprocess.Popen(f'explorer.exe "{path}"')
        return {"status": "revealed", "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open explorer: {e}")


@app.get("/api/preview")
def get_preview(file_id: int, chunk_id: Optional[int] = None):
    """Returns preview text and context for a result."""
    with index_store.get_connection() as conn:
        f = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not f:
            raise HTTPException(status_code=404, detail="File not found")

        chunk = None
        if chunk_id:
            chunk_row = conn.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,)).fetchone()
            if chunk_row:
                chunk = dict(chunk_row)

        return {
            "file": dict(f),
            "chunk": chunk,
        }


# Mount static frontend
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
