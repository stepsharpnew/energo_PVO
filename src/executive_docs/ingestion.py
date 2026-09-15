from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
import threading
import warnings
import zipfile
from pathlib import Path

import openpyxl
from lxml import etree
from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from .domain import Artifact


ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".docx", ".png", ".jpg", ".jpeg", ".csv", ".txt"}
MAX_OFFICE_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_OFFICE_COMPRESSION_RATIO = 300
EXTRACTOR_VERSION = "4"
VISUAL_PAGE_LABEL_VERSION = "original-page-labels-1"
VISUAL_PAGE_LABEL_HEIGHT = 28

PILOT_PATTERNS = {
    "kl_04": (r"(?<![а-яa-z])кл\s*[-–—]?\s*0[,.]4", r"кабельн\w*\s+лини\w*\s+0[,.]4"),
    "kl_6": (r"(?<![а-яa-z])кл\s*[-–—]?\s*6(?:\s*кв)?", r"кабельн\w*\s+лини\w*\s+6\s*кв"),
    "vrs": (r"\bврщ\b", r"вводно[- ]распределительн\w*\s+щит"),
}
OUT_OF_SCOPE_PATTERNS = {
    "ktp": (r"\bктп\b", r"трансформаторн\w*\s+подстанц"),
    "vl": (r"\bвл\s*[-–—]?\s*6", r"воздушн\w*\s+лини"),
    "geo": (r"\bгео\b", r"геодез"),
    "gnb": (r"\bгнб\b",),
    "avk": (r"\bавк\b",),
    "emr": (r"\bэмр\b",),
}
EVIDENCE_TERMS = (
    "рабочий проект",
    "технические условия",
    "наименование объекта",
    "адрес",
    "шифр",
    "ведомость объемов",
    "ведомость объёмов",
    "спецификация",
    "кабельная линия",
    "кл-0,4",
    "кл 0,4",
    "кл-6",
    "кл 6",
    "врщ",
    "исполнительная схема",
    "сертификат",
    "паспорт",
)


def validate_signature(path: Path) -> None:
    ext = path.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Неподдерживаемый формат: {ext}")
    head = path.read_bytes()[:16]
    if ext == ".pdf" and not head.startswith(b"%PDF-"):
        raise ValueError("Расширение PDF не соответствует содержимому")
    if ext in {".xlsx", ".docx"} and not head.startswith(b"PK"):
        raise ValueError("Файл Office не является OOXML ZIP")
    if ext in {".xlsx", ".docx"}:
        try:
            with zipfile.ZipFile(path) as archive:
                members = archive.infolist()
                total = sum(item.file_size for item in members)
                compressed = sum(item.compress_size for item in members)
                if any(item.flag_bits & 0x1 for item in members):
                    raise ValueError("Зашифрованные Office-файлы не поддерживаются")
                if total > MAX_OFFICE_UNCOMPRESSED_BYTES or (compressed and total / compressed > MAX_OFFICE_COMPRESSION_RATIO):
                    raise ValueError("Подозрительный коэффициент сжатия Office-файла")
                required = "xl/workbook.xml" if ext == ".xlsx" else "word/document.xml"
                if required not in archive.namelist() or archive.testzip():
                    raise ValueError("Повреждённая структура OOXML")
        except zipfile.BadZipFile as exc:
            raise ValueError("Повреждённый OOXML ZIP") from exc
    if ext == ".png" and not head.startswith(b"\x89PNG"):
        raise ValueError("Некорректный PNG")
    if ext in {".jpg", ".jpeg"} and not head.startswith(b"\xff\xd8"):
        raise ValueError("Некорректный JPEG")


