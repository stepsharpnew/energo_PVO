from pathlib import Path

import pytest

from executive_docs.config import Settings
from executive_docs.domain import Claim, ClaimStatus, ProjectState
from executive_docs.knowledge import KnowledgeBase
from executive_docs.profiles import ProfileStore, is_profile_claim
from executive_docs.review import IndependentReviewer


def test_unapproved_profile_is_not_loaded(tmp_path: Path) -> None:
    (tmp_path / "organization.yaml").write_text(
        "profile_id: organization\nversion: candidate\napproved: false\nvalues:\n  contractor.name: Candidate\n",
        encoding="utf-8",
    )
    assert ProfileStore(tmp_path).claims("khimki") == []


def test_even_approved_profiles_never_supply_claims(tmp_path: Path) -> None:
    (tmp_path / "organization.yaml").write_text(
        "profile_id: organization\nversion: '1.0'\napproved: true\neffective_from: 2026-01-01\neffective_to: 2026-12-31\nvalues:\n  contractor.name: ООО Тест\n",
        encoding="utf-8",
    )
    (tmp_path / "khimki.yaml").write_text(
        "profile_id: khimki\nversion: '2.0'\napproved: true\neffective_from: 2026-01-01\neffective_to: 2026-12-31\nvalues:\n  customer.name: ПАО Тест\n",
        encoding="utf-8",
    )
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    assert ProfileStore(tmp_path).claims("khimki") == []
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_profile_store_never_opens_even_malformed_files(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "organization.yaml").write_text("not: [valid YAML", encoding="utf-8")
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: pytest.fail("retired profile files must not be read"),
    )
    assert ProfileStore(tmp_path).claims("khimki") == []


def test_settings_do_not_require_a_profile_directory(tmp_path: Path) -> None:
    legacy_path = tmp_path / "profiles"
    legacy_path.write_text("This is not a directory", encoding="utf-8")
    settings = Settings(
        data_dir=tmp_path / "data",
        runs_dir=tmp_path / "runs",
        contracts_dir=tmp_path / "contracts",
        fill_contracts_dir=tmp_path / "fill-contracts",
        approved_templates_dir=tmp_path / "approved",
        profiles_dir=legacy_path,
    )
    settings.ensure_directories()
    assert legacy_path.read_text(encoding="utf-8") == "This is not a directory"
    assert settings.policy("balanced").name == "balanced"


@pytest.mark.parametrize(
    "updates",
    [
        {"source_kind": "approved_profile"},
        {"rule_id": "profile:organization:1.0"},
        {"key": "customer.profile.version"},
        {"key": "customer.profile_confirmation"},
    ],
)
@pytest.mark.parametrize("status", [ClaimStatus.OBSERVED, ClaimStatus.DERIVED, ClaimStatus.HUMAN_CONFIRMED])
def test_retired_claim_cannot_reenter_through_a_different_status(updates: dict, status: ClaimStatus) -> None:
    claim = Claim(
        key="customer.name",
        raw_value="ПАО Тест",
        normalized_value="ПАО Тест",
        source_kind="project_pdf",
        source_file_id="pdf-1",
        locator="page:1",
        evidence_fragment="Заказчик: ПАО Тест",
        status=status,
    )
    assert not is_profile_claim(claim)
    assert is_profile_claim(claim.model_copy(update=updates))


def test_reviewer_rejects_retired_profile_before_any_paid_call(monkeypatch) -> None:
    monkeypatch.setattr(
        "executive_docs.review.OpenAI",
        lambda **_: pytest.fail("no API request may validate retired profile claims"),
    )
    settings = Settings(agent_mode="openai", openai_api_key="test-key")
    state = ProjectState(
        job_id="99999999-9999-9999-9999-999999999999",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        claims=[
            Claim(
                key="customer.name",
                raw_value="ПАО Тест",
                normalized_value="ПАО Тест",
                source_kind="approved_profile",
                locator="khimki.yaml:values.customer.name",
                evidence_fragment="Legacy approved profile",
                status=ClaimStatus.DERIVED,
                rule_id="profile:khimki:1.0",
            )
        ],
    )
    issues = IndependentReviewer(settings, KnowledgeBase(settings.skill_dir)).review(state, [])
    assert [issue.code for issue in issues] == ["PROFILE_SOURCE_RETIRED"]
    assert state.model_usage == []
