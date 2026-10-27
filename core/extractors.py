import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional

# Register modern image plugins for Pillow (AVIF, JXL, HEIF/HEIC)
try:
    import pillow_avif
except ImportError:
    pass

try:
    import pillow_jxl
except ImportError:
    pass

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass


def format_timestamp(seconds: float) -> str:
    """Formats seconds into MM:SS or HH:MM:SS format."""
    total_sec = max(0, int(seconds))
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def is_mostly_numbers(text: str) -> bool:
    """
    Checks if a text block is mostly numeric data (like a data export or numbers table).
    Such text is matched by exact text (BM25 FTS5) only to avoid vector space pollution.
    """
    alnum = [c for c in text if c.isalnum()]
    if not alnum or len(alnum) < 10:
        return False
    digits = sum(c.isdigit() for c in alnum)
    return (digits / len(alnum)) >= 0.35


class ExtractedSegment:
    def __init__(
        self,
        text: str,
        loc_start: int = 1,
        loc_end: int = 1,
        label: str = "",
        is_numeric_export: bool = False,
    ):
        self.text = text.strip()
        self.loc_start = loc_start
        self.loc_end = loc_end
        self.label = label
        self.is_numeric_export = is_numeric_export

    def __repr__(self):
        return f"<Segment loc={self.loc_start}-{self.loc_end} label={self.label!r} chars={len(self.text)} num={self.is_numeric_export}>"


def extract_text_file(path: str) -> List[ExtractedSegment]:
    """Reads a text, code, typst, or markdown file and returns line-numbered segments."""
    encodings = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]
    content = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                content = f.read()
            break
        except (UnicodeDecodeError, OSError):
            continue

    if content is None:
        return []

    lines = content.splitlines()
    if not lines:
        return []

    return [
        ExtractedSegment(
            text=content,
            loc_start=1,
            loc_end=len(lines),
            label="text",
            is_numeric_export=is_mostly_numbers(content),
        )
    ]


def extract_rtf_file(path: str) -> List[ExtractedSegment]:
    """Extracts clean text from an RTF document."""
    try:
        from striprtf.striprtf import rtf_to_text
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        clean = rtf_to_text(raw).strip()
        if clean:
            lines = clean.splitlines()
            return [
                ExtractedSegment(
                    text=clean,
                    loc_start=1,
                    loc_end=len(lines),
                    label="RTF Document",
                    is_numeric_export=is_mostly_numbers(clean),
                )
            ]
    except Exception as e:
        print(f"[Extractors] Error reading RTF {path}: {e}")
    return []


def extract_odt_file(path: str) -> List[ExtractedSegment]:
    """Extracts text from an OpenDocument Text (.odt) file."""
    try:
        with zipfile.ZipFile(path, "r") as z:
            with z.open("content.xml") as f:
                tree = ET.parse(f)
        root = tree.getroot()
        paragraphs = []
        for elem in root.iter():
            if elem.tag.endswith("}p") or elem.tag.endswith("}h"):
                txt = "".join(elem.itertext()).strip()
                if txt:
                    paragraphs.append(txt)
        if paragraphs:
            full_text = "\n\n".join(paragraphs)
            return [
                ExtractedSegment(
                    text=full_text,
                    loc_start=1,
                    loc_end=len(paragraphs),
                    label="ODT Document",
                    is_numeric_export=is_mostly_numbers(full_text),
                )
            ]
    except Exception as e:
        print(f"[Extractors] Error reading ODT {path}: {e}")
    return []


