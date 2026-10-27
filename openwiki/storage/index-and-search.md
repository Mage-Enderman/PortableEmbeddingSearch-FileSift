---
type: concept
title: Index Storage and Hybrid Search Engine
description: Architecture of the SQLite WAL storage layer, FTS5 BM25 text synchronization triggers, in-memory dense vector cosine scoring, query modifier parsing, and Reciprocal Rank Fusion (RRF).
tags: [sqlite, fts5, bm25, rrf, reciprocal-rank-fusion, vector-store, searcher]
verified:
  - by: openwiki/0.7.2
    at: 2026-10-27T03:41:19.738Z
sources:
  - id: openwiki-source-f286f4e8f719791fa3518b28
    resource: repo://core/index_store.py
  - id: openwiki-source-541e953cbcfc4178fd1675a2
    resource: repo://core/searcher.py
generated: { by: "antigravity", at: "2026-10-27T03:41:19.738Z" }
---

# Index Storage and Hybrid Search Engine

FileSift provides a hybrid search architecture pairing embedded SQLite storage with an in-memory vector cache and lexical search engine. Dense semantic understanding and exact keyword precision are merged via Reciprocal Rank Fusion (RRF).

```
                      Raw User Query / Media Input
                                   |
                                   v
+-----------------------------------------------------------------------------------+
| Query Parser (parse_query_modifiers)                                              |
|  - Negative concept detection ("not:snow", "!crowds")                             |
|  - Extension exclusions ("!json", "-pdf")                                         |
|  - Code intent detection ("code:", "def ", "class ", "import ")                   |
+-----------------------------------------------------------------------------------+
             |                                              |
             v                                              v
+---------------------------------------+      +------------------------------------+
| Dense Vector Branch                   |      | Lexical FTS5 BM25 Branch           |
|  - EmbeddingGemma 2 512d inference    |      |  - Sanitized terms OR-joined       |
|  - Negative vector steering (pos - α·neg) |   |  - Porter stemmer + unicode61     |
|  - Dot product against RAM matrix     |      |  - SQLite bm25() score             |
+---------------------------------------+      +------------------------------------+
             \                                              /
              \                                            /
               v                                          v
+-----------------------------------------------------------------------------------+
| Reciprocal Rank Fusion (RRF) Merger                                               |
|  - RRF(d) = 0.65 / (60 + rank_sem) + 0.35 / (60 + rank_bm25)                      |
|  - Normalization by max score, extension pruning, snippet generation with <mark>  |
+-----------------------------------------------------------------------------------+
```

---

## 1. SQLite Storage Architecture

All database tables, vector BLOBs, and full-text indexes reside in a single portable file (`data/index.sqlite`), managed by `core/index_store.py:IndexStore`:

### Concurrency and Journaling
- **WAL Journaling**: Database connections enable Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) and relaxed synchronous writes (`PRAGMA synchronous = NORMAL;`).
- **Foreign Key Integrity**: `PRAGMA foreign_keys = ON;` guarantees that deleting a file from the `files` table automatically cascades and purges corresponding chunk rows.

### Table Schema
1. `meta`: Key-value storage for schema and index metadata.
2. `files`: File-level inventory storing `id`, `path` (UNIQUE), `filename`, `extension`, `size`, `mtime`, `status`, `chunk_count`, and `indexed_at`.
3. `chunks`: Individual content segments storing `file_id` (foreign key), `chunk_index`, `text`, `title`, `loc_start`, `loc_end`, `label`, and `vector` (BLOB).
4. `fts_chunks`: SQLite FTS5 external content virtual table indexing `text`, `title`, and `filename` using `tokenize='porter unicode61 remove_diacritics 2'`.

### Automated FTS Synchronization Triggers
Rather than managing duplicate insert/update/delete logic in application code, SQLite triggers keep the FTS index in lockstep:
- `chunks_ai`: Copies newly inserted chunk text, title, and filename into `fts_chunks`.
- `chunks_ad`: Issues `'delete'` entries to `fts_chunks` when chunks are removed.
- `chunks_au`: Updates `fts_chunks` on chunk modification.

---

## 2. In-Memory Vector Operations & BLOB Serialization

- **BLOB Serialization (`vector_to_blob` / `blob_to_vector`)**: 512-dimensional float32 numpy arrays are serialized as continuous binary bytes (`np.ascontiguousarray(vec, dtype=np.float32).tobytes()`), yielding exactly 2,048 bytes per vector blob.
- **In-Memory Cache (`load_all_vectors` & `refresh_vector_cache`)**: To eliminate disk I/O during real-time typing, all chunk vectors are stacked into an $N \times 512$ NumPy float32 matrix (`_cached_matrix`) alongside parallel chunk IDs (`_cached_chunk_ids`).
- **Cosine Dot Product**: Because all embeddings are unit-normalized ($L_2 = 1.0$), cosine similarity simplifies to a matrix-vector dot product:
  $$\text{sims} = \mathbf{M} \cdot \mathbf{v}_q$$
  yielding instant similarity scoring across thousands of files.

---

## 3. Query Parsing & Vector Steering

Search input is parsed in `core/searcher.py:parse_query_modifiers`:

### Negative Concept Steering
When a user provides negative constraints (e.g. `sunset on beach not:people` or `not:crowd`), the engine embeds the negative concept into $\mathbf{v}_{\text{neg}}$ and steers the query vector away:
$$\mathbf{v}_{\text{steered}} = \mathbf{v}_{\text{query}} - 0.65 \cdot \mathbf{v}_{\text{neg}}$$
The resulting vector is re-normalized to unit length prior to the cosine dot product.

### Filetype Exclusions
Negative filetype markers such as `!json`, `-pdf`, or `!tests` are extracted into `excluded_extensions` and stripped from the semantic prompt so they do not distort the embedding. Candidates matching excluded extensions are filtered out during candidate evaluation.

---

## 4. Hybrid Search via Reciprocal Rank Fusion (RRF)

Natural language search often struggles with precise keywords, serial numbers, or function names. FileSift fuses semantic and lexical matches using Reciprocal Rank Fusion:

1. **Semantic Ranking**: Vector similarity scores are computed for all chunks in RAM, and candidates are sorted in descending order of similarity.
2. **Lexical BM25 Ranking**: Cleaned query terms are combined into an OR query over `fts_chunks`. SQLite's `bm25()` function scores matching chunks.
3. **Fusion Formulation**:
   $$RRF(d) = w_{\text{vec}} \cdot \frac{1}{k + \text{rank}_{\text{sem}}(d) + 1} + w_{\text{kw}} \cdot \frac{1}{k + \text{rank}_{\text{bm25}}(d) + 1}$$
   where default smoothing constant $k = 60.0$, vector weight $w_{\text{vec}} = 0.65$, and keyword weight $w_{\text{kw}} = 0.35$.
4. **Snippets and Highlighting**: `create_highlighted_snippet()` locates query terms in chunk text and wraps matched boundaries with `<mark>` tags for rendering in the UI.
