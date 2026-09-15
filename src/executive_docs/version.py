"""Public application release identity; never expose deployment secrets."""

import os
import re

VERSION = "0.2.0"


def release_revision() -> str:
    revision = os.getenv("APP_REVISION", "")
    return revision if re.fullmatch(r"[0-9a-f]{40}", revision) else "development"
