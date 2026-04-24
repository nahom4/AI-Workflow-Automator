"""
Per-run spec validation: counts how many required fields are populated
in a batch of extracted items. Updates success_rate in site_specs.
"""

from __future__ import annotations

REQUIRED_FIELDS = {"title", "url", "id"}


def success_rate(items: list[dict]) -> float:
    """Fraction of items where all required fields are non-empty."""
    if not items:
        return 0.0
    ok = sum(
        1
        for item in items
        if all(item.get(f) for f in REQUIRED_FIELDS)
    )
    return ok / len(items)


def is_healthy(items: list[dict], threshold: float = 0.6) -> bool:
    return success_rate(items) >= threshold
