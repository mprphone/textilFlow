from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from ..models import ActualCostEntry, ProductionBatch, ProductionOrder, ProductionOrderVariant, QualityInspection, SalesOrder, SalesOrderLine, Shipment, ShipmentLine, StyleVariant


EPSILON = 0.001
SHIPPED_STATUSES = {"shipped", "invoiced"}
RESERVED_STATUSES = {"closed", "ready"}
OPEN_PACKING_STATUSES = {"draft", "planned", "preparing", "closed", "ready"}
VISIBLE_SHIPMENT_STATUSES = OPEN_PACKING_STATUSES | SHIPPED_STATUSES
APPROVED_QUALITY_RESULTS = {"passed", "conditional"}
FINAL_INSPECTION_TYPES = {"final", "revista"}


def _quantity(value) -> float:
    return round(float(value or 0), 2)


def approved_quantity(db: Session, order: ProductionOrder, variant_id: int | None = None) -> float:
    """Quantidade aprovada em controlos finais/revista, limitada ao produzido."""
    inspections = (
        db.query(QualityInspection)
        .filter_by(company_id=order.company_id, production_order_id=order.id)
        .filter(QualityInspection.inspection_type.in_(FINAL_INSPECTION_TYPES))
        .filter(QualityInspection.result.in_(APPROVED_QUALITY_RESULTS))
        .all()
    )
    if variant_id is not None:
        filtered = []
        for row in inspections:
            batch = db.get(ProductionBatch, row.batch_id) if row.batch_id else None
            inspected_variant = row.variant_id or (batch.variant_id if batch else None)
            if inspected_variant == variant_id:
                filtered.append(row)
        inspections = filtered
    approved = sum(max(0.0, _quantity(row.released_quantity) or (_quantity(row.inspected_quantity) - _quantity(row.defect_quantity))) for row in inspections)
    limit = _quantity(order.completed_quantity)
    if variant_id is not None:
        variant = db.query(ProductionOrderVariant).filter_by(production_order_id=order.id, variant_id=variant_id).first()
        limit = min(limit, _quantity(variant.quantity) if variant else limit)
    return min(limit, round(approved, 2))


def _has_scoped_quality(db: Session, order: ProductionOrder) -> bool:
    inspections = db.query(QualityInspection).filter_by(company_id=order.company_id, production_order_id=order.id).filter(
        QualityInspection.inspection_type.in_(FINAL_INSPECTION_TYPES),
        QualityInspection.result.in_(APPROVED_QUALITY_RESULTS),
    ).all()
    for row in inspections:
        if row.variant_id:
            return True
        if row.batch_id:
            batch = db.get(ProductionBatch, row.batch_id)
            if batch and batch.variant_id:
                return True
    return False


def _packed_for_variant(db: Session, order_id: int, variant_id: int) -> float:
    from ..models import ProductionMovement
    return round(sum(float(row.quantity or 0) for row in db.query(ProductionMovement).filter_by(
        production_order_id=order_id, movement_type="packing", variant_id=variant_id
    ).all()), 2)


def _packed_total(db: Session, order: ProductionOrder) -> float:
    """Saldo físico como fonte principal, com leitura legada até ao backfill."""
    from .execution import movement_holdings
    physical = float(movement_holdings(db, order)["packed"])
    legacy = float((order.custom_data or {}).get("packed_quantity") or 0)
    return round(max(physical, legacy), 2)


def _quantity_for_production_order(db: Session, production_order_id: int, statuses: set[str], *, variant_id=None, by_variant=False) -> float:
    query = (
        db.query(ShipmentLine)
        .join(Shipment, Shipment.id == ShipmentLine.shipment_id)
        .filter(ShipmentLine.production_order_id == production_order_id)
        .filter(Shipment.status.in_(statuses))
    )
    if by_variant:
        query = query.filter(ShipmentLine.variant_id == variant_id)
    rows = query.all()
    return round(sum(_quantity(row.quantity) for row in rows), 2)


