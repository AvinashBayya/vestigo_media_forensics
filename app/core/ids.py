"""Prefixed random identifiers (art_…, job_…, ev_…, df_…, rve_…)."""

import re
import uuid

ARTIFACT = "art"
JOB = "job"
EVIDENCE = "ev"
DERIVED_FILE = "df"
REVIEW_EVENT = "rve"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def is_valid_id(value: str, prefix: str) -> bool:
    return re.fullmatch(rf"{prefix}_[0-9a-f]{{32}}", value) is not None