def extract_html_file(path: str) -> List[ExtractedSegment]:
    """Extracts visible text from an HTML document."""
    try:
        from html.parser import HTMLParser

        class HTMLTextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text_parts = []
                self.ignore = False

            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "noscript"):
                    self.ignore = True

            def handle_endtag(self, tag):
                if tag in ("script", "style", "noscript"):
                    self.ignore = False

            def handle_data(self, data):
                if not self.ignore:
                    val = data.strip()
                    if val:
                        self.text_parts.append(val)

        parser = HTMLTextExtractor()
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            parser.feed(f.read())
        clean_text = "\n".join(parser.text_parts)
        if clean_text.strip():
            lines = clean_text.splitlines()
            return [
                ExtractedSegment(
                    text=clean_text.strip(),
                    loc_start=1,
                    loc_end=len(lines),
                    label="HTML Document",
                    is_numeric_export=is_mostly_numbers(clean_text),
                )
            ]
    except Exception as e:
        print(f"[Extractors] Error reading HTML {path}: {e}")
    return []


def extract_docx_file(path: str) -> List[ExtractedSegment]:
    """Extracts text from a DOCX file using python-docx."""
    segments = []
    try:
        import docx
        doc = docx.Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        if paragraphs:
            full_text = "\n\n".join(paragraphs)
            segments.append(
                ExtractedSegment(
                    text=full_text,
                    loc_start=1,
                    loc_end=len(paragraphs),
                    label="Document",
                    is_numeric_export=is_mostly_numbers(full_text),
                )
            )
    except Exception as e:
        print(f"[Extractors] Error reading DOCX {path}: {e}")
    return segments


def extract_pdf_file(path: str, max_pages: int = 5000) -> List[ExtractedSegment]:
    """
    Extracts text page-by-page from a PDF file using pypdf (up to 5,000 pages).
    Scanned pages with images are tagged for indexing and visual match.
    """
    segments = []
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        total_pages = min(len(reader.pages), max_pages)

        for page_idx in range(total_pages):
            page = reader.pages[page_idx]
            text = (page.extract_text() or "").strip()
            page_num = page_idx + 1

            if text:
                segments.append(
                    ExtractedSegment(
                        text=text,
                        loc_start=page_num,
                        loc_end=page_num,
                        label=f"Page {page_num}",
                        is_numeric_export=is_mostly_numbers(text),
                    )
                )
            elif len(page.images) > 0:
                # Scanned page with image
                filename = Path(path).name
                scan_note = f"Scanned page {page_num} of {filename} ({len(page.images)} image embedded)"
                segments.append(
                    ExtractedSegment(
                        text=scan_note,
                        loc_start=page_num,
                        loc_end=page_num,
                        label=f"Page {page_num} (Scan)",
                        is_numeric_export=False,
                    )
                )
    except Exception as e:
        print(f"[Extractors] Error reading PDF {path}: {e}")
    return segments


def extract_xlsx_file(path: str) -> List[ExtractedSegment]:
    """
    Extracts text from an Excel spreadsheet (.xlsx):
    Reads each worksheet's name and rows.
    """
    segments = []
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        for sheet_idx, sheet_name in enumerate(wb.sheetnames):
            ws = wb[sheet_name]
            rows_text = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                if cells:
                    rows_text.append(" | ".join(cells))
            if rows_text:
                content = f"Sheet: {sheet_name}\n" + "\n".join(rows_text[:500])
                segments.append(
                    ExtractedSegment(
                        text=content,
                        loc_start=sheet_idx + 1,
                        loc_end=sheet_idx + 1,
                        label=f"Sheet: {sheet_name}",
                        is_numeric_export=is_mostly_numbers(content),
                    )
                )
        wb.close()
    except Exception as e:
        print(f"[Extractors] Error reading XLSX {path}: {e}")
    return segments


