from __future__ import annotations

from app import models


def recommendations_for_reasons(order_line: models.OrderLine, reason_codes: list[str]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []

    if "LOW_STOCK" in reason_codes:
        actions.append(
            {
                "title": "Source alternate supplier",
                "action": "Request quote from a backup distributor and split reorder for remaining quantity.",
                "priority": "high",
            }
        )
    if "ETA_VOLATILITY" in reason_codes:
        actions.append(
            {
                "title": "Resequence dependent work",
                "action": "Shift tasks requiring this SKU by 2-4 days and advance unaffected tasks.",
                "priority": "medium",
            }
        )
    if "PARTIAL_DELIVERY" in reason_codes:
        actions.append(
            {
                "title": "Close remaining quantity gap",
                "action": "Create a split order for undelivered quantity to avoid full-project blockage.",
                "priority": "high",
            }
        )
    if "STALE_DATA" in reason_codes:
        actions.append(
            {
                "title": "Refresh connector data",
                "action": "Run connector retry now and verify supplier endpoint freshness before final decisions.",
                "priority": "medium",
            }
        )

    if not actions:
        actions.append(
            {
                "title": "Confirm with supplier",
                "action": "Contact supplier dispatcher to confirm ETA and lock delivery window.",
                "priority": "low",
            }
        )
    return actions

