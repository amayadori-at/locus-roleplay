from __future__ import annotations

import re


LOCUS_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def is_locus_id(value: str) -> bool:
    return LOCUS_ID_PATTERN.fullmatch(value) is not None