def classify(path: Path, preview: str = "", original_name: str | None = None) -> str:
    name = (original_name or path.name).lower()
    text = (name + " " + preview[:4000]).lower()
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        return "image_evidence"
    if "сертифик" in text:
        return "certificate"
    if "паспорт" in text:
        return "passport"
    if "аттест" in text:
        return "attestation"
    if path.suffix.lower() == ".xlsx" and ("акт освидетельствования скрытых работ" in text or name.startswith("аоср")):
        return "filled_aosr"
    if "исполнительн" in text or (path.suffix.lower() == ".pdf" and name.startswith("аоср")) or "ис гео" in name:
        return "execution_scheme"
    if "техническ" in text and "услов" in text:
        return "technical_conditions"
    if "рабочий проект" in text or "состав проекта" in text:
        return "project"
    if path.suffix.lower() == ".xlsx":
        return "spreadsheet"
    return "source"


def extract_pdf(path: Path, page_numbers: list[int] | None = None, max_chars: int = 60_000) -> tuple[str, int]:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ValueError("Зашифрованные PDF не поддерживаются")
    pages = page_numbers or list(range(1, len(reader.pages) + 1))
    chunks: list[str] = []
    for number in pages:
        if number < 1 or number > len(reader.pages):
            continue
        text = reader.pages[number - 1].extract_text() or ""
        chunks.append(f"\n--- PAGE {number} ---\n{text}")
        if sum(map(len, chunks)) >= max_chars:
            chunks.append("\n[TRUNCATED]")
            break
    return "".join(chunks)[:max_chars], len(reader.pages)


def extract_docx(path: Path, max_chars: int = 60_000) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = etree.fromstring(xml)
    text = "\n".join(root.itertext())
    return text[:max_chars]


def extract_xlsx(path: Path, sheet_names: list[str] | None = None, max_chars: int = 60_000) -> str:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=False, keep_links=True)
    names = sheet_names or workbook.sheetnames
    chunks: list[str] = []
    for name in names:
        if name not in workbook.sheetnames:
            continue
        sheet = workbook[name]
        chunks.append(f"\n--- SHEET {name} [{sheet.sheet_state}] ---")
        for row in sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 1000)):
            values = [f"{cell.coordinate}={cell.value}" for cell in row if cell.value not in (None, "")]
            if values:
                chunks.append(" | ".join(values))
            if sum(map(len, chunks)) >= max_chars:
                chunks.append("[TRUNCATED]")
                return "\n".join(chunks)[:max_chars]
    return "\n".join(chunks)[:max_chars]


def extract_csv(path: Path, max_chars: int = 60_000) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    rows = csv.reader(io.StringIO(text))
    return "\n".join(" | ".join(row) for row in rows)[:max_chars]


def extract_source(path: Path, *, pages: list[int] | None = None, sheets: list[str] | None = None) -> tuple[str, int | None]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf(path, pages)
    if ext == ".xlsx":
        return extract_xlsx(path, sheets), None
    if ext == ".docx":
        return extract_docx(path), None
    if ext == ".csv":
        return extract_csv(path), None
    if ext == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")[:60_000], None
    return f"Binary image {path.name}; use the uploaded image as visual evidence.", None


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace("ё", "е")).strip()


def detect_scope(text: str, original_name: str) -> str:
    """Route paid context; this is not accepted as factual document evidence."""
    content = _normalized(text)
    name = _normalized(original_name)
    # Explicit names are a cheap routing hint, never a Claim. Content remains
    # available in the inventory, and unknown/conflicting files stay eligible
    # for model inspection rather than becoming document facts here.
    for source in (name, content[:2_500], content):
        for family, patterns in PILOT_PATTERNS.items():
            if any(re.search(pattern, source) for pattern in patterns):
                return family
        for family, patterns in OUT_OF_SCOPE_PATTERNS.items():
            if any(re.search(pattern, source) for pattern in patterns):
                return family
    return "unknown"


