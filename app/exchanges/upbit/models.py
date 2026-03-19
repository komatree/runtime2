"""Upbit phase-2 design stubs.

These models are intentionally minimal and non-executable.
They exist to anchor future implementation boundaries without implying
that Upbit support is already built.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UpbitDesignNote:
    """Placeholder design record for future Upbit adapter work."""

    area: str
    note: str
