from __future__ import annotations

from datetime import timedelta


SUPPORTED_SUPPLIERS = {
    "MetroLumber",
    "BuildPro",
    "ConcreteNow",
    "SteelHub",
    "RapidRoof",
}

ALERT_COOLDOWN = timedelta(hours=12)
STALE_DATA_THRESHOLD_HOURS = 48
HIGH_PRIORITY_IMPACT_DAYS = 7

DEFAULT_TENANT_ID = "demo-tenant"
DEFAULT_USER_ID = "demo-user"
DEFAULT_USER_ROLE = "owner"

