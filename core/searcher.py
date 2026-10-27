import re
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from core.index_store import IndexStore
from core.embedder import EmbeddingGemmaEngine
from core.config import config


class SearchResult:
    def __init__(
        self,
        chunk_id: int,
        file_id: int,
        path: str,
        filename: str,
        extension: str,
        loc_label: str,
        loc_start: int,
        loc_end: int,
        snippet: str,
        full_text: str,
        score: float,
        semantic_score: float,
        bm25_score: float,
        kind: str,
    ):
        self.chunk_id = chunk_id
        self.file_id = file_id
        self.path = path
        self.filename = filename
        self.extension = extension
        self.loc_label = loc_label
        self.loc_start = loc_start
        self.loc_end = loc_end
        self.snippet = snippet
        self.full_text = full_text
        self.score = score
        self.semantic_score = semantic_score
        self.bm25_score = bm25_score
        self.kind = kind

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "file_id": self.file_id,
            "path": self.path,
            "filename": self.filename,
            "extension": self.extension,
            "loc_label": self.loc_label,
            "loc_start": self.loc_start,
            "loc_end": self.loc_end,
            "snippet": self.snippet,
            "full_text": self.full_text,
            "score": round(self.score, 3),
            "score_pct": min(100, max(0, int(self.score * 100))),
            "semantic_score": round(self.semantic_score, 3),
            "bm25_score": round(self.bm25_score, 3),
            "kind": self.kind,
        }


class ParsedQuery:
    def __init__(
        self,
        clean_text: str,
        is_code: bool = False,
        excluded_extensions: Optional[Set[str]] = None,
        negative_concept: Optional[str] = None,
    ):
        self.clean_text = clean_text
        self.is_code = is_code
        self.excluded_extensions = excluded_extensions or set()
        self.negative_concept = negative_concept


def parse_query_modifiers(raw_query: str) -> ParsedQuery:
    """
    Parses search arguments, negative concepts, and filetype exclusion flags:
    - !json or -json or !.json or -.pdf -> excluded_extensions
    - not:snow or !crowds or -glasses -> negative_concept
    - Strips operators from clean_text to prevent polluting semantic prompt.
    """
    tokens = raw_query.strip().split()
    clean_tokens = []
    excluded_extensions = set()
    negative_concepts = []

    for t in tokens:
        lower = t.lower()
        if lower.startswith("not:") and len(lower) > 4:
            negative_concepts.append(lower[4:])
        elif (lower.startswith("!") or lower.startswith("-")) and len(lower) > 1:
            val = lower[1:].lstrip(".")
            # Common extensions or known allowed extensions
            if f".{val}" in config.allowed_extensions or (len(val) <= 5 and val.isalnum()):
                excluded_extensions.add(f".{val}")
            else:
                negative_concepts.append(val)
        else:
            clean_tokens.append(t)

    clean_text = " ".join(clean_tokens).strip()
    is_code = clean_text.startswith("code:") or any(kw in clean_text for kw in ("func ", "def ", "class ", "import "))
    if clean_text.startswith("code:"):
        clean_text = clean_text[5:].strip()

    neg_concept = " ".join(negative_concepts).strip() if negative_concepts else None
    return ParsedQuery(
        clean_text=clean_text,
        is_code=is_code,
        excluded_extensions=excluded_extensions,
        negative_concept=neg_concept,
    )