def extract_ods_file(path: str) -> List[ExtractedSegment]:
    """
    Extracts text from an OpenDocument Spreadsheet (.ods):
    Reads each sheet's name and rows.
    """
    segments = []
    try:
        with zipfile.ZipFile(path, "r") as z:
            with z.open("content.xml") as f:
                tree = ET.parse(f)
        root = tree.getroot()
        for sheet_idx, table in enumerate(root.iter("{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table")):
            sheet_name = table.attrib.get(
                "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}name", f"Sheet {sheet_idx + 1}"
            )
            rows_text = []
            for row in table.iter("{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table-row"):
                cells = []
                for cell in row.iter("{urn:oasis:names:tc:opendocument:xmlns:table:1.0}table-cell"):
                    txt = "".join(cell.itertext()).strip()
                    if txt:
                        cells.append(txt)
                if cells:
                    rows_text.append(" | ".join(cells))
            if rows_text:
                content = f"Sheet: {sheet_name}\n" + "\n".join(rows_text[:500])
                segments.append(
                    ExtractedSegment(
                        text=content,
                        loc_start=sheet_idx + 1,
                        loc_end=sheet_idx + 1,
                        label=f"Sheet: {sheet_name}",
                        is_numeric_export=is_mostly_numbers(content),
                    )
                )
    except Exception as e:
        print(f"[Extractors] Error reading ODS {path}: {e}")
    return segments


def extract_pptx_file(path: str) -> List[ExtractedSegment]:
    """
    Extracts text from a PowerPoint presentation (.pptx):
    Reads each slide's text and speaker notes.
    """
    segments = []
    try:
        import pptx
        prs = pptx.Presentation(path)
        for slide_idx, slide in enumerate(prs.slides):
            slide_texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        t = paragraph.text.strip()
                        if t:
                            slide_texts.append(t)
            # Speaker notes
            notes_text = ""
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes_text = slide.notes_slide.notes_text_frame.text.strip()

            parts = []
            if slide_texts:
                parts.append("\n".join(slide_texts))
            if notes_text:
                parts.append(f"Speaker Notes:\n{notes_text}")

            if parts:
                full = f"Slide {slide_idx + 1}:\n" + "\n\n".join(parts)
                segments.append(
                    ExtractedSegment(
                        text=full,
                        loc_start=slide_idx + 1,
                        loc_end=slide_idx + 1,
                        label=f"Slide {slide_idx + 1}",
                        is_numeric_export=is_mostly_numbers(full),
                    )
                )
    except Exception as e:
        print(f"[Extractors] Error reading PPTX {path}: {e}")
    return segments


def extract_odp_file(path: str) -> List[ExtractedSegment]:
    """
    Extracts text from an OpenDocument Presentation (.odp):
    Reads each slide's text and notes.
    """
    segments = []
    try:
        with zipfile.ZipFile(path, "r") as z:
            with z.open("content.xml") as f:
                tree = ET.parse(f)
        root = tree.getroot()
        for page_idx, page in enumerate(root.iter("{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}page")):
            page_texts = []
            for elem in page.iter():
                if elem.tag.endswith("}p") or elem.tag.endswith("}h"):
                    t = "".join(elem.itertext()).strip()
                    if t:
                        page_texts.append(t)
            if page_texts:
                full = f"Slide {page_idx + 1}:\n" + "\n".join(page_texts)
                segments.append(
                    ExtractedSegment(
                        text=full,
                        loc_start=page_idx + 1,
                        loc_end=page_idx + 1,
                        label=f"Slide {page_idx + 1}",
                        is_numeric_export=is_mostly_numbers(full),
                    )
                )
    except Exception as e:
        print(f"[Extractors] Error reading ODP {path}: {e}")
    return segments


def extract_image_file(path: str) -> List[ExtractedSegment]:
    """Extracts image metadata and tags using PIL."""
    segments = []
    try:
        from PIL import Image, ExifTags
        with Image.open(path) as img:
            filename = Path(path).name
            meta_parts = [
                f"Image file: {filename}",
                f"Format: {img.format or Path(path).suffix.upper()}",
                f"Size: {img.width}x{img.height}",
            ]

            try:
                exif = img.getexif()
                if exif:
                    exif_details = []
                    for tag_id, val in exif.items():
                        tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                        if isinstance(val, (str, int, float)) and len(str(val)) < 100:
                            exif_details.append(f"{tag_name}: {val}")
                    if exif_details:
                        meta_parts.append("EXIF: " + ", ".join(exif_details[:8]))
            except Exception:
                pass

            summary = " | ".join(meta_parts)
            segments.append(ExtractedSegment(text=summary, loc_start=1, loc_end=1, label="Image Metadata"))
    except Exception as e:
        print(f"[Extractors] Error reading image {path}: {e}")
    return segments


