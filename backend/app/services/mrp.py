"""Necessidades de material da semana (MRP): planos de confeção + BOM vs stock."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models import Company, Material, ProductionOrder, SewingPlan, Style
from .order_followup import bom_material_needs
from .primavera import fetch_stock


def week_monday(day: date | None = None) -> date:
    day = day or date.today()
    return day - timedelta(days=day.weekday())


def week_material_plan(db: Session, company_id: int, start: date | None = None, *, pull_primavera: bool = True) -> dict:
    start = week_monday(start)
    end = start + timedelta(days=6)
    plans = (
        db.query(SewingPlan)
        .filter(
            SewingPlan.company_id == company_id,
            SewingPlan.status.notin_(["cancelled", "done", "completed"]),
            SewingPlan.start_date <= end,
            SewingPlan.end_date >= start,
        )
        .all()
    )
    qty_by_order: dict[int, float] = defaultdict(float)
    for plan in plans:
        if plan.production_order_id:
            qty_by_order[plan.production_order_id] += float(plan.quantity or 0)

    if not qty_by_order:
        orders = (
            db.query(ProductionOrder)
            .filter(
                ProductionOrder.company_id == company_id,
                ProductionOrder.status.notin_(["cancelled", "completed", "shipped"]),
            )
            .all()
        )
        for order in orders:
            planned = order.planned_start or order.planned_end
            if planned is None or start <= planned <= end:
                qty_by_order[order.id] = float(order.quantity or 0)

    buckets: dict[int, dict] = {}
    order_refs = []
    for order_id, planned_qty in qty_by_order.items():
        order = db.get(ProductionOrder, order_id)
        if not order or order.company_id != company_id:
            continue
        order_qty = float(order.quantity or 0) or planned_qty or 1
        factor = planned_qty / order_qty if order_qty else 1
        style = db.get(Style, order.style_id) if order.style_id else None
        order_refs.append({
            "order_id": order.id,
            "order_no": order.order_no,
            "quantity": round(planned_qty, 2),
            "style": style.reference if style else None,
        })
        for row in bom_material_needs(db, order):
            mid = row.get("material_id")
            if not mid:
                continue
            bucket = buckets.setdefault(mid, {
                "material_id": mid,
                "description": row["description"],
                "unit": row["unit"],
                "required": 0.0,
                "available_local": float(row["available_quantity"] or 0),
                "orders": [],
            })
            need = float(row["required_quantity"] or 0) * factor
            bucket["required"] += need
            bucket["orders"].append({"order_no": order.order_no, "required": round(need, 4)})

    material_ids = list(buckets.keys())
    materials = {
        row.id: row for row in db.query(Material).filter(Material.id.in_(material_ids)).all()
    } if material_ids else {}

    primavera = {"ok": False, "error": None, "count": 0, "items": []}
    primavera_by_code: dict[str, float] = {}
    if pull_primavera:
        company = db.get(Company, company_id)
        try:
            primavera = fetch_stock(company) if company else {"ok": False, "error": "Empresa não encontrada", "count": 0, "items": []}
            for item in primavera.get("items") or []:
                key = str(item.get("item") or "").strip().upper()
                if key:
                    primavera_by_code[key] = primavera_by_code.get(key, 0) + float(item.get("available") or 0)
        except Exception as error:
            primavera = {"ok": False, "error": str(error), "count": 0, "items": []}

    items = []
    for mid, bucket in buckets.items():
        material = materials.get(mid)
        code = (material.code if material else "") or ""
        pri = primavera_by_code.get(code.upper()) if code else None
        available_local = float(bucket["available_local"] or 0)
        if primavera.get("ok") and pri is not None:
            available = pri
        else:
            available = available_local
        shortage = max(0.0, bucket["required"] - available)
        items.append({
            "material_id": mid,
            "code": code,
            "description": bucket["description"],
            "unit": bucket["unit"],
            "supplier_id": material.supplier_id if material else None,
            "required": round(bucket["required"], 4),
            "available_local": round(available_local, 4),
            "primavera_available": round(pri, 4) if pri is not None else None,
            "available": round(available, 4),
            "shortage": round(shortage, 4),
            "status": "shortage" if shortage > 0.001 else "ok",
            "orders": bucket["orders"],
        })
    items.sort(key=lambda row: (0 if row["status"] == "shortage" else 1, row["code"] or ""))
    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "plan_count": len(plans),
        "order_count": len(order_refs),
        "orders": order_refs,
        "items": items,
        "shortage_count": sum(1 for row in items if row["status"] == "shortage"),
        "primavera": {
            "ok": bool(primavera.get("ok")),
            "error": primavera.get("error"),
            "count": primavera.get("count") or 0,
            "path": primavera.get("path"),
            "items": primavera.get("items") or [],
        },
    }