def _shipped_for_production_order(db: Session, production_order_id: int, *, variant_id=None, by_variant=False) -> float:
    return _quantity_for_production_order(db, production_order_id, SHIPPED_STATUSES, variant_id=variant_id, by_variant=by_variant)


def _reserved_for_production_order(db: Session, production_order_id: int, *, variant_id=None, by_variant=False) -> float:
    return _quantity_for_production_order(db, production_order_id, RESERVED_STATUSES, variant_id=variant_id, by_variant=by_variant)


def _active_shipments(db: Session, sales_order_id: int) -> list[Shipment]:
    return (
        db.query(Shipment)
        .filter_by(sales_order_id=sales_order_id)
        .filter(Shipment.status.in_(VISIBLE_SHIPMENT_STATUSES))
        .order_by(Shipment.id.asc())
        .all()
    )


def dispatch_status(db: Session, sales_order) -> dict:
    """Saldo expedivel da encomenda, calculado por linha e por OF.

    Apenas conta pecas simultaneamente produzidas, aprovadas na qualidade e
    embaladas. O saldo expedido e acumulado em todas as expedicoes anteriores.
    """
    if not sales_order:
        return {"ready": False, "reason": "Encomenda nao encontrada", "missing": []}

    lines = (
        db.query(SalesOrderLine)
        .filter_by(company_id=sales_order.company_id, sales_order_id=sales_order.id)
        .order_by(SalesOrderLine.id.asc())
        .all()
    )
    shipments = _active_shipments(db, sales_order.id)
    ordered_quantity = round(sum(_quantity(line.quantity) for line in lines), 2)
    shipped_quantity = round(sum(_quantity(row.quantity) for row in shipments if row.status in SHIPPED_STATUSES), 2)
    reserved_quantity = round(sum(_quantity(row.quantity) for row in shipments if row.status in RESERVED_STATUSES), 2)
    remaining_quantity = max(0.0, round(ordered_quantity - shipped_quantity, 2))
    line_statuses = []
    allocations = []
    missing = []

    for line in lines:
        production_orders = (
            db.query(ProductionOrder)
            .filter_by(company_id=sales_order.company_id, sales_order_line_id=line.id)
            .order_by(ProductionOrder.id.asc())
            .all()
        )
        if not production_orders:
            missing.append(f"Linha {line.id}: sem OF associada")
        line_available = 0.0
        line_produced = 0.0
        line_approved = 0.0
        line_packed = 0.0
        line_shipped = 0.0
        line_reserved = 0.0
        for order in production_orders:
            produced = min(_quantity(order.quantity), _quantity(order.completed_quantity))
            approved = approved_quantity(db, order)
            packed = min(produced, _quantity(_packed_total(db, order)))
            shipped = _shipped_for_production_order(db, order.id)
            reserved = _reserved_for_production_order(db, order.id)
            available = max(0.0, round(min(produced, approved, packed) - shipped - reserved, 2))
            line_produced += produced
            line_approved += approved
            line_packed += packed
            line_shipped += shipped
            line_reserved += reserved
            variants = db.query(ProductionOrderVariant).filter_by(production_order_id=order.id).order_by(ProductionOrderVariant.id).all()
            if variants:
                order_available = available
                scoped_quality = _has_scoped_quality(db, order)
                scoped_packing = any(_packed_for_variant(db, order.id, variant.variant_id) > EPSILON for variant in variants)
                for variant in variants:
                    already_variant = _shipped_for_production_order(db, order.id, variant_id=variant.variant_id, by_variant=True)
                    reserved_variant = _reserved_for_production_order(db, order.id, variant_id=variant.variant_id, by_variant=True)
                    allocated_variant = already_variant + reserved_variant
                    variant_available = min(order_available, max(0.0, _quantity(variant.quantity) - allocated_variant))
                    if scoped_quality:
                        variant_available = min(variant_available, max(0.0, approved_quantity(db, order, variant.variant_id) - allocated_variant))
                    if scoped_packing:
                        variant_available = min(variant_available, max(0.0, _packed_for_variant(db, order.id, variant.variant_id) - allocated_variant))
                    if variant_available > EPSILON:
                        allocations.append({
                            "sales_order_line_id": line.id,
                            "production_order_id": order.id,
                            "production_order_no": order.order_no,
                            "variant_id": variant.variant_id,
                            "variant": _variant_label(db, variant.variant_id),
                            "available_quantity": variant_available,
                        })
                        line_available += variant_available
                        order_available = round(order_available - variant_available, 2)
            elif available > EPSILON:
                allocations.append({
                    "sales_order_line_id": line.id,
                    "production_order_id": order.id,
                    "production_order_no": order.order_no,
                    "variant_id": line.variant_id,
                    "variant": _variant_label(db, line.variant_id),
                    "available_quantity": available,
                })
                line_available += available
        line_statuses.append({
            "sales_order_line_id": line.id,
            "description": line.description,
            "ordered_quantity": _quantity(line.quantity),
            "produced_quantity": round(line_produced, 2),
            "approved_quantity": round(line_approved, 2),
            "packed_quantity": round(line_packed, 2),
            "shipped_quantity": round(line_shipped, 2),
            "reserved_quantity": round(line_reserved, 2),
            "available_quantity": round(line_available, 2),
        })

    available_quantity = min(remaining_quantity, round(sum(row["available_quantity"] for row in allocations), 2))
    if remaining_quantity <= EPSILON:
        reason = "Encomenda integralmente expedida"
    elif available_quantity > EPSILON:
        reason = f"{available_quantity:g} unidades disponiveis para expedicao"
    elif reserved_quantity > EPSILON:
        reason = f"{reserved_quantity:g} unidades reservadas em packing lists"
    else:
        details = []
        if sum(row["produced_quantity"] for row in line_statuses) <= shipped_quantity + EPSILON:
            details.append("sem nova producao concluida")
        if sum(row["approved_quantity"] for row in line_statuses) <= shipped_quantity + EPSILON:
            details.append("sem nova quantidade aprovada na qualidade")
        if sum(row["packed_quantity"] for row in line_statuses) <= shipped_quantity + EPSILON:
            details.append("sem nova quantidade embalada")
        reason = "; ".join(missing + details) or "Sem quantidade disponivel para expedicao"

    return {
        "ready": available_quantity > EPSILON,
        "reason": reason,
        "missing": missing,
        "ordered_quantity": ordered_quantity,
        "shipped_quantity": shipped_quantity,
        "reserved_quantity": reserved_quantity,
        "remaining_quantity": remaining_quantity,
        "available_quantity": round(available_quantity, 2),
        "shipment_count": len([row for row in shipments if row.status in SHIPPED_STATUSES]),
        "packing_list_count": len(shipments),
        "lines": line_statuses,
        "allocations": allocations,
    }


