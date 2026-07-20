from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path

import openpyxl
from lxml import etree
from pypdf import PdfReader

from .domain import Artifact


ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".docx", ".png", ".jpg", ".jpeg", ".csv", ".txt"}
MAX_OFFICE_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_OFFICE_COMPRESSION_RATIO = 300


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


def build_inventory(root: Path, artifacts: list[Artifact]) -> tuple[list[Artifact], str]:
    updated: list[Artifact] = []
    manifest: list[dict] = []
    for artifact in artifacts:
        path = root / "input" / artifact.stored_name
        validate_signature(path)
        preview = ""
        pages = None
        try:
            preview, pages = extract_source(path, pages=[1, 2] if path.suffix.lower() == ".pdf" else None)
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
                "preview": re.sub(r"\s+", " ", preview)[:1200],
            }
        )
    return updated, json.dumps(manifest, ensure_ascii=False, indent=2)
