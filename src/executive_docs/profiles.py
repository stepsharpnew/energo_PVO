from __future__ import annotations

from pathlib import Path

from .domain import Claim


def is_profile_metadata_key(key: str) -> bool:
    """Recognize retired profile controls, including saved legacy answers."""

    normalized = key.strip().lower()
    return ".profile." in normalized or normalized.endswith(".profile_confirmation")


def is_profile_claim(claim: Claim) -> bool:
    """A legacy approval flag must never make a profile into project evidence."""

    return (
        "profile" in claim.source_kind.strip().lower()
        or (claim.rule_id or "").strip().lower().startswith("profile:")
        or is_profile_metadata_key(claim.key)
    )


class ProfileStore:
    """Deprecated compatibility facade; saved profile files are never consulted.

    Keep the import and constructor available for legacy callers without
    deleting or migrating their profile files. All new facts must come from
    the current project's evidence, not a reusable organization directory.
    """

    def __init__(self, profiles_dir: Path):
        self.profiles_dir = profiles_dir

    def claims(self, branch_id: str) -> list[Claim]:
        return []