def _segment_score(text: str, *, first: bool = False) -> int:
    normalized = _normalized(text)
    score = 20 if first else 0
    score += sum(12 for term in EVIDENCE_TERMS if term in normalized)
    score += min(len(text) // 1000, 12)
    return score


def _pdf_text_reliability(text: str) -> tuple[bool, str | None]:
    """Detect a broken or overlay-only text layer without guessing its contents."""
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False, "no_text_layer"
    invalid = sum(
        (ord(char) < 32 and char not in "\n\r\t\f")
        or char == "\ufffd"
        or "\ue000" <= char <= "\uf8ff"
        for char in text
    )
    if invalid >= 2 and invalid / len(compact) >= 0.005:
        return False, "broken_font_encoding"
    # Broken ToUnicode maps can turn Cyrillic letters into Latin Extended
    # glyphs (e.g. "ǚтǹоитǮлȅǺтǫо") without emitting replacement characters.
    mixed_words = sum(
        bool(re.search(r"[А-Яа-яЁё]", word))
        and bool(re.search(r"[\u0100-\u024f]", word))
        for word in re.findall(r"[^\W\d_]+", text)
    )
    if mixed_words >= 3:
        return False, "broken_font_encoding"
    if len(re.findall(r"\(cid:\d+\)", text)) >= 2:
        return False, "unmapped_font_glyphs"
    # A scanned page can contain hundreds of perfectly readable characters
    # belonging only to its electronic-signature overlay, not the page body.
    without_signature = re.sub(
        r"ДОКУМЕНТ\s+ПОДПИСАН\s+ЭЛЕКТРОННОЙ\s+ПОДПИСЬЮ"
        r".*?Оператор\s+ЭДО[^\r\n]*(?:\r?\n|$)",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if without_signature != text and len(re.sub(r"\s+", "", without_signature)) < 80:
        return False, "electronic_signature_overlay_only"
    return True, None


def _pdf_layout_text(page: PageObject, *, diagnostics: dict | None = None) -> str | None:
    """Supplement plain extraction with column spacing, never guessed OCR.

    The supported strip-rotated warning means upright table text remains
    usable but incomplete; retain that warning. Degraded layout/font geometry
    or extraction errors fall back to the plain text and visual route.
    """
    thread_id = threading.get_ident()

    class LayoutWarnings(logging.Handler):
        def __init__(self) -> None:
            super().__init__()
            self.messages: list[str] = []

        def emit(self, record: logging.LogRecord) -> None:
            if record.thread == thread_id and record.levelno >= logging.WARNING:
                self.messages.append(record.getMessage())

    handler = LayoutWarnings()
    logger = logging.getLogger("pypdf")
    logger.addHandler(handler)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            text = page.extract_text(extraction_mode="layout", layout_mode_strip_rotated=True) or ""
        messages = handler.messages + [str(item.message) for item in caught]
        if any(message != "Rotated text discovered. Output will be incomplete." for message in messages):
            return None
        if messages and diagnostics is not None:
            diagnostics["layout_text_partial"] = True
            diagnostics["layout_text_warnings"] = sorted(set(messages))
        return text[:25_000] if text.strip() else None
    except Exception:
        return None
    finally:
        logger.removeHandler(handler)


def _build_segments(path: Path) -> tuple[list[dict], int | None]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ValueError("Зашифрованные PDF не поддерживаются")
        segments = []
        for number, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "")[:25_000]
            layout_diagnostics: dict = {}
            layout_text = _pdf_layout_text(page, diagnostics=layout_diagnostics)
            text_reliable, text_reliability_reason = _pdf_text_reliability(text)
            segments.append(
                {
                    "locator": f"page:{number}",
                    "page": number,
                    "sheet": None,
                    "text": text,
                    "layout_text": layout_text,
                    "layout_text_reliable": bool(layout_text and _pdf_text_reliability(layout_text)[0]),
                    **layout_diagnostics,
                    "char_count": len(text),
                    "text_reliable": text_reliable,
                    "text_reliability_reason": text_reliability_reason,
                    "visual_required": not text_reliable or len(re.sub(r"\s+", "", text)) < 80,
                    "score": _segment_score(text, first=number == 1),
                }
            )
        return segments, len(reader.pages)
    if ext == ".xlsx":
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=False, keep_links=True)
        segments = []
        try:
            for position, sheet in enumerate(workbook.worksheets):
                lines = [f"--- SHEET {sheet.title} [{sheet.sheet_state}] ---"]
                for row in sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 1000)):
                    values = [f"{cell.coordinate}={cell.value}" for cell in row if cell.value not in (None, "")]
                    if values:
                        lines.append(" | ".join(values))
                    if sum(map(len, lines)) >= 25_000:
                        lines.append("[TRUNCATED]")
                        break
                text = "\n".join(lines)[:25_000]
                segments.append(
                    {
                        "locator": f"sheet:{sheet.title}",
                        "page": None,
                        "sheet": sheet.title,
                        "text": text,
                        "char_count": len(text),
                        "visual_required": False,
                        "score": _segment_score(text, first=position == 0),
                    }
                )
        finally:
            workbook.close()
        return segments, None
    text, pages = extract_source(path)
    return (
        [
            {
                "locator": "file",
                "page": None,
                "sheet": None,
                "text": text,
                "char_count": len(text),
                "visual_required": ext in {".png", ".jpg", ".jpeg"},
                "score": _segment_score(text, first=True),
            }
        ],
        pages,
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_index(root: Path, artifact: Artifact) -> dict:
    path = root / "input" / artifact.stored_name
    cache_dir = root / "extracted"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{artifact.sha256}-{EXTRACTOR_VERSION}.json"
    digest = _file_sha256(path)
    if digest != artifact.sha256:
        raise ValueError(f"Файл {artifact.original_name} изменился после загрузки")
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("sha256") == artifact.sha256 and cached.get("extractor_version") == EXTRACTOR_VERSION:
                joined = "\n".join(item.get("text", "") for item in cached.get("segments", []))
                # Extraction is content-addressed, while a filename is only a
                # routing hint. Rebind routing metadata for duplicate bytes
                # uploaded under different names.
                cached["original_name"] = artifact.original_name
                cached["scope"] = detect_scope(joined[:120_000], artifact.original_name)
                return cached
        except (OSError, json.JSONDecodeError):
            pass
    segments, pages = _build_segments(path)
    joined = "\n".join(item["text"] for item in segments)
    payload = {
        "extractor_version": EXTRACTOR_VERSION,
        "sha256": artifact.sha256,
        "original_name": artifact.original_name,
        "pages": pages,
        "scope": detect_scope(joined[:120_000], artifact.original_name),
        "segments": segments,
    }
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(cache_path)
    return payload


def read_indexed_source(
    root: Path,
    artifact: Artifact,
    *,
    pages: list[int] | None = None,
    sheets: list[str] | None = None,
    max_chars: int = 18_000,
    include_layout: bool = False,
) -> tuple[str, int | None]:
    index = source_index(root, artifact)
    selected = []
    page_set = set(pages or [])
    sheet_set = set(sheets or [])
    for segment in index["segments"]:
        if page_set and segment.get("page") not in page_set:
            continue
        if sheet_set and segment.get("sheet") not in sheet_set:
            continue
        reliability_note = (
            "[UNRELIABLE TEXT LAYER: read the supplied page image for exact values; "
            f"reason={segment.get('text_reliability_reason', 'unknown')}]\n"
            if segment.get("text_reliable") is False
            else ""
        )
        layout = segment.get("layout_text") if include_layout and segment.get("layout_text_reliable") else None
        layout_block = (f"[LAYOUT EXTRACT: same physical page; rotated text may be omitted]\n{layout}\n[PLAIN EXTRACT]\n"
                        if layout else "")
        selected.append(f"\n--- {segment['locator']} ---\n{layout_block}{reliability_note}{segment['text']}")
    text = "".join(selected)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[TRUNCATED BY SOURCE BUDGET]"
    return text, index.get("pages")


def _pilot_match_count(text: str) -> int:
    normalized = _normalized(text)
    return sum(
        len(re.findall(pattern, normalized))
        for patterns in PILOT_PATTERNS.values()
        for pattern in patterns
    )


def _segment_context_score(segment: dict, *, project: bool) -> int:
    score = int(segment.get("score") or 0)
    matches = _pilot_match_count(segment.get("text", ""))
    if project:
        if segment.get("visual_required"):
            score += 1_200
        if matches:
            score += 900 + min(matches, 20) * 40
        if segment.get("page") == 1:
            score += 800
    elif segment.get("visual_required"):
        score += 600
    return score


def _selected_template_text_score(segment: dict) -> int:
    """Prefer useful readable PDF facts, independent of legacy KL/VRS pilots."""
    reliable = segment.get("text_reliable", True) or segment.get("layout_text_reliable", False)
    text = _normalized(str(segment.get("text") or "") + " " + str(segment.get("layout_text") or ""))
    score = 1_000 if reliable else 0
    if any(term in text for term in ("спецификац", "наименование и техническ", "количество", "кол-во")):
        score += 650
    if any(term in text for term in ("ведомость объем", "ведомость объём", "материал", "оборудован")):
        score += 350
    if any(term in text for term in ("заказчик", "проектная организация", "подрядчик", "застройщик", "реквизит", "огрн", "инн")):
        score += 500
    if segment.get("page") == 1:
        score += 300
    return score


def build_compact_evidence(
    root: Path,
    artifacts: list[Artifact],
    max_chars: int,
    *,
    selected_template: bool = False,
) -> list[dict]:
    candidates: list[tuple[int, Artifact, dict, str]] = []
    for artifact in artifacts:
        selected_pdf = selected_template and Path(artifact.original_name).suffix.lower() == ".pdf"
        if artifact.category == "filled_aosr" and not selected_pdf:
            continue
        index = source_index(root, artifact)
        scope = index.get("scope", "unknown")
        if not selected_pdf and artifact.category == "execution_scheme" and scope in OUT_OF_SCOPE_PATTERNS:
            continue
        is_project = selected_pdf or artifact.category in {"project", "technical_conditions"}
        per_file = len(index["segments"]) if selected_pdf else (32 if is_project else 3)
        score_segment = _selected_template_text_score if selected_pdf else lambda item: _segment_context_score(item, project=is_project)
        ranked = sorted(
            index["segments"],
            key=lambda item: (-score_segment(item), int(item.get("page") or 0) if selected_pdf else 0, str(item["locator"])),
        )[:per_file]
        category_bonus = {
            "project": 50,
            "technical_conditions": 45,
            "execution_scheme": 40,
            "passport": 35,
            "certificate": 35,
            "attestation": 30,
        }.get(artifact.category, 10)
        for segment in ranked:
            candidates.append(
                (
                    category_bonus + score_segment(segment),
                    artifact,
                    segment,
                    scope,
                )
            )
    packet: list[dict] = []
    used = 2 if selected_template else 0  # JSON list brackets in selected mode.
    for _, artifact, segment, scope in sorted(candidates, key=lambda item: -item[0]):
        if used >= max_chars:
            break
        record_overhead = 180
        remaining = max_chars - used - record_overhead
        if remaining <= 0:
            break
        excerpt = segment["text"][: min(8_000, remaining)]
        layout_text = segment.get("layout_text") if segment.get("layout_text_reliable") else None
        if selected_template and layout_text and re.sub(r"\s+", " ", layout_text).strip() != re.sub(r"\s+", " ", segment["text"]).strip():
            # Keep both independently extracted views, with a shared per-page
            # text allowance. Layout gets most space when it restores columns.
            layout_text = layout_text[:min(6_000, remaining)]
            excerpt = excerpt[:max(0, min(2_000, remaining - len(layout_text)))]
        else:
            layout_text = None
        if not excerpt.strip() and not layout_text:
            continue
        record = {
            "file_id": artifact.id,
            "category": artifact.category,
            "scope_hint": scope,
            "locator": segment["locator"],
            "visual_required": segment["visual_required"],
            "text_reliable": segment.get("text_reliable", True),
            "text_reliability_reason": segment.get("text_reliability_reason"),
            "evidence_instruction": (
                "Read the supplied page image for exact values. This extracted text "
                "is incomplete or has broken font encoding; do not quote it as reliable evidence."
                if segment.get("text_reliable") is False
                else None
            ),
            "text": excerpt,
        }
        if layout_text:
            record["layout_text"] = layout_text
            record["layout_text_reliable"] = True
            if segment.get("layout_text_partial"):
                record["layout_text_partial"] = True
                record["layout_text_warnings"] = segment.get("layout_text_warnings", [])
        if selected_template:
            separator = 2 if packet else 0
            # Count actual serialized text, including escaped control chars
            # from broken fonts, instead of assuming fixed record overhead.
            record_size = len(json.dumps(record, ensure_ascii=False))
            while used + separator + record_size > max_chars:
                overflow = used + separator + record_size - max_chars
                key = "text" if record["text"] else "layout_text"
                if not record.get(key):
                    break
                record[key] = record[key][:max(0, len(record[key]) - overflow)]
                record_size = len(json.dumps(record, ensure_ascii=False))
            if used + separator + record_size > max_chars or not (record["text"].strip() or record.get("layout_text", "").strip()):
                continue
            used += separator + record_size
        else:
            used += len(excerpt) + record_overhead
        packet.append(record)
    return packet


def _selected_pdf_pages(index: dict, *, project: bool, limit: int | None = None) -> list[int]:
    segments = [item for item in index["segments"] if item.get("page")]
    effective_limit = limit if limit is not None else (len(segments) if project else 4)
    ranked = sorted(
        segments,
        key=lambda item: (-_segment_context_score(item, project=project), int(item["page"])),
    )
    return sorted(int(item["page"]) for item in ranked[:effective_limit])


def _label_visual_page(source_page: PageObject, original_page: int) -> PageObject:
    """Add a separate top band without scaling or covering source content.

    Normalize rotation on a copy, then preserve exactly the original visible
    CropBox. Translating that viewport to the origin avoids clipping pages
    whose media/crop boxes do not start at (0, 0).
    """
    # Clone into an owned writer before transforming content. This avoids
    # mutating reader-owned streams and is compatible with pypdf's strict
    # ownership rules for replace_contents/rotation normalization.
    page = PdfWriter().add_page(source_page)
    if page.rotation:
        page.transfer_rotation_to_content()
    left, bottom = float(page.cropbox.left), float(page.cropbox.bottom)
    width, height = float(page.cropbox.width), float(page.cropbox.height)
    if width <= 0 or height <= 0:
        raise ValueError("PDF page has an invalid visible page box")
    result = PageObject.create_blank_page(width=width, height=height + VISUAL_PAGE_LABEL_HEIGHT)
    if "/UserUnit" in page:
        result[NameObject("/UserUnit")] = page["/UserUnit"]
    result.merge_transformed_page(page, Transformation().translate(-left, -bottom))

    # Standard PDF font: routing must not depend on installed OS fonts or add
    # a new runtime dependency just to label the source page number.
    label = f"Original PDF page: {original_page}"
    font_size = min(14.0, width / (len(label) * 0.6 + 2))
    label_page = PageObject.create_blank_page(width=width, height=height + VISUAL_PAGE_LABEL_HEIGHT)
    label_page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/VisualPageLabel"): DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }),
        }),
    })
    stream = DecodedStreamObject()
    stream.set_data((
        f"q 1 1 1 rg 0 {height:g} {width:g} {VISUAL_PAGE_LABEL_HEIGHT} re f "
        f"0 0 0 rg BT /VisualPageLabel {font_size:g} Tf "
        f"{font_size:g} {height + 9:g} Td ({label}) Tj ET Q"
    ).encode("ascii"))
    label_page[NameObject("/Contents")] = stream
    result.merge_page(label_page)
    return result


