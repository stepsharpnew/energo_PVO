from __future__ import annotations

import hashlib
from pathlib import Path

import yaml


class KnowledgeBase:
    def __init__(self, skill_dir: Path):
        self.skill_dir = skill_dir
        self.references_dir = skill_dir / "references"
        self.index_path = self.references_dir / "index.yaml"

    def instructions(self) -> str:
        return (self.skill_dir / "SKILL.md").read_text(encoding="utf-8")

    def index(self) -> dict:
        if not self.index_path.exists():
            return {"topics": {}}
        return yaml.safe_load(self.index_path.read_text(encoding="utf-8")) or {"topics": {}}

    def topics(self) -> list[str]:
        return sorted((self.index().get("topics") or {}).keys())

    def load(self, topic: str) -> str:
        relative = (self.index().get("topics") or {}).get(topic)
        if not relative:
            return f"Unknown topic: {topic}. Available: {', '.join(self.topics())}"
        path = (self.references_dir / relative).resolve()
        if self.references_dir.resolve() not in path.parents:
            raise ValueError("Knowledge path escapes skill directory")
        return path.read_text(encoding="utf-8")

    def version(self) -> str:
        digest = hashlib.sha256()
        paths = [self.skill_dir / "SKILL.md", *sorted(self.references_dir.rglob("*"))]
        for path in paths:
            if path.is_file():
                digest.update(path.relative_to(self.skill_dir).as_posix().encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()[:12]

    def skill_version(self) -> str:
        return hashlib.sha256((self.skill_dir / "SKILL.md").read_bytes()).hexdigest()[:12]