def next_packing_list_number(db: Session, company_id: int) -> str:
    year = date.today().year
    prefix = f"PL-{year}-"
    last = db.query(Shipment).filter(Shipment.company_id == company_id, Shipment.shipment_no.like(f"{prefix}%")).order_by(Shipment.id.desc()).first()
    sequence = 1
    if last:
        try:
            sequence = int(last.shipment_no.rsplit("-", 1)[-1]) + 1
        except (TypeError, ValueError):
            sequence = 1
    return f"{prefix}{sequence:05d}"


def _parse_datetime(value) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _requested_candidates(status: dict, payload: dict) -> tuple[list[dict], float]:
    requested_allocations = payload.get("allocations") or []
    candidates = status["allocations"]
    if requested_allocations:
        available_by_key = {
            (row["production_order_id"], row.get("variant_id")): row for row in candidates
        }
        candidates = []
        seen = set()
        for requested_row in requested_allocations:
            variant_id = int(requested_row.get("variant_id") or 0) or None
            key = (int(requested_row.get("production_order_id") or 0), variant_id)
            if key in seen:
                raise ValueError("A mesma variante foi indicada mais do que uma vez")
            seen.add(key)
            candidate = available_by_key.get(key)
            quantity = _quantity(requested_row.get("quantity"))
            if quantity <= EPSILON:
                continue
            if not candidate:
                raise ValueError("Uma das variantes selecionadas já não está disponível")
            if quantity > candidate["available_quantity"] + EPSILON:
                raise ValueError(f"A variante {candidate.get('variant') or candidate['production_order_no']} só tem {candidate['available_quantity']:g} unidades disponíveis")
            candidates.append({**candidate, "requested_quantity": quantity})
        requested = round(sum(row["requested_quantity"] for row in candidates), 2)
    else:
        requested = _quantity(payload.get("quantity")) or round(sum(row["available_quantity"] for row in candidates), 2)
    if requested <= EPSILON:
        raise ValueError("Indique uma quantidade valida")
    if requested > status["remaining_quantity"] + EPSILON:
        raise ValueError(f"Faltam expedir apenas {status['remaining_quantity']:g} unidades")
    if requested > status["available_quantity"] + EPSILON:
        raise ValueError(f"So existem {status['available_quantity']:g} unidades produzidas, aprovadas e embaladas")
    return candidates, requested