def _pdf_subset(source: Path, destination: Path, pages: list[int], *, label_original_pages: bool = False) -> Path:
    source_hash = _file_sha256(source) if label_original_pages else None
    if destination.exists():
        try:
            cached = PdfReader(str(destination))
            metadata = cached.metadata or {}
            labels_match = not label_original_pages or (
                metadata.get("/ExecutiveDocsVisualVersion") == VISUAL_PAGE_LABEL_VERSION
                and metadata.get("/ExecutiveDocsVisualPages") == json.dumps(pages)
                and metadata.get("/ExecutiveDocsSourceSHA256") == source_hash
            )
            if not cached.is_encrypted and len(cached.pages) == len(pages) and labels_match:
                return destination
        except Exception:
            pass
    reader = PdfReader(str(source))
    writer = PdfWriter()
    for page in pages:
        if 1 <= page <= len(reader.pages):
            original = reader.pages[page - 1]
            writer.add_page(_label_visual_page(original, page) if label_original_pages else original)
        elif label_original_pages:
            raise ValueError(f"Visual page {page} is outside the source PDF")
    if label_original_pages:
        writer.add_metadata({
            "/ExecutiveDocsVisualVersion": VISUAL_PAGE_LABEL_VERSION,
            "/ExecutiveDocsVisualPages": json.dumps(pages),
            "/ExecutiveDocsSourceSHA256": source_hash,
        })
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        writer.write(stream)
    temporary.replace(destination)
    return destination