def extract_audio_file(path: str) -> List[ExtractedSegment]:
    """Extracts audio metadata using soundfile or PyAV."""
    segments = []
    filename = Path(path).name
    try:
        import soundfile as sf
        info = sf.info(path)
        dur_sec = round(info.duration, 1)
        summary = f"Audio file: {filename} | Duration: {format_timestamp(dur_sec)} | Sample Rate: {info.samplerate}Hz | Channels: {info.channels} | Format: {info.format}"
        segments.append(ExtractedSegment(text=summary, loc_start=1, loc_end=1, label=f"Audio ({format_timestamp(dur_sec)})"))
    except Exception:
        try:
            import av
            with av.open(path) as container:
                dur_sec = round(float(container.duration or 0) / 1000000, 1) if container.duration else 0
                summary = f"Audio file: {filename} | Duration: {format_timestamp(dur_sec)}"
                segments.append(ExtractedSegment(text=summary, loc_start=1, loc_end=1, label=f"Audio ({format_timestamp(dur_sec)})"))
        except Exception as e:
            segments.append(ExtractedSegment(text=f"Audio file: {filename}", loc_start=1, loc_end=1, label="Audio"))
    return segments


def extract_video_file(path: str) -> List[ExtractedSegment]:
    """Extracts video metadata using PyAV."""
    segments = []
    filename = Path(path).name
    try:
        import av
        with av.open(path) as container:
            dur_sec = round(float(container.duration or 0) / 1000000, 1) if container.duration else 0
            v_stream = next((s for s in container.streams if s.type == "video"), None)
            res = f"{v_stream.width}x{v_stream.height}" if v_stream else "unknown"
            a_stream = next((s for s in container.streams if s.type == "audio"), None)
            audio_info = "with soundtrack" if a_stream else "no audio"
            summary = f"Video file: {filename} | Duration: {format_timestamp(dur_sec)} | Resolution: {res} | {audio_info}"
            segments.append(ExtractedSegment(text=summary, loc_start=1, loc_end=1, label=f"Video ({format_timestamp(dur_sec)})"))
    except Exception as e:
        segments.append(ExtractedSegment(text=f"Video file: {filename}", loc_start=1, loc_end=1, label="Video"))
    return segments


DOC_EXTS = {".pdf", ".docx", ".odt", ".rtf", ".txt", ".md", ".markdown", ".rst", ".org", ".typ", ".html", ".htm"}
SHEET_EXTS = {".xlsx", ".ods", ".pptx", ".odp", ".csv", ".tsv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".jxl", ".heic", ".heif", ".bmp", ".gif", ".tiff", ".tif"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}


def extract_file_content(path: str) -> List[ExtractedSegment]:
    """Route file to appropriate extractor based on extension."""
    ext = Path(path).suffix.lower()

    if ext == ".pdf":
        return extract_pdf_file(path)
    elif ext == ".docx":
        return extract_docx_file(path)
    elif ext == ".rtf":
        return extract_rtf_file(path)
    elif ext == ".odt":
        return extract_odt_file(path)
    elif ext in (".html", ".htm"):
        return extract_html_file(path)
    elif ext == ".xlsx":
        return extract_xlsx_file(path)
    elif ext == ".ods":
        return extract_ods_file(path)
    elif ext == ".pptx":
        return extract_pptx_file(path)
    elif ext == ".odp":
        return extract_odp_file(path)
    elif ext in IMAGE_EXTS:
        return extract_image_file(path)
    elif ext in AUDIO_EXTS:
        return extract_audio_file(path)
    elif ext in VIDEO_EXTS:
        return extract_video_file(path)
    else:
        # Default text, code, typst, markdown, csv, tsv
        return extract_text_file(path)