def _apply_packing_fields(shipment: Shipment, payload: dict) -> None:
    if "packing_mode" in payload:
        mode = str(payload.get("packing_mode") or "simple")
        if mode not in {"simple", "boxes"}:
            raise ValueError("Modo de embalagem inválido")
        shipment.packing_mode = mode
    if "package_count" in payload:
        shipment.package_count = max(0, int(payload.get("package_count") or 0))
    if "net_weight" in payload:
        shipment.net_weight = max(0, float(payload.get("net_weight") or 0))
    if "gross_weight" in payload:
        shipment.gross_weight = max(0, float(payload.get("gross_weight") or 0))
    if shipment.gross_weight and shipment.net_weight and shipment.gross_weight + EPSILON < shipment.net_weight:
        raise ValueError("O peso bruto não pode ser inferior ao peso líquido")
    if "packing_data" in payload:
        shipment.packing_data = dict(payload.get("packing_data") or {})
    if shipment.packing_mode == "boxes":
        boxes = list((shipment.packing_data or {}).get("boxes") or [])
        if boxes and shipment.package_count < len(boxes):
            shipment.package_count = len(boxes)
    for field in ("destination", "notes", "carrier", "tracking_no", "vehicle_plate"):
        if field in payload:
            setattr(shipment, field, payload.get(field) or None)


def _validate_packing_details(shipment: Shipment) -> None:
    if shipment.packing_mode != "boxes":
        return
    boxes = list((shipment.packing_data or {}).get("boxes") or [])
    if not boxes or len(boxes) != int(shipment.package_count or 0):
        raise ValueError("No detalhe por caixa, preencha todos os volumes")
    codes = [str(row.get("code") or "").strip() for row in boxes]
    if any(not code for code in codes) or len(set(codes)) != len(codes):
        raise ValueError("Cada caixa deve ter um código único")
    quantities = [_quantity(row.get("quantity")) for row in boxes]
    if any(value <= EPSILON for value in quantities):
        raise ValueError("Indique a quantidade de peças de cada caixa")
    total = round(sum(quantities), 2)
    if abs(total - _quantity(shipment.quantity)) > EPSILON:
        raise ValueError(f"As caixas somam {total:g} unidades, mas o packing list tem {shipment.quantity:g}")