def select_visual_sources(
    root: Path,
    artifacts: list[Artifact],
    *,
    max_pages: int,
    include_project: bool,
    selected_template: bool = False,
) -> list[dict]:
    page_candidates: list[tuple[int, str, int, Artifact, Path, str, bool]] = []
    for artifact in artifacts:
        path = root / "input" / artifact.stored_name
        ext = path.suffix.lower()
        selected_pdf = selected_template and ext == ".pdf"
        index = source_index(root, artifact)
        scope = index.get("scope", "unknown")
        if artifact.category == "filled_aosr" and not selected_pdf:
            continue
        if not selected_pdf and artifact.category == "execution_scheme" and scope in OUT_OF_SCOPE_PATTERNS:
            continue
        if ext in {".png", ".jpg", ".jpeg"}:
            page_candidates.append((1_250, artifact.original_name.casefold(), 1, artifact, path, "image evidence", True))
            continue
        if ext != ".pdf":
            continue
        is_project = selected_pdf or artifact.category in {"project", "technical_conditions"}
        if is_project and not include_project and not selected_pdf:
            continue
        visually_relevant = artifact.category == "execution_scheme" or is_project or any(
            item.get("visual_required") for item in index["segments"]
        )
        if not visually_relevant:
            continue
        segments = {int(item["page"]): item for item in index["segments"] if item.get("page")}
        if is_project:
            pages = _selected_pdf_pages(index, project=True, limit=None)
        elif artifact.category == "execution_scheme":
            pages = _selected_pdf_pages(index, project=False, limit=len(index["segments"]))
        else:
            visual_pages = [int(item["page"]) for item in index["segments"] if item.get("page") and item.get("visual_required")]
            pages = visual_pages or _selected_pdf_pages(index, project=False, limit=4)
        for page in pages:
            segment = segments[page]
            required = False
            if is_project:
                if segment.get("visual_required"):
                    priority, reason = 1_300, "project page without reliable text layer"
                    required = True
                elif selected_pdf:
                    priority = 500 + _selected_template_text_score(segment)
                    reason = "selected-template readable table or role evidence"
                elif _pilot_match_count(segment.get("text", "")):
                    priority, reason = 1_100 + min(_pilot_match_count(segment.get("text", "")), 20), "pilot-family project evidence"
                elif page == 1:
                    priority, reason = 1_000, "project title page"
                else:
                    priority, reason = 500 + int(segment.get("score") or 0), "ranked project evidence"
            elif artifact.category == "execution_scheme":
                priority = 1_200 if scope in PILOT_PATTERNS else 900
                reason = "pilot execution scheme" if scope in PILOT_PATTERNS else "unclassified execution scheme"
                required = True
            else:
                priority, reason = 800 + int(segment.get("visual_required") or 0) * 100, "visual source evidence"
                required = bool(segment.get("visual_required"))
            page_candidates.append((priority, artifact.original_name.casefold(), page, artifact, path, reason, required))

    ranked = sorted(page_candidates, key=lambda item: (-item[0], item[1], item[2]))
    required_candidates = [item for item in ranked if item[6]]
    if len(required_candidates) > max_pages:
        raise ValueError(
            f"Минимально необходимый визуальный контекст требует {len(required_candidates)} страниц, "
            f"а выбранный профиль разрешает {max_pages}. Используйте более высокий профиль или увеличьте лимит."
        )
    required_keys = {(item[3].id, item[2]) for item in required_candidates}
    optional = [item for item in ranked if (item[3].id, item[2]) not in required_keys]
    chosen = required_candidates + optional[: max_pages - len(required_candidates)]
    chosen.sort(key=lambda item: (-item[0], item[1], item[2]))
    grouped: dict[str, dict] = {}
    for priority, _, page, artifact, path, reason, _ in chosen:
        item = grouped.setdefault(
            artifact.id,
            {"artifact": artifact, "source_path": path, "pages": [], "reasons": set(), "priority": priority},
        )
        item["pages"].append(page)
        item["reasons"].add(reason)
        item["priority"] = max(item["priority"], priority)

    selected: list[dict] = []
    for item in sorted(grouped.values(), key=lambda value: (-value["priority"], value["artifact"].original_name.casefold())):
        artifact = item["artifact"]
        path = item["source_path"]
        pages = sorted(set(item["pages"]))
        visual_path = path
        if path.suffix.lower() == ".pdf":
            total_pages = int(source_index(root, artifact).get("pages") or len(pages))
            if selected_template or pages != list(range(1, total_pages + 1)):
                cache_key = ",".join(map(str, pages))
                if selected_template:
                    cache_key = f"{VISUAL_PAGE_LABEL_VERSION}:{cache_key}"
                suffix = hashlib.sha256(cache_key.encode()).hexdigest()[:10]
                visual_path = _pdf_subset(
                    path, root / "extracted" / "visual" / f"{artifact.sha256}-{suffix}.pdf", pages,
                    label_original_pages=selected_template,
                )
        selected.append(
            {
                "artifact": artifact,
                "path": visual_path,
                "pages": pages,
                "reason": "; ".join(sorted(item["reasons"])),
            }
        )
    return selected


