import zipfile
from pathlib import Path

from executive_docs.domain import ProjectState
from executive_docs.packaging import build_result_zip, revision_paths


def test_result_zip_contains_only_current_revision_in_stable_layout(tmp_path: Path) -> None:
    state = ProjectState(
        job_id="77777777-7777-7777-7777-777777777777",
        revision=2,
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
    )
    old_revision, _, _ = revision_paths(tmp_path, 1)
    (old_revision / "xlsx").mkdir(parents=True)
    (old_revision / "xlsx" / "old.xlsx").write_bytes(b"old")
    revision, preview, report = revision_paths(tmp_path, 2)
    for directory in (revision / "xlsx", revision / "attachments", preview, report):
        directory.mkdir(parents=True, exist_ok=True)
    (revision / "xlsx" / "act.xlsx").write_bytes(b"xlsx")
    (revision / "attachments" / "scheme.pdf").write_bytes(b"pdf")
    (preview / "act.pdf").write_bytes(b"pdf")
    (report / "manifest.json").write_text("{}", encoding="utf-8")
    result = build_result_zip(state, tmp_path)
    with zipfile.ZipFile(result) as archive:
        names = set(archive.namelist())
    assert names == {
        "xlsx/act.xlsx",
        "attachments/scheme.pdf",
        "pdf/act.pdf",
        "report/manifest.json",
    }