def _replace_packing_lines(db: Session, shipment: Shipment, candidates: list[dict], requested: float) -> list[ShipmentLine]:
    for old in db.query(ShipmentLine).filter_by(shipment_id=shipment.id).all():
        db.delete(old)
    db.flush()
    remaining = requested
    rows = []
    for candidate in candidates:
        if remaining <= EPSILON:
            break
        take = min(remaining, candidate.get("requested_quantity", candidate["available_quantity"]))
        row = ShipmentLine(
            company_id=shipment.company_id, shipment_id=shipment.id,
            sales_order_line_id=candidate["sales_order_line_id"],
            production_order_id=candidate["production_order_id"],
            variant_id=candidate.get("variant_id"), quantity=round(take, 2),
        )
        db.add(row)
        rows.append(row)
        remaining = round(remaining - take, 2)
    if remaining > EPSILON:
        raise ValueError("Nao foi possivel alocar toda a quantidade as ordens de fabrico")
    shipment.quantity = requested
    db.flush()
    return rows


def create_packing_list(db: Session, sales_order, payload: dict) -> tuple[Shipment, list[ShipmentLine], dict]:
    status = dispatch_status(db, sales_order)
    candidates, requested = _requested_candidates(status, payload)

    shipment = Shipment(
        company_id=sales_order.company_id,
        sales_order_id=sales_order.id,
        shipment_no=str(payload.get("shipment_no") or next_packing_list_number(db, sales_order.company_id)).strip(),
        quantity=requested,
        status="preparing",
        documents=payload.get("documents") or [],
    )
    _apply_packing_fields(shipment, payload)
    db.add(shipment)
    db.flush()
    lines = _replace_packing_lines(db, shipment, candidates, requested)
    _validate_packing_details(shipment)
    return shipment, lines, dispatch_status(db, sales_order)


def update_packing_list(db: Session, shipment: Shipment, payload: dict) -> tuple[Shipment, list[ShipmentLine], dict]:
    if shipment.status not in {"draft", "planned", "preparing"}:
        raise ValueError("Um packing list fechado já não pode ser alterado")
    sales_order = db.get(SalesOrder, shipment.sales_order_id)
    status = dispatch_status(db, sales_order)
    candidates, requested = _requested_candidates(status, payload)
    _apply_packing_fields(shipment, payload)
    lines = _replace_packing_lines(db, shipment, candidates, requested)
    _validate_packing_details(shipment)
    shipment.status = "preparing"
    return shipment, lines, dispatch_status(db, sales_order)


def close_packing_list(db: Session, shipment: Shipment, user_id: int | None = None) -> tuple[Shipment, list[ShipmentLine], dict]:
    if shipment.status in RESERVED_STATUSES | SHIPPED_STATUSES:
        lines = db.query(ShipmentLine).filter_by(shipment_id=shipment.id).all()
        sales_order = db.get(SalesOrder, shipment.sales_order_id)
        return shipment, lines, dispatch_status(db, sales_order)
    if shipment.status not in {"draft", "planned", "preparing"}:
        raise ValueError("Este packing list não pode ser fechado")
    _validate_packing_details(shipment)
    sales_order = db.get(SalesOrder, shipment.sales_order_id)
    status = dispatch_status(db, sales_order)
    available = {(row["production_order_id"], row.get("variant_id")): row["available_quantity"] for row in status["allocations"]}
    lines = db.query(ShipmentLine).filter_by(shipment_id=shipment.id).order_by(ShipmentLine.id).all()
    if not lines:
        raise ValueError("O packing list não tem artigos")
    for line in lines:
        current = available.get((line.production_order_id, line.variant_id), 0)
        if float(line.quantity or 0) > current + EPSILON:
            raise ValueError(f"Só existem {current:g} unidades disponíveis para uma das linhas")
    from .operations_control import reserve_finished_goods
    for line in lines:
        reserve_finished_goods(db, shipment, line)
    shipment.status = "closed"
    shipment.closed_at = datetime.now(timezone.utc)
    db.flush()
    return shipment, lines, dispatch_status(db, sales_order)