def build_inventory(root: Path, artifacts: list[Artifact]) -> tuple[list[Artifact], str]:
    updated: list[Artifact] = []
    manifest: list[dict] = []
    for artifact in artifacts:
        # Older browsers can serialize an unselected optional <input
        # type="file"> as an empty multipart part. Previous versions stored
        # that sentinel as a zero-byte artifact named "file".
        if artifact.size == 0 and artifact.original_name == "file":
            continue
        path = root / "input" / artifact.stored_name
        validate_signature(path)
        try:
            index = source_index(root, artifact)
            preview = "\n".join(item["text"] for item in index["segments"][:2])
            pages = index.get("pages")
        except Exception as exc:
            raise ValueError(f"Не удалось прочитать {artifact.original_name}: {exc}") from exc
        item = artifact.model_copy(update={"category": classify(path, preview, artifact.original_name), "pages": pages})
        updated.append(item)
        manifest.append(
            {
                "id": item.id,
                "name": item.original_name,
                "stored_name": item.stored_name,
                "category": item.category,
                "media_type": item.media_type,
                "size": item.size,
                "sha256": item.sha256,
                "pages": item.pages,
                "scope_hint": index.get("scope", "unknown"),
                "preview": re.sub(r"\s+", " ", preview)[:1200],
            }
        )
    return updated, json.dumps(manifest, ensure_ascii=False, indent=2)
