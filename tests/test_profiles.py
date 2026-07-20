from pathlib import Path

from executive_docs.profiles import ProfileStore


def test_unapproved_profile_is_not_loaded(tmp_path: Path) -> None:
    (tmp_path / "organization.yaml").write_text(
        "profile_id: organization\nversion: candidate\napproved: false\nvalues:\n  contractor.name: Candidate\n",
        encoding="utf-8",
    )
    assert ProfileStore(tmp_path).claims("khimki") == []


def test_approved_profiles_become_rule_backed_claims(tmp_path: Path) -> None:
    (tmp_path / "organization.yaml").write_text(
        "profile_id: organization\nversion: '1.0'\napproved: true\neffective_from: 2026-01-01\neffective_to: 2026-12-31\nvalues:\n  contractor.name: ООО Тест\n",
        encoding="utf-8",
    )
    (tmp_path / "khimki.yaml").write_text(
        "profile_id: khimki\nversion: '2.0'\napproved: true\neffective_from: 2026-01-01\neffective_to: 2026-12-31\nvalues:\n  customer.name: ПАО Тест\n",
        encoding="utf-8",
    )
    claims = ProfileStore(tmp_path).claims("khimki")
    values = {claim.key: claim.normalized_value for claim in claims}
    assert values["contractor.name"] == "ООО Тест"
    assert values["customer.name"] == "ПАО Тест"
    assert values["customer.profile.version"] == "2.0"
    assert all(claim.rule_id and claim.status.value == "derived" for claim in claims)
