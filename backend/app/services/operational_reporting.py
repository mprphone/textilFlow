from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..models import (
    CustomerClaim, FinishedGoodsUnit, ProductionMovement, ProductionOrder,
    QualityInspection, SalesOrder, SalesOrderLine, Shipment, SubcontractJob,
)
from .cost_control import actual_order_cost


def _pct(numerator: float, denominator: float) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0


def operations_scorecard(db: Session, company_id: int) -> dict:
    today = date.today()
    sales = db.query(SalesOrder).filter_by(company_id=company_id).all()
    shipments = db.query(Shipment).filter_by(company_id=company_id, status="shipped").all()
    shipments_by_order = defaultdict(list)
    for row in shipments:
        shipments_by_order[row.sales_order_id].append(row)
    fulfilments = []
    for order in sales:
        rows = shipments_by_order[order.id]
        ordered = sum(float(line.quantity or 0) for line in db.query(SalesOrderLine).filter_by(sales_order_id=order.id).all())
        shipped = sum(float(row.quantity or 0) for row in rows)
        if ordered <= 0 or shipped + 0.001 < ordered:
            continue
        last_date = max((row.shipped_at.date() for row in rows if row.shipped_at), default=None)
        if order.delivery_date and last_date:
            fulfilments.append(last_date <= order.delivery_date)

    production = db.query(ProductionOrder).filter_by(company_id=company_id).all()
    completed = [row for row in production if row.actual_start and row.actual_end]
    lead_days = [
        max(0.0, (row.actual_end - row.actual_start).total_seconds() / 86400)
        for row in completed
    ]
    active = [row for row in production if row.status not in {"completed", "cancelled"}]
    wip_ages = []
    for row in active:
        start = row.actual_start or row.created_at
        if start:
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            wip_ages.append(max(0, (datetime.now(timezone.utc) - start).days))

    inspections = db.query(QualityInspection).filter_by(company_id=company_id).filter(
        QualityInspection.inspection_type.in_(["final", "revista"])
    ).order_by(QualityInspection.created_at, QualityInspection.id).all()
    first_inspections = []
    seen_scopes = set()
    for row in inspections:
        if row.result == "pending":
            continue
        scope = (row.production_order_id, row.batch_id, row.variant_id)
        if scope in seen_scopes:
            continue
        seen_scopes.add(scope)
        first_inspections.append(row)
    inspected = sum(float(row.inspected_quantity or 0) for row in first_inspections)
    defects = sum(float(row.defect_quantity or 0) for row in first_inspections)
    first_pass = max(0.0, inspected - defects)
    movements = db.query(ProductionMovement).filter_by(company_id=company_id).all()
    scrap = sum(float(row.quantity or 0) for row in movements if row.movement_type == "scrap")
    rework = sum(float(row.quantity or 0) for row in movements if row.movement_type == "rework_start")

    supplier_jobs = db.query(SubcontractJob).filter_by(company_id=company_id).filter(
        SubcontractJob.status == "received"
    ).all()
    dated_supplier_jobs = [row for row in supplier_jobs if row.received_date and row.expected_date]
    on_time_supplier = sum(
        bool(row.received_date and row.expected_date and row.received_date <= row.expected_date)
        for row in dated_supplier_jobs
    )
    accepted_supplier = sum(float(row.accepted_quantity or 0) for row in supplier_jobs)
    received_supplier = accepted_supplier + sum(float(row.rejected_quantity or 0) for row in supplier_jobs)

    revenue = actual = 0.0
    valued_sales_lines = set()
    for order in production:
        line = db.get(SalesOrderLine, order.sales_order_line_id) if order.sales_order_line_id else None
        if line and line.id not in valued_sales_lines:
            revenue += float(line.unit_price or 0) * float(line.quantity or 0)
            valued_sales_lines.add(line.id)
        actual += sum(actual_order_cost(db, order)["totals"].values())
    claims = db.query(CustomerClaim).filter_by(company_id=company_id).all()
    finished = db.query(FinishedGoodsUnit).filter_by(company_id=company_id).filter(
        FinishedGoodsUnit.status == "available"
    ).all()

    trend = defaultdict(lambda: {"produced": 0.0, "shipped": 0.0, "rejected": 0.0})
    for row in movements:
        if row.movement_type == "operation_output" and row.occurred_at:
            trend[row.occurred_at.strftime("%Y-%m")]["produced"] += max(0.0, float(row.quantity or 0))
    for row in shipments:
        if row.shipped_at:
            trend[row.shipped_at.strftime("%Y-%m")]["shipped"] += float(row.quantity or 0)
    for row in inspections:
        marker = row.created_at
        if marker:
            trend[marker.strftime("%Y-%m")]["rejected"] += float(row.defect_quantity or 0)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period_label": f"Acumulado até {today.isoformat()}",
        "kpis": {
            "otif_pct": _pct(sum(fulfilments), len(fulfilments)),
            "orders_fulfilled": len(fulfilments),
            "production_lead_days": round(sum(lead_days) / len(lead_days), 1) if lead_days else 0,
            "wip_orders": len(active),
            "wip_age_days": round(sum(wip_ages) / len(wip_ages), 1) if wip_ages else 0,
            "first_pass_yield_pct": _pct(first_pass, inspected),
            "rework_quantity": round(rework, 2),
            "scrap_quantity": round(scrap, 2),
            "supplier_otd_pct": _pct(on_time_supplier, len(dated_supplier_jobs)),
            "supplier_acceptance_pct": _pct(accepted_supplier, received_supplier),
            "revenue": round(revenue, 2),
            "actual_cost": round(actual, 2),
            "actual_margin": round(revenue - actual, 2),
            "claim_count": len(claims),
            "open_claim_count": sum(row.status != "closed" for row in claims),
            "finished_goods_quantity": round(sum(float(row.quantity or 0) for row in finished), 2),
        },
        "trend": [{"period": key, **{name: round(value, 2) for name, value in values.items()}} for key, values in sorted(trend.items())[-12:]],
    }
