#!/usr/bin/env python3
"""Approve a manually checked organization or customer profile."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ORGANIZATION = {
    "contractor.name",
    "contractor.registration",
    "contractor.address",
    "contractor.construction_control.position",
    "contractor.construction_control.name",
    "contractor.construction_control.authority",
    "contractor.work_supervisor.position",
    "contractor.work_supervisor.name",
    "contractor.work_supervisor.authority",
    "designer.name",
    "designer.registration",
    "designer.address",
    "designer.issue_city",
}
REQUIRED_CUSTOMER = {
    "customer.name",
    "customer.registration",
    "customer.address",
    "customer.construction_control.position",
    "customer.construction_control.name",
    "customer.construction_control.authority",
    "customer.site_representative.position",
    "customer.site_representative.name",
    "customer.site_representative.authority",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["organization", "khimki", "solnechnogorsk"], required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--effective-from", required=True)
    parser.add_argument("--effective-to", required=True)
    args = parser.parse_args()
    start = date.fromisoformat(args.effective_from)
    end = date.fromisoformat(args.effective_to)
    if end < start:
        raise SystemExit("effective-to cannot be earlier than effective-from")
    path = ROOT / "profiles" / f"{args.profile}.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    values = payload.get("values") or {}
    required = REQUIRED_ORGANIZATION if args.profile == "organization" else REQUIRED_CUSTOMER
    missing = sorted(key for key in required if not str(values.get(key, "")).strip())
    if missing:
        raise SystemExit("Profile fields are empty: " + ", ".join(missing))
    payload.update(
        {
            "version": args.version,
            "approved": True,
            "approved_by": args.approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "effective_from": start.isoformat(),
            "effective_to": end.isoformat(),
        }
    )
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Approved profile {args.profile} version {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
