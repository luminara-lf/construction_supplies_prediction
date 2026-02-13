from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import random


SUPPORTED_SUPPLIERS = [
    "MetroLumber",
    "BayDrywall",
    "PacificConcrete",
    "GoldenStateSteel",
    "NorCalElectrical",
]


@dataclass(frozen=True)
class SupplierInventoryRow:
    supplier_sku: str
    qty_available: float
    captured_at: datetime


@dataclass(frozen=True)
class SupplierOrderRow:
    project_id: str
    supplier_order_id: str
    supplier_sku: str
    material_name: str
    qty_ordered: float
    qty_delivered: float
    eta_date: date
    historical_late_rate: float
    eta_volatility: float
    lead_time_trend_days: float
    source_updated_at: datetime


@dataclass(frozen=True)
class SupplierSyncPayload:
    inventory: list[SupplierInventoryRow]
    orders: list[SupplierOrderRow]


def supplier_supported(name: str) -> bool:
    return name in SUPPORTED_SUPPLIERS


def _sku_catalog() -> list[tuple[str, str]]:
    return [
        ("DRYWALL_58", "Drywall Sheet 5/8"),
        ("LBR_2X4_8", "Stud Lumber 2x4x8"),
        ("PLYWOOD_34", "Plywood 3/4"),
        ("STEEL_BEAM_I", "I-Beam Structural Steel"),
        ("ELEC_PANEL_200A", "Electrical Panel 200A"),
        ("CONC_READY_4K", "Ready Mix Concrete 4K PSI"),
    ]


def generate_supplier_payload(supplier_name: str, connector_id: str) -> SupplierSyncPayload:
    now = datetime.now(timezone.utc)
    seed = f"{supplier_name}:{connector_id}:{now.date().isoformat()}"
    rng = random.Random(seed)

    inventory: list[SupplierInventoryRow] = []
    orders: list[SupplierOrderRow] = []
    project_ids = ["P-1001", "P-1002", "P-1015", "P-1099"]

    for idx, (sku, material_name) in enumerate(_sku_catalog(), start=1):
        qty_ordered = float(rng.randint(30, 180))
        qty_delivered = float(rng.randint(0, int(qty_ordered * 0.65)))
        qty_available = float(rng.randint(0, 220))
        eta_days = rng.randint(-2, 18)

        inventory.append(
            SupplierInventoryRow(
                supplier_sku=sku,
                qty_available=qty_available,
                captured_at=now,
            )
        )

        orders.append(
            SupplierOrderRow(
                project_id=rng.choice(project_ids),
                supplier_order_id=f"{supplier_name[:3].upper()}-SO-{idx}",
                supplier_sku=sku,
                material_name=material_name,
                qty_ordered=qty_ordered,
                qty_delivered=qty_delivered,
                eta_date=(now + timedelta(days=eta_days)).date(),
                historical_late_rate=round(rng.uniform(0.05, 0.8), 2),
                eta_volatility=round(rng.uniform(0.0, 1.0), 2),
                lead_time_trend_days=round(rng.uniform(-2.0, 12.0), 2),
                source_updated_at=now - timedelta(hours=rng.randint(0, 72)),
            )
        )

    return SupplierSyncPayload(inventory=inventory, orders=orders)