def dispatch_packing_list(
    db: Session, shipment: Shipment, payload: dict, user_id: int | None = None,
    *, require_documents: bool = True,
) -> tuple[Shipment, list[ShipmentLine], dict]:
    if shipment.status in SHIPPED_STATUSES:
        raise ValueError("Este packing list já foi expedido")
    if shipment.status not in RESERVED_STATUSES:
        raise ValueError("Feche primeiro o packing list")
    has_delivery_note = any(isinstance(row, dict) and row.get("doc_type") == "sales_delivery" for row in (shipment.documents or []))
    if require_documents and not has_delivery_note:
        raise ValueError("Gere a guia de transporte antes de confirmar a saída")
    _apply_packing_fields(shipment, payload)
    if not shipment.carrier:
        raise ValueError("Indique o transportador")
    shipment.shipped_at = _parse_datetime(payload.get("shipped_at"))
    shipment.status = "shipped"
    sales_order = db.get(SalesOrder, shipment.sales_order_id)
    lines = db.query(ShipmentLine).filter_by(shipment_id=shipment.id).order_by(ShipmentLine.id).all()
    from .operations_control import consume_reserved_finished_goods
    for row in lines:
        consume_reserved_finished_goods(db, shipment, row, user_id)
    total_shipped = sum(_quantity(row.quantity) for row in _active_shipments(db, sales_order.id) if row.status in SHIPPED_STATUSES)
    ordered = sum(_quantity(row.quantity) for row in db.query(SalesOrderLine).filter_by(sales_order_id=sales_order.id).all())
    sales_order.status = "shipped" if total_shipped + EPSILON >= ordered else "partially_shipped"
    for row in lines:
        order = db.get(ProductionOrder, row.production_order_id)
        data = dict(order.custom_data or {})
        data["shipped_quantity"] = max(_quantity(data.get("shipped_quantity")), _shipped_for_production_order(db, order.id))
        order.custom_data = data
    transport_cost = round(float(payload.get("transport_cost") or 0), 4)
    if transport_cost > 0:
        for row in lines:
            share = round(transport_cost * float(row.quantity or 0) / max(float(shipment.quantity or 0), EPSILON), 4)
            db.add(ActualCostEntry(
                company_id=row.company_id, production_order_id=row.production_order_id,
                category="transport", description=f"Transporte {shipment.shipment_no}",
                quantity=row.quantity, unit="un", unit_cost=share / max(float(row.quantity or 0), EPSILON),
                amount=share, occurred_on=date.today(), reference=f"shipment:{shipment.id}", user_id=user_id,
            ))
    db.flush()
    return shipment, lines, dispatch_status(db, sales_order)


def cancel_packing_list(db: Session, shipment: Shipment) -> Shipment:
    if shipment.status in SHIPPED_STATUSES:
        raise ValueError("Uma expedição confirmada não pode ser cancelada por este ecrã")
    if shipment.status in RESERVED_STATUSES:
        from .operations_control import release_finished_goods_reservations
        release_finished_goods_reservations(db, shipment)
    shipment.status = "cancelled"
    db.flush()
    return shipment


def create_partial_shipment(db: Session, sales_order, payload: dict) -> tuple[Shipment, list[ShipmentLine], dict]:
    """Fluxo legado: cria, fecha e expede numa transação."""
    shipment, _, _ = create_packing_list(db, sales_order, payload)
    shipment, _, _ = close_packing_list(db, shipment, payload.get("user_id"))
    shipment, shipment_lines, status = dispatch_packing_list(
        db, shipment, payload, payload.get("user_id"), require_documents=False,
    )
    return shipment, shipment_lines, status


def _variant_label(db: Session, variant_id) -> str | None:
    if not variant_id:
        return None
    variant = db.get(StyleVariant, variant_id)
    if not variant:
        return None
    return " · ".join(value for value in (variant.color, variant.size) if value)
