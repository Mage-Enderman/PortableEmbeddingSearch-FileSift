from typing import List, Dict, Any
from pathlib import Path
from core.extractors import ExtractedSegment, is_mostly_numbers


class Chunk:
    def __init__(
        self,
        chunk_index: int,
        text: str,
        title: str,
        loc_start: int,
        loc_end: int,
        label: str,
        doc_prompt: str,
        is_numeric_export: bool = False,
    ):
        self.chunk_index = chunk_index
        self.text = text
        self.title = title
        self.loc_start = loc_start
        self.loc_end = loc_end
        self.label = label
        # Official EmbeddingGemma 2 document task prompt format:
        # title: {title} | text: {content}
        self.doc_prompt = doc_prompt
        self.is_numeric_export = is_numeric_export

    def __repr__(self):
        return f"<Chunk idx={self.chunk_index} loc={self.loc_start}-{self.loc_end} chars={len(self.text)} num={self.is_numeric_export}>"


def chunk_file_segments(
    file_path: str,
    segments: List[ExtractedSegment],
    max_chunk_chars: int = 1500,
    overlap_chars: int = 200,
) -> List[Chunk]:
    """Splits extracted segments into semantic chunks suitable for embedding."""
    chunks = []
    filename = Path(file_path).name
    chunk_index = 0

    for seg in segments:
        text = seg.text
        seg_numeric = seg.is_numeric_export or is_mostly_numbers(text)

        if len(text) <= max_chunk_chars:
            if text.strip():
                doc_prompt = f"title: {filename} | text: {text.strip()}"
                chunks.append(
                    Chunk(
                        chunk_index=chunk_index,
                        text=text.strip(),
                        title=filename,
                        loc_start=seg.loc_start,
                        loc_end=seg.loc_end,
                        label=seg.label or f"Lines {seg.loc_start}-{seg.loc_end}",
                        doc_prompt=doc_prompt,
                        is_numeric_export=seg_numeric,
                    )
                )
                chunk_index += 1
            continue

        # If segment is larger, split by lines/paragraphs
        lines = text.splitlines(keepends=True)
        current_lines = []
        current_len = 0
        seg_start_line = seg.loc_start
        line_offset = 0

        for idx, line in enumerate(lines):
            current_lines.append(line)
            current_len += len(line)

            if current_len >= max_chunk_chars:
                chunk_text = "".join(current_lines).strip()
                if chunk_text:
                    loc_start = seg_start_line + line_offset
                    loc_end = loc_start + len(current_lines) - 1
                    label = f"Lines {loc_start}-{loc_end}"
                    doc_prompt = f"title: {filename} | text: {chunk_text}"
                    chunk_numeric = seg_numeric or is_mostly_numbers(chunk_text)

                    chunks.append(
                        Chunk(
                            chunk_index=chunk_index,
                            text=chunk_text,
                            title=filename,
                            loc_start=loc_start,
                            loc_end=loc_end,
                            label=label,
                            doc_prompt=doc_prompt,
                            is_numeric_export=chunk_numeric,
                        )
                    )
                    chunk_index += 1

                # Calculate overlap
                overlap_len = 0
                overlap_lines = []
                for ol in reversed(current_lines):
                    if overlap_len + len(ol) > overlap_chars:
                        break
                    overlap_lines.insert(0, ol)
                    overlap_len += len(ol)

                line_offset += len(current_lines) - len(overlap_lines)
                current_lines = list(overlap_lines)
                current_len = overlap_len

        # Flush remainder
        if current_lines:
            chunk_text = "".join(current_lines).strip()
            if chunk_text:
                loc_start = seg_start_line + line_offset
                loc_end = loc_start + len(current_lines) - 1
                label = f"Lines {loc_start}-{loc_end}"
                doc_prompt = f"title: {filename} | text: {chunk_text}"
                chunk_numeric = seg_numeric or is_mostly_numbers(chunk_text)

                chunks.append(
                    Chunk(
                        chunk_index=chunk_index,
                        text=chunk_text,
                        title=filename,
                        loc_start=loc_start,
                        loc_end=loc_end,
                        label=label,
                        doc_prompt=doc_prompt,
                        is_numeric_export=chunk_numeric,
                    )
                )
                chunk_index += 1

    return chunks
