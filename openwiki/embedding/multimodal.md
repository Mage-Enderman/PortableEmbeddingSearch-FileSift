---
type: concept
title: EmbeddingGemma 2 Multimodal Inference Engine
description: Architecture of the on-device multimodal embedding engine utilizing EmbeddingGemma 2, Matryoshka dimension truncation, PyAV temporal audio/video sampling, and task-specific prompt prefixes.
tags: [embedding, embeddinggemma-2, multimodal, matryoshka, pytorch, sentence-transformers, pyav]
verified:
  - by: openwiki/0.7.2
    at: 2026-10-27T03:41:19.738Z
sources:
  - id: openwiki-source-fa5486f74b509a8f838a2dde
    resource: repo://core/embedder.py
  - id: openwiki-source-0df87428a8e51c52d17e1ca8
    resource: repo://core/indexer.py
generated: { by: "antigravity", at: "2026-10-27T03:41:19.738Z" }
---

# EmbeddingGemma 2 Multimodal Inference Engine

FileSift uses Google DeepMind's `google/embeddinggemma-2` as a unified on-device multimodal embedding backbone. The engine maps natural language search queries, code snippets, document chunks, raster images, audio recordings, and video frames into a shared 512-dimensional vector space.

```
                    Unified 512d Matryoshka Vector Space
                                      ▲
     +-----------------+--------------+---------------+------------------+
     |                 |                              |                  |
+---------+   +-------------------+          +------------------+  +-----------+
| Queries |   | Text Documents    |          | Audio Windows    |  | Video     |
| & Code  |   | & Numeric Filters |          | (30s @ 16kHz)    |  | Frames    |
+---------+   +-------------------+          +------------------+  +-----------+
     ▲                 ▲                              ▲                  ▲
 task prompt      title: ... | text: ...          PyAV mono 16k     PyAV interval
```

---

## 1. Engine Architecture and Lifecycle

The embedding subsystem is implemented in `core/embedder.py:EmbeddingGemmaEngine` as a singleton (`get_instance()`):

### Device Management and Precision
- **Device Resolution (`resolve_device`)**: Inspects runtime configuration (`auto`, `cuda`, `cpu`). If set to `auto` or `cuda`, it queries `torch.cuda.is_available()`.
- **Numerical Precision**: EmbeddingGemma 2 is susceptible to overflow in standard FP16. The engine explicitly chooses `torch.bfloat16` when CUDA supports bfloat16 (`torch.cuda.is_bf16_supported()`), falling back to `torch.float32` otherwise.
- **Dynamic Device Switching (`switch_device`)**: Allows changing the inference device at runtime between CPU and GPU without restarting the application, transferring the active model weights via `model.to(new_device)`.
- **Portable Weight Storage**: Cache directories (`HF_HOME` and `TORCH_HOME`) are pinned to `./data/models/` in `core/config.py` so model weights remain strictly inside the local portable app directory.

---

## 2. Task Prompting & Matryoshka Representation Learning

EmbeddingGemma 2 relies on explicit task instructions and Matryoshka Representation Learning (MRL):

### Asymmetric Query Prefixes
Queries must include task-specific instructions during encoding to align with document embeddings:
- **General Search**: `task: search result | query: {query}`
- **Code Retrieval**: `task: code retrieval | query: {query}`

The search parser (`core/searcher.py:parse_query_modifiers`) automatically detects code indicators or explicit query terms to toggle `is_code=True`.

### Document Prompt Format
Text documents and code chunks are formatted according to the official convention:
```
title: {filename} | text: {chunk_text}
```

### Matryoshka Dimension Truncation
EmbeddingGemma 2 produces 768-dimensional base embeddings. FileSift truncates the representations to 512 dimensions (`truncate_dim=512`) followed by L2 normalization (`normalize_embeddings=True`). This produces high-density representations that preserve similarity ranking quality while reducing memory footprint and accelerating dot-product calculations.

---

## 3. Multimodal Ingestion Pipeline

### Image Embedding (`embed_image`)
Accepts file paths, PIL Image objects, or raw byte buffers. Images are converted to RGB mode and encoded directly through the model's visual projection layer into the unified 512d space. This supports finding visual matches from text queries or reverse-searching images using image input.

### Temporal Audio Sampling (`extract_audio_windows` & `embed_audio`)
Audio files (`.wav`, `.mp3`, `.m4a`, `.ogg`, `.flac`, `.aac`) are processed via PyAV:
1. Decoded and resampled to 16,000 Hz 16-bit mono PCM.
2. Segmented into overlapping 30-second windows with a 15-second hop stride.
3. Windows are encoded into the 512d space with start/end second markers (`loc_start`, `loc_end`), producing indexed entries that point users directly to exact timestamps (e.g. `▶ 01:45`).

### Video Keyframe & Audio Extraction (`extract_video_frames` & `embed_video`)
Video files (`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`) undergo dual-track decomposition:
1. **Visual Keyframes**: Video streams are decoded frame-by-frame via PyAV at 3-second intervals up to 60 frames. Each sampled frame is embedded as an image chunk tagged with `🎬 {timestamp}`.
2. **Soundtrack Processing**: The video's audio stream is concurrently extracted and sliced into 30-second audio windows tagged with `🎵 {timestamp}`.
3. **Whole-Video Aggregate Embedding**: For whole-video similarity, `embed_video` samples representative frames, encodes each frame, computes the mean vector, and L2-normalizes it.
