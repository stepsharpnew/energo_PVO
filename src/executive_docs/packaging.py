from __future__ import annotations

import html
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from .domain import ProjectState, ValidationIssue
from .excel import OOXMLWorkbook, sha256
from .usage import PRICING_SNAPSHOT_DATE, job_estimated_cost


def revision_paths(job_root: Path, revision: int) -> tuple[Path, Path, Path]:
    revision_root = job_root / "output" / "revisions" / f"r{revision}"
    preview_root = job_root / "preview" / f"r{revision}"
    report_root = job_root / "report" / f"r{revision}"
    return revision_root, preview_root, report_root


def render_selected_sheets(
    workbook_path: Path,
    selected_sheets: list[str],
    preview_dir: Path,
    soffice_path: str,
) -> tuple[list[Path], list[ValidationIssue]]:
    preview_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    issues: list[ValidationIssue] = []
    for sheet in selected_sheets:
        with tempfile.TemporaryDirectory(prefix="id-render-") as temporary:
            temp = Path(temporary)
            safe_sheet = "".join(char if char.isalnum() or char in "-_" else "_" for char in sheet)
            render_xlsx = temp / f"{workbook_path.stem}-{safe_sheet}.xlsx"
            libreoffice_profile = temp / "lo-profile"
            package = OOXMLWorkbook(workbook_path)
            package.set_only_visible(sheet)
            package.configure_printing(sheet)
            package.save(render_xlsx)
            try:
                completed = subprocess.run(
                    [
                        soffice_path,
                        f"-env:UserInstallation={libreoffice_profile.as_uri()}",
                        "--headless",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        str(temp),
                        str(render_xlsx),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                issues.append(ValidationIssue(code="RENDER_UNAVAILABLE", severity="error", message=str(exc), artifact=workbook_path.name))
                continue
            pdf = render_xlsx.with_suffix(".pdf")
            if completed.returncode != 0 or not pdf.exists():
                issues.append(ValidationIssue(code="RENDER_FAILED", severity="error", message=(completed.stderr or completed.stdout or "LibreOffice export failed")[-1000:], artifact=workbook_path.name, locator=sheet))
                continue
            destination = preview_dir / f"{workbook_path.stem} - {safe_sheet}.pdf"
            shutil.copy2(pdf, destination)
            try:
                reader = PdfReader(str(destination))
                if not reader.pages:
                    raise ValueError("PDF не содержит страниц")
                if len(reader.pages) > 4:
                    issues.append(ValidationIssue(code="UNEXPECTED_PAGE_COUNT", severity="error", message=f"Один акт занял {len(reader.pages)} страниц", artifact=destination.name))
                for page_number, page in enumerate(reader.pages, 1):
                    width = float(page.mediabox.width)
                    height = float(page.mediabox.height)
                    if width > height:
                        issues.append(ValidationIssue(code="PAGE_ORIENTATION", severity="error", message="Ожидалась книжная ориентация", artifact=destination.name, locator=f"page:{page_number}"))
                    if abs(width - 595.28) > 12 or abs(height - 841.89) > 12:
                        issues.append(ValidationIssue(code="PAGE_NOT_A4", severity="error", message=f"Размер страницы не A4: {width:.1f}×{height:.1f} pt", artifact=destination.name, locator=f"page:{page_number}"))
            except Exception as exc:
                issues.append(ValidationIssue(code="PREVIEW_INVALID", severity="error", message=str(exc), artifact=destination.name))
            outputs.append(destination)
    return outputs, issues


def merge_pdfs(paths: list[Path], destination: Path) -> None:
    writer = PdfWriter()
    for path in paths:
        if not path.exists() or path.suffix.lower() != ".pdf":
            continue
        reader = PdfReader(str(path))
        for page in reader.pages:
            writer.add_page(page)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as stream:
        writer.write(stream)


def write_report(state: ProjectState, job_root: Path) -> tuple[Path, Path, Path]:
    _, _, report_dir = revision_paths(job_root, state.revision)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_json = report_dir / "report.json"
    manifest_json = report_dir / "manifest.json"
    report_html = report_dir / "report.html"
    report_json.write_text(
        json.dumps(
            {
                "job_id": state.job_id,
                "revision": state.revision,
                "status": state.status,
                "summary": state.summary,
                "processing_profile": state.processing_profile,
                "model_usage": [item.model_dump(mode="json") for item in state.model_usage],
                "estimated_cost_usd": job_estimated_cost(state),
                "pricing_snapshot_date": PRICING_SNAPSHOT_DATE,
                "claims": [item.model_dump(mode="json") for item in state.claims],
                "work_items": [item.model_dump(mode="json") for item in state.work_items],
                "document_plans": [item.model_dump(mode="json") for item in state.document_plans],
                "validation_issues": [item.model_dump(mode="json") for item in state.validation_issues],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    issue_rows = "".join(
        f"<tr><td>{html.escape(item.severity)}</td><td>{html.escape(item.code)}</td><td>{html.escape(item.message)}</td></tr>"
        for item in state.validation_issues
    ) or "<tr><td colspan='3'>Ошибок не обнаружено</td></tr>"
    claim_rows = "".join(
        f"<tr><td>{html.escape(item.key)}</td><td>{html.escape(item.normalized_value)}</td><td>{html.escape(item.locator)}</td></tr>"
        for item in state.claims
    )
    usage_rows = "".join(
        f"<tr><td>{html.escape(item.stage)}</td><td>{html.escape(item.model)}</td><td>{item.input_tokens}</td><td>{item.cached_tokens}</td><td>{item.output_tokens}</td><td>{item.estimated_cost_usd if item.estimated_cost_usd is not None else 'нет тарифа'}</td></tr>"
        for item in state.model_usage
    ) or "<tr><td colspan='6'>Платных вызовов не было</td></tr>"
    report_html.write_text(
        f"""<!doctype html><html lang='ru'><meta charset='utf-8'><title>Отчёт {state.job_id}</title>
<style>body{{font:14px Arial;max-width:1100px;margin:30px auto;color:#172033}}table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #d8dfeb;padding:8px;text-align:left}}h1,h2{{color:#153a67}}</style>
<h1>Отчёт по комплекту</h1><p><b>Статус:</b> {html.escape(state.status)}</p><p>{html.escape(state.summary)}</p>
<h2>Расход модели</h2><p><b>Профиль:</b> {html.escape(state.processing_profile)}</p><table><tr><th>Этап</th><th>Модель</th><th>Вход</th><th>Кэш</th><th>Выход</th><th>Оценка, USD</th></tr>{usage_rows}</table>
<h2>Проверки</h2><table><tr><th>Уровень</th><th>Код</th><th>Сообщение</th></tr>{issue_rows}</table>
<h2>Источники значений</h2><table><tr><th>Поле</th><th>Значение</th><th>Источник</th></tr>{claim_rows}</table></html>""",
        encoding="utf-8",
    )
    revision_root, preview_root, _ = revision_paths(job_root, state.revision)
    files = []
    for root in (revision_root, preview_root, report_dir):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path != manifest_json:
                files.append({"path": path.relative_to(job_root).as_posix(), "sha256": sha256(path), "size": path.stat().st_size})
    manifest_json.write_text(
        json.dumps(
            {
                "job_id": state.job_id,
                "revision": state.revision,
                "model": state.model,
                "processing_profile": state.processing_profile,
                "model_usage": [item.model_dump(mode="json") for item in state.model_usage],
                "estimated_cost_usd": job_estimated_cost(state),
                "pricing_snapshot_date": PRICING_SNAPSHOT_DATE,
                "skill_version": state.skill_version,
                "knowledge_version": state.knowledge_version,
                "template_versions": state.template_versions,
                "sources": [item.model_dump(mode="json") for item in state.artifacts],
                "validation_issues": [item.model_dump(mode="json") for item in state.validation_issues],
                "files": files,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return report_html, report_json, manifest_json


def build_result_zip(state: ProjectState, job_root: Path) -> Path:
    destination = job_root / "output" / f"result-r{state.revision}.zip"
    revision_root, preview_root, report_root = revision_paths(job_root, state.revision)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for folder, archive_prefix in (
            (revision_root / "xlsx", Path("xlsx")),
            (revision_root / "attachments", Path("attachments")),
            (preview_root, Path("pdf")),
            (report_root, Path("report")),
        ):
            if not folder.exists():
                continue
            for path in folder.rglob("*"):
                if path.is_file() and path != destination:
                    archive.write(path, archive_prefix / path.relative_to(folder))
    return destination
