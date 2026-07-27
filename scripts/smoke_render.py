#!/usr/bin/env python3
"""Render one generated AOSR sheet to verify the local LibreOffice path."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from executive_docs.domain import Claim, ClaimStatus, DocumentPlan, WorkItem  # noqa: E402
from executive_docs.excel import ExcelGenerator  # noqa: E402
from executive_docs.packaging import render_selected_sheets  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--soffice", default="soffice")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="id-render-smoke-") as temporary:
        root = Path(temporary)
        item = WorkItem(
            id="render-smoke",
            family="kl_04",
            work_type="Устройство трубопровода КЛ-0,4 кВ",
            sequence_index=1,
            actual_start="01.06.2026",
            actual_end="02.06.2026",
            change_state="NO",
            source_claim_keys=["actual.start", "actual.end"],
        )
        plan = DocumentPlan(
            template_id="aosr_kl_04",
            selected_sheets=["АОСР-3"],
            work_item_ids=[item.id],
            first_number=17,
            output_filename="АОСР КЛ-0,4кВ.xlsx",
        )
        claims = [
            Claim(key="actual.start", raw_value=item.actual_start or "", normalized_value=item.actual_start or "", source_kind="human_answer", locator="smoke:start", evidence_fragment="smoke", status=ClaimStatus.HUMAN_CONFIRMED),
            Claim(key="actual.end", raw_value=item.actual_end or "", normalized_value=item.actual_end or "", source_kind="human_answer", locator="smoke:end", evidence_fragment="smoke", status=ClaimStatus.HUMAN_CONFIRMED),
        ]
        output, _ = ExcelGenerator(
            ROOT,
            ROOT / "templates" / "contracts",
            ROOT / "templates" / "approved",
        ).generate(plan, [item], claims, root)
        pdfs, issues = render_selected_sheets(output, plan.selected_sheets, root / "preview", args.soffice)
        print(f"pdf_count={len(pdfs)}")
        for issue in issues:
            print(f"{issue.severity}:{issue.code}:{issue.message}")
        return 1 if issues or len(pdfs) != 1 else 0


if __name__ == "__main__":
    raise SystemExit(main())