class HybridSearcher:
    def __init__(self, index_store: Optional[IndexStore] = None, embedder: Optional[EmbeddingGemmaEngine] = None):
        self.store = index_store or IndexStore()
        self.embedder = embedder or EmbeddingGemmaEngine.get_instance()
        self._cached_matrix: Optional[np.ndarray] = None
        self._cached_chunk_ids: Optional[List[int]] = None

    def refresh_vector_cache(self) -> None:
        """Reloads vector matrix into RAM for instant similarity matching."""
        matrix, chunk_ids = self.store.load_all_vectors()
        self._cached_matrix = matrix
        self._cached_chunk_ids = chunk_ids

    @staticmethod
    def classify_extension(ext: str) -> str:
        ext = ext.lower()
        if ext in [".pdf", ".docx", ".odt", ".rtf", ".txt", ".md", ".markdown", ".rst", ".org", ".typ", ".html", ".htm", ".doc"]:
            return "docs"
        elif ext in [".xlsx", ".ods", ".pptx", ".odp", ".csv", ".tsv"]:
            return "sheets"
        elif ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".scss", ".json", ".yaml", ".yml", ".toml", ".xml", ".sql", ".rs", ".go", ".c", ".cpp", ".h", ".hpp", ".cs", ".java", ".kt", ".swift", ".sh", ".bash", ".ps1", ".bat", ".cmd"]:
            return "code"
        elif ext in [".png", ".jpg", ".jpeg", ".webp", ".avif", ".jxl", ".heic", ".heif", ".bmp", ".gif", ".tiff", ".tif"]:
            return "images"
        elif ext in [".mp4", ".mkv", ".avi", ".mov", ".webm"]:
            return "videos"
        elif ext in [".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac"]:
            return "audio"
        return "docs"

    @staticmethod
    def create_highlighted_snippet(text: str, query: str, max_chars: int = 240) -> str:
        """Extracts most relevant excerpt and marks query matches with <mark> tags."""
        words = [w for w in re.split(r"\W+", query.lower()) if len(w) > 2]
        if not words:
            snippet = text[:max_chars].strip()
            return snippet + "..." if len(text) > max_chars else snippet

        # Find first matching word
        lower_text = text.lower()
        best_pos = -1
        for w in words:
            pos = lower_text.find(w)
            if pos != -1 and (best_pos == -1 or pos < best_pos):
                best_pos = pos

        if best_pos == -1:
            snippet = text[:max_chars].strip()
            if len(text) > max_chars:
                snippet += "..."
        else:
            start = max(0, best_pos - 60)
            end = min(len(text), start + max_chars)
            snippet = text[start:end].strip()
            if start > 0:
                snippet = "..." + snippet
            if end < len(text):
                snippet = snippet + "..."

        # Highlight words
        pattern = re.compile(rf"\b({'|'.join(re.escape(w) for w in words)})\b", re.IGNORECASE)
        highlighted = pattern.sub(r"<mark>\1</mark>", snippet)
        return highlighted

    def search(
        self,
        query: str,
        kind_filter: Optional[str] = None,
        limit: int = 25,
        vector_weight: float = 0.65,
        keyword_weight: float = 0.35,
    ) -> List[SearchResult]:
        query = query.strip()
        if not query:
            return []

        # Parse modifiers (!json, -pdf, not:snow)
        parsed = parse_query_modifiers(query)
        clean_query = parsed.clean_text or query

        # Ensure vector matrix is loaded
        if self._cached_matrix is None or self._cached_chunk_ids is None:
            self.refresh_vector_cache()

        total_chunks = len(self._cached_chunk_ids)
        if total_chunks == 0:
            return []

        # 1. Semantic Vector Search with optional Inverse Concept Steering
        semantic_scores: Dict[int, float] = {}
        if self.embedder.is_loaded() or self._cached_matrix.shape[0] > 0:
            try:
                pos_vec = self.embedder.embed_query(clean_query, is_code=parsed.is_code)
                if parsed.negative_concept:
                    # Inverse concept subtraction
                    neg_vec = self.embedder.embed_query(parsed.negative_concept, is_code=False)
                    steered = pos_vec - 0.65 * neg_vec
                    norm = np.linalg.norm(steered)
                    final_query_vec = (steered / norm).astype(np.float32) if norm > 0 else pos_vec
                else:
                    final_query_vec = pos_vec

                # Cosine similarity is dot product of normalized vectors
                sims = np.dot(self._cached_matrix, final_query_vec)
                for cid, sim in zip(self._cached_chunk_ids, sims):
                    semantic_scores[cid] = float(sim)
            except Exception as e:
                print(f"[HybridSearcher] Semantic search error: {e}")

        # 2. BM25 Keyword Search
        bm25_matches = self.store.bm25_search(clean_query, limit=100)
        bm25_scores: Dict[int, float] = dict(bm25_matches)

        # 3. Reciprocal Rank Fusion (RRF)
        sorted_semantic = sorted(semantic_scores.items(), key=lambda x: x[1], reverse=True)
        sorted_bm25 = sorted(bm25_scores.items(), key=lambda x: x[1], reverse=True)

        rrf_scores: Dict[int, float] = {}
        k = 60.0

        for rank, (cid, score) in enumerate(sorted_semantic[:100]):
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + vector_weight * (1.0 / (k + rank + 1))

        for rank, (cid, score) in enumerate(sorted_bm25[:100]):
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + keyword_weight * (1.0 / (k + rank + 1))

        if not rrf_scores:
            return []

        top_candidates = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:500]
        candidate_ids = [cid for cid, _ in top_candidates]
        details = self.store.get_chunk_details(candidate_ids)

        max_rrf = top_candidates[0][1] if top_candidates else 1.0

        results: List[SearchResult] = []
        for cid, rrf_val in top_candidates:
            if cid not in details:
                continue

            info = details[cid]
            ext = info["extension"].lower()

            # Apply hard extension exclusions (!json, -pdf, etc.)
            if ext in parsed.excluded_extensions:
                continue

            kind = self.classify_extension(ext)
            if kind_filter and kind_filter != "all" and kind != kind_filter:
                continue

            sem_score = semantic_scores.get(cid, 0.0)
            bm25_sc = bm25_scores.get(cid, 0.0)
            normalized_score = rrf_val / max_rrf if max_rrf > 0 else 0.0

            snippet = self.create_highlighted_snippet(info["text"], clean_query)

            res = SearchResult(
                chunk_id=cid,
                file_id=info["file_id"],
                path=info["path"],
                filename=info["filename"],
                extension=info["extension"],
                loc_label=info["label"],
                loc_start=info["loc_start"],
                loc_end=info["loc_end"],
                snippet=snippet,
                full_text=info["text"],
                score=normalized_score,
                semantic_score=sem_score,
                bm25_score=bm25_sc,
                kind=kind,
            )
            results.append(res)
            if len(results) >= limit:
                break

        return results

    def search_by_vector(
        self,
        query_vector: np.ndarray,
        negative_vector: Optional[np.ndarray] = None,
        excluded_extensions: Optional[Set[str]] = None,
        kind_filter: Optional[str] = None,
        limit: int = 30,
    ) -> List[SearchResult]:
        """
        Performs vector similarity search with support for:
        - Inverse/Negative search: Steers away from negative_vector
        - Filetype exclusions: Skips excluded_extensions
        """
        if self._cached_matrix is None or self._cached_chunk_ids is None:
            self.refresh_vector_cache()

        if self._cached_matrix.shape[0] == 0:
            return []

        # Vector steering if negative vector is provided
        if negative_vector is not None:
            steered = query_vector - 0.65 * negative_vector
            norm = np.linalg.norm(steered)
            search_vector = (steered / norm).astype(np.float32) if norm > 0 else query_vector
        else:
            search_vector = query_vector

        # Cosine similarity against all cached chunk vectors
        sims = np.dot(self._cached_matrix, search_vector)
        sorted_indices = np.argsort(sims)[::-1][:min(500, len(sims))]

        candidate_ids = [self._cached_chunk_ids[idx] for idx in sorted_indices]
        candidate_scores = {self._cached_chunk_ids[idx]: float(sims[idx]) for idx in sorted_indices}
        details = self.store.get_chunk_details(candidate_ids)

        excl = excluded_extensions or set()
        results: List[SearchResult] = []
        for cid in candidate_ids:
            if cid not in details:
                continue

            info = details[cid]
            ext = info["extension"].lower()

            if ext in excl:
                continue

            kind = self.classify_extension(ext)
            if kind_filter and kind_filter != "all" and kind != kind_filter:
                continue

            sim_score = candidate_scores.get(cid, 0.0)
            norm_score = max(0.0, min(1.0, (sim_score + 1.0) / 2.0))

            res = SearchResult(
                chunk_id=cid,
                file_id=info["file_id"],
                path=info["path"],
                filename=info["filename"],
                extension=info["extension"],
                loc_label=info["label"],
                loc_start=info["loc_start"],
                loc_end=info["loc_end"],
                snippet=info["text"][:240],
                full_text=info["text"],
                score=norm_score,
                semantic_score=sim_score,
                bm25_score=0.0,
                kind=kind,
            )
            results.append(res)
            if len(results) >= limit:
                break

        return results
