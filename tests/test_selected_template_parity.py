"""Offline regression cases must never become production filling evidence."""
import importlib.util
from pathlib import Path

import pytest

from executive_docs.excel import OOXMLWorkbook
from executive_docs.selected_templates import TemplateCatalog

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "tests/fixtures/selected-template-parity/ojr-berezhnoy.yaml"
PDF = ROOT / "ETALON/I-354783.Бережной.5557.pdf"
spec = importlib.util.spec_from_file_location("parity_audit", ROOT / "scripts/audit_selected_template_parity.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture(scope="module")
def catalog():
    return TemplateCatalog(ROOT, ROOT / "templates/fill-contracts", ROOT / "templates/approved")


def test_partial_inventory_is_not_claimed_as_complete_etalon_parity(catalog):
    report = module.audit(catalog, "ojr", PDF, case_path=CASE)
    assert report["overall_etalon_coverage"] is None
    assert report["matched_reviewed_pdf_targets"] is None
    assert report["reviewed_pdf_targets"] == 6
    assert report["classification_counts"]["unreviewed"] > 0
    assert ["Раздел5", "B6"] in [list(target) for target in report["unmapped_etalon_changes"]]
    assert any(item["classification"] == "unchanged_example_needs_source_review" for item in report["inventory"])


def test_wrong_pdf_cannot_use_another_projects_expected_values(catalog, tmp_path):
    wrong = tmp_path / "other.pdf"
    wrong.write_bytes(b"not the paired PDF")
    with pytest.raises(ValueError, match="другому шаблону или PDF"):
        module.audit(catalog, "ojr", wrong, case_path=CASE)


def test_blank_output_and_copied_etalon_date_fail_semantic_checks(catalog, tmp_path):
    output = tmp_path / "wrong.xlsx"
    package = OOXMLWorkbook(catalog.candidate_path(catalog.get("ojr")))
    package.set_cell("Данные объект", "B7", "05.05.2026")
    package.save(output)
    report = module.audit(catalog, "ojr", PDF, case_path=CASE, output=output)
    assert report["matched_reviewed_pdf_targets"] == 0
    assert report["failed_checks"] == 7
    assert report["overall_etalon_coverage"] is None
