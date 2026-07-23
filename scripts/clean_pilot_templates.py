#!/usr/bin/env python3
"""Create technically cleaned pilot-template candidates while preserving OOXML layout."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from executive_docs.excel import OOXMLWorkbook, sha256, workbook_snapshot  # noqa: E402


PLANS = [
    {
        "template_id": "aosr_kl",
        "source": ROOT / "template" / "9. АОСР КЛ.xlsx",
        "output": ROOT / "templates" / "approved" / "9. АОСР КЛ.xlsx",
        "clear": [
            *(f"B{row}" for row in range(2, 8)),
            "B9",
            "B43",
        ],
        "formulas": {
            "Данные объект": {"B44": "B3"},
            "АОСР-1": {"A53": "'Данные объект'!C21", "A114": "'Данные объект'!B20"},
            "АОСР-2": {"A53": "'Данные объект'!C21", "A115": "'Данные объект'!B20"},
            "АОСР-3": {"A53": "'Данные объект'!C21", "A115": "'Данные объект'!B20"},
            "АОСР-4": {"A53": "'Данные объект'!C21", "A115": "'Данные объект'!B20"},
            "АОСР-5": {"A53": "'Данные объект'!C21", "A115": "'Данные объект'!B20"},
            "АОСР-6": {"A53": "'Данные объект'!C21", "A115": "'Данные объект'!B20"},
            "АОСР-7": {"A53": "'Данные объект'!C21", "A114": "'Данные объект'!B20"},
            "АОСР-пожар": {"A53": "'Данные объект'!C21", "A115": "'Данные объект'!B20"},
        },
        "remove_defined_names": ["кабель"],
        "forbidden_tokens": [
            "SAP - 305042",
            "Красный Воин",
            "4609-305042-221-10/24",
            "КЛ-10кВ ф.1 от ТП №3463",
        ],
    },
    {
        "template_id": "aosr_vrs",
        "source": ROOT / "template" / "10. АОСР ВРЩ.xlsx",
        "output": ROOT / "templates" / "approved" / "10. АОСР ВРЩ.xlsx",
        "clear": [
            *(f"B{row}" for row in range(2, 8)),
            "B9",
            "B43",
        ],
        "formulas": {
            "Данные объект": {
                "B12": "'Данные организации'!C2",
                "B24": "'Данные организации'!G2",
                "B25": "'Данные организации'!G3",
                "B44": "B3",
            },
            "АОСР-1": {"A113": "'Данные объект'!B20"},
            "АОСР-2": {"A119": "'Данные объект'!B20"},
            "АОСР-3": {"A115": "'Данные объект'!B20"},
            "АОСР-4": {"A115": "'Данные объект'!B20"},
            "АОСР-5": {"A120": "'Данные объект'!B20"},
            "АОСР-6": {"A118": "'Данные объект'!B20"},
        },
        "remove_defined_names": [],
        "forbidden_tokens": [
            "SAP - 301971",
            "Жилино",
            "3746-984421-20-02/23",
        ],
    },
]


def package_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        return "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in archive.namelist()
            if name.endswith((".xml", ".rels"))
        )


def print_signature(snapshot: dict) -> list[tuple[str, str, str | None, str | None]]:
    return [
        (item["name"], item["print_area"], item["page_orientation"], item["paper_size"])
        for item in snapshot["sheets"]
    ]


def clean(plan: dict) -> dict:
    source_snapshot = workbook_snapshot(plan["source"])
    workbook = OOXMLWorkbook(plan["source"])
    for coordinate in plan["clear"]:
        workbook.clear_cell("Данные объект", coordinate)
    for sheet_name, formulas in plan["formulas"].items():
        for coordinate, formula in formulas.items():
            workbook.set_formula(sheet_name, coordinate, formula)
    for name in plan["remove_defined_names"]:
        workbook.remove_defined_name(name)
    workbook.remove_external_links()
    workbook.clear_formula_caches()
    workbook.remove_calculation_chain()
    workbook.prune_shared_strings()
    workbook.enable_full_calculation()
    workbook.save(plan["output"])

    output_snapshot = workbook_snapshot(plan["output"])
    text = package_text(plan["output"])
    errors = [error for sheet in output_snapshot["sheets"] for error in sheet["errors"]]
    errors.extend(output_snapshot["defined_name_errors"])
    stale = [token for token in plan["forbidden_tokens"] if token in text]
    checks = {
        "valid_zip": zipfile.ZipFile(plan["output"]).testzip() is None,
        "sheet_order_unchanged": [item["name"] for item in source_snapshot["sheets"]]
        == [item["name"] for item in output_snapshot["sheets"]],
        "print_configuration_unchanged": print_signature(source_snapshot) == print_signature(output_snapshot),
        "formula_errors_removed": not errors,
        "external_links_removed": output_snapshot["external_links"] == 0,
        "stale_tokens_removed": not stale,
    }
    return {
        "template_id": plan["template_id"],
        "source": plan["source"].relative_to(ROOT).as_posix(),
        "output": plan["output"].relative_to(ROOT).as_posix(),
        "source_sha256": source_snapshot["sha256"],
        "candidate_sha256": sha256(plan["output"]),
        "checks": checks,
        "errors": errors,
        "stale_tokens": stale,
        "status": "READY_FOR_VISUAL_APPROVAL" if all(checks.values()) else "BLOCKED",
    }


def main() -> int:
    results = [clean(plan) for plan in PLANS]
    report = {
        "purpose": "Technical cleanup only. Specialist visual/semantic approval is still required.",
        "templates": results,
    }
    destination = ROOT / "templates" / "approved" / "cleanup-report.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["status"] == "READY_FOR_VISUAL_APPROVAL" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
