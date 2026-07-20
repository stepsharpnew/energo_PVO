from __future__ import annotations

from pathlib import Path

import yaml

from .domain import Claim, ClaimStatus


class ProfileStore:
    def __init__(self, profiles_dir: Path):
        self.profiles_dir = profiles_dir

    def _claims_from_file(self, path: Path) -> list[Claim]:
        if not path.exists():
            return []
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not payload.get("approved"):
            return []
        version = str(payload.get("version") or "")
        profile_id = str(payload.get("profile_id") or path.stem)
        values = payload.get("values") or {}
        claims = [
            Claim(
                key=str(key),
                raw_value=str(value),
                normalized_value=str(value),
                source_kind="approved_profile",
                locator=f"{path.name}:values.{key}",
                evidence_fragment=f"Утверждённый профиль {profile_id}, версия {version}",
                status=ClaimStatus.DERIVED,
                rule_id=f"profile:{profile_id}:{version}",
            )
            for key, value in values.items()
            if value not in (None, "")
        ]
        version_key = "customer.profile.version" if profile_id in {"khimki", "solnechnogorsk"} else "organization.profile.version"
        claims.append(
            Claim(
                key=version_key,
                raw_value=version,
                normalized_value=version,
                source_kind="approved_profile",
                locator=f"{path.name}:version",
                evidence_fragment=f"Утверждённый профиль {profile_id}",
                status=ClaimStatus.DERIVED,
                rule_id=f"profile:{profile_id}:{version}",
            )
        )
        for key in ("effective_from", "effective_to"):
            if payload.get(key):
                claims.append(
                    Claim(
                        key=f"{profile_id}.profile.{key}",
                        raw_value=str(payload[key]),
                        normalized_value=str(payload[key]),
                        source_kind="approved_profile",
                        locator=f"{path.name}:{key}",
                        evidence_fragment=f"Период действия профиля {profile_id}",
                        status=ClaimStatus.DERIVED,
                        rule_id=f"profile:{profile_id}:{version}",
                    )
                )
        return claims

    def claims(self, branch_id: str) -> list[Claim]:
        return [
            *self._claims_from_file(self.profiles_dir / "organization.yaml"),
            *self._claims_from_file(self.profiles_dir / f"{branch_id}.yaml"),
        ]
