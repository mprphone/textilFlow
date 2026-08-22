from datetime import date, timedelta
import json
import re
import unicodedata

from ...models import (
    CapacityDay, CapacityEvent, Customer, Department, Employee, EmployeeSkill, Machine, MachineType, Operation, ProductOperation,
    ProcessJob, ProductionEvent, ProductionLine, ProductionOrder, SalesOrder, SalesOrderLine, SewingPlan, SkillType, Style,
    SubcontractService, Supplier, WorkAssignment, WorkShift, DowntimeEvent,
)
from ..confection_schedule import duration_days, end_from_start, monday_of, next_workday, order_hours



def _code(value: str, index: int) -> str:
    clean = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().upper()
    clean = re.sub(r"[^A-Z0-9]+", "-", clean).strip("-")
    return (clean or f"SKILL-{index}")[:80]


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def ensure_confection_data(db) -> int:
    """Completa a base operacional sem substituir dados introduzidos pelo utilizador."""

    created = 0
    company_ids = [row[0] for row in db.query(ProductionLine.company_id).distinct().all()]
    for company_id in company_ids:
        shift = db.query(WorkShift).filter_by(company_id=company_id, code="T1").first()
        if not shift:
            shift = WorkShift(
                company_id=company_id, code="T1", name="Turno normal",
                start_time="08:00", end_time="17:00", minutes_day=480, break_minutes=30,
            )
            db.add(shift)
            db.flush()
            created += 1

        created += _ensure_catalogs(db, company_id)
        created += keep_two_sewing_lines(db, company_id)

        if not db.query(EmployeeSkill).filter_by(company_id=company_id).first():
            for employee in db.query(Employee).filter_by(company_id=company_id).all():
                for index, skill in enumerate(employee.skills or [], start=1):
                    db.add(EmployeeSkill(
                        company_id=company_id, employee_id=employee.id,
                        skill_code=_code(str(skill), index), skill_name=str(skill),
                        proficiency_level=3, efficiency_pct=85, active=True,
                    ))
                    created += 1

        for order in db.query(ProductionOrder).filter(
            ProductionOrder.company_id == company_id,
            ProductionOrder.status.notin_(["completed", "cancelled"]),
        ).all():
            if db.query(SewingPlan).filter_by(company_id=company_id, production_order_id=order.id).first():
                continue
            sam = sum(row.smv or 0 for row in db.query(ProductOperation).filter_by(style_id=order.style_id).all())
            efficiency = 85
            line = db.get(ProductionLine, order.line_id) if order.line_id else None
            if line:
                efficiency = line.target_efficiency or efficiency
            remaining = max(0, (order.quantity or 0) - (order.completed_quantity or 0))
            start_date = max(date.today(), order.planned_start or date.today())
            end_date = max(start_date, order.planned_end or start_date + timedelta(days=10))
            db.add(SewingPlan(
                company_id=company_id, code=f"PLAN-{order.order_no}", production_order_id=order.id,
                style_id=order.style_id, line_id=order.line_id, source_type="confirmed",
                allocation_type="internal", start_date=start_date, end_date=end_date,
                quantity=remaining, sam_minutes=sam, efficiency_pct=efficiency,
                required_minutes=round(remaining * sam / (efficiency / 100), 2) if efficiency else 0,
                probability_pct=100, priority=order.priority, status="in_progress" if order.status == "in_progress" else "planned",
            ))
            created += 1

        for supplier in db.query(Supplier).filter(
            Supplier.company_id == company_id,
            Supplier.supplier_type == "sewing",
        ).all():
            if not supplier.weekly_capacity:
                supplier.weekly_capacity = 12000
                created += 1
            if not supplier.piece_cost:
                service = db.query(SubcontractService).filter_by(
                    company_id=company_id, supplier_id=supplier.id, category="sewing", active=True
                ).first()
                supplier.piece_cost = service.unit_cost if service else 1.2
        created += _ensure_map_book(db, company_id)
    return created


def _ensure_catalogs(db, company_id: int) -> int:
    created = 0
    skills = [
        ("EST", "Estender"), ("CORTE", "Corte"), ("PP", "Ponto preso"), ("CC", "Corta-e-cose"),
        ("REC", "Recobrimento"), ("GOLA", "Gola"), ("BAINHA", "Bainha"),
    ]
    for code, name in skills:
        if not db.query(SkillType).filter_by(company_id=company_id, code=code).first():
            db.add(SkillType(company_id=company_id, code=code, name=name, active=True))
            created += 1
    for employee in db.query(Employee).filter_by(company_id=company_id).all():
        for skill in employee.skills or []:
            name = str(skill).strip()
            if not name:
                continue
            code = _code(name, 1)[:40]
            if not db.query(SkillType).filter_by(company_id=company_id, code=code).first() and not db.query(SkillType).filter_by(company_id=company_id, name=name).first():
                db.add(SkillType(company_id=company_id, code=code, name=name, active=True))
                created += 1
    machines = [
        ("spreader", "Mesa de estender"), ("cutter", "Corte"), ("lockstitch", "Ponto preso"),
        ("overlock", "Corta-e-cose"), ("coverstitch", "Recobrimento"),
    ]
    for code, name in machines:
        if not db.query(MachineType).filter_by(company_id=company_id, code=code).first():
            db.add(MachineType(company_id=company_id, code=code, name=name, active=True))
            created += 1
    for machine in db.query(Machine).filter_by(company_id=company_id).all():
        code = (machine.machine_type or "").strip()
        if not code:
            continue
        if not db.query(MachineType).filter_by(company_id=company_id, code=code).first():
            db.add(MachineType(company_id=company_id, code=code, name=code, active=True))
            created += 1
    db.flush()
    return created


DEMO_EXTRA_LINE_CODES = {"LA", "LB", "LC", "A", "B", "C"}


def keep_two_sewing_lines(db, company_id: int) -> int:
    """Remove as linhas de demo A/B/C. Não apaga linhas que o utilizador criar a seguir."""
    conf = db.query(Department).filter_by(company_id=company_id, code="CONF").first()
    if not conf:
        return 0
    changed = 0
    rows = db.query(ProductionLine).filter_by(company_id=company_id, department_id=conf.id).order_by(ProductionLine.id).all()
    keep = [row for row in rows if row.code not in DEMO_EXTRA_LINE_CODES]
    for code in ("L1", "L2"):
        if not any(row.code == code for row in keep):
            found = next((row for row in rows if row.code == code), None)
            if found and found not in keep:
                keep.append(found)
    while len(keep) < 2:
        index = len(keep) + 1
        code = f"L{index}"
        if any(row.code == code for row in keep):
            index += 1
            continue
        line = ProductionLine(
            company_id=company_id, department_id=conf.id, code=code,
            name=f"Linha {index}", production_mode="line",
            capacity_minutes_day=3840, target_pcs_hour=80, target_efficiency=85, active=True,
        )
        db.add(line)
        db.flush()
        keep.append(line)
        changed += 1
    named = [row for row in keep if row.code in {"L1", "L2"}]
    named.sort(key=lambda row: row.code)
    for index, line in enumerate(named, start=1):
        if line.name != f"Linha {index}":
            changed += 1
        line.name = f"Linha {index}"
        line.active = True
        line.production_mode = "line"
        if not line.capacity_minutes_day:
            line.capacity_minutes_day = 3840
    extra_ids = [row.id for row in rows if row.code in DEMO_EXTRA_LINE_CODES]
    if not extra_ids:
        db.flush()
        return changed
    target_l1 = next((row for row in keep if row.code == "L1"), keep[0])
    target_l2 = next((row for row in keep if row.code == "L2"), keep[-1])
    remap = {}
    for extra in rows:
        if extra.id not in extra_ids:
            continue
        remap[extra.id] = target_l1.id if extra.code in {"LA", "A", "L1"} else target_l2.id
    db.query(CapacityDay).filter(
        CapacityDay.company_id == company_id,
        CapacityDay.line_id.in_(extra_ids),
    ).delete(synchronize_session=False)
    _remap_line_ids(db, company_id, remap)
    db.flush()
    db.query(ProductionLine).filter(ProductionLine.id.in_(extra_ids)).delete(synchronize_session=False)
    db.flush()
    return changed + len(extra_ids)


def _remap_line_ids(db, company_id: int, remap: dict[int, int]) -> None:
    models = (Employee, Machine, SewingPlan, ProductionOrder, CapacityEvent, WorkAssignment, ProductionEvent, ProcessJob, DowntimeEvent)
    for model in models:
        for row in db.query(model).filter(model.company_id == company_id, model.line_id.in_(remap.keys())).all():
            row.line_id = remap[row.line_id]
    for plan in db.query(SewingPlan).filter(SewingPlan.company_id == company_id).all():
        try:
            meta = json.loads(plan.notes or "")
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        key = meta.get("line_key")
        if key in {"A", "LA"}:
            meta["line_key"] = "L1"
        elif key in {"B", "C", "LB", "LC"}:
            meta["line_key"] = "L2"
        plan.notes = json.dumps(meta, ensure_ascii=False)


def _ensure_map_book(db, company_id: int) -> int:
    created = 0
    conf = db.query(Department).filter_by(company_id=company_id, code="CONF").first()
    if not conf:
        return 0
    zara = db.query(Customer).filter_by(company_id=company_id, code="ZARA").first()
    if zara and zara.name == "Zara":
        zara.name = "ZARA PORTUGAL"
    if not zara:
        return created
    mango = db.query(Customer).filter_by(company_id=company_id, code="MANGO").first()
    md = db.query(Customer).filter_by(company_id=company_id, code="MD").first()
    customers = {
        "ZARA PORTUGAL": zara,
        "Mango": mango or zara,
        "Massimo Dutti": md or zara,
    }
    line1 = db.query(ProductionLine).filter_by(company_id=company_id, department_id=conf.id, code="L1").first()
    line2 = db.query(ProductionLine).filter_by(company_id=company_id, department_id=conf.id, code="L2").first()
    sewing = db.query(ProductionLine).filter_by(company_id=company_id, department_id=conf.id, active=True).order_by(ProductionLine.id).all()
    if not line1 and sewing:
        line1 = sewing[0]
    if not line2 and len(sewing) > 1:
        line2 = sewing[1]
    lines = {"A": line1, "B": line2}

    shift = db.query(WorkShift).filter_by(company_id=company_id, code="T1").first()

    styles = {}
    for reference, description in [
        ("TSHIRT-BASIC", "T-Shirt Basic Plus"),
        ("POLO-PIQUE", "Polo Pique"),
        ("CAMISA-TWILL", "Camisa Twill"),
        ("CASACO-SARJA", "Casaco Sarja"),
        ("SWEAT-HOOD", "Sweat Hoodie"),
    ]:
        style = db.query(Style).filter_by(company_id=company_id, reference=reference).first()
        if not style:
            style = Style(
                company_id=company_id, customer_id=zara.id if zara else None,
                reference=reference, description=description, collection="SS26",
                lifecycle_status="approved", approved=True,
            )
            db.add(style)
            db.flush()
            created += 1
        styles[reference] = style

    if db.query(ProductionOrder).filter_by(company_id=company_id, order_no="OP-2026-0886").first():
        return created

    today = date.today()
    origin = monday_of(today)

    scheduled = [
        ("OP-2026-0886", "ZARA PORTUGAL", "TSHIRT-BASIC", "A", 1200, 14.5, today, False, "in_progress"),
        ("OP-2026-0885", "ZARA PORTUGAL", "SWEAT-HOOD", "A", 1600, 14.5, origin + timedelta(days=7), False, "planned"),
        ("OP-2026-0888", "Mango", "TSHIRT-BASIC", "A", 900, 14.5, origin + timedelta(days=7), False, "planned"),
        ("OP-2026-0871", "Massimo Dutti", "POLO-PIQUE", "B", 1800, 22, origin, False, "planned"),
        ("OP-2026-0874", "ZARA PORTUGAL", "CAMISA-TWILL", "B", 700, 28, origin + timedelta(days=7), False, "planned"),
        ("OP-2026-0862", "Mango", "CASACO-SARJA", "B", 420, 45, origin, False, "planned"),
        ("OP-2026-0868", "Massimo Dutti", "CASACO-SARJA", "B", 380, 45, origin + timedelta(days=7), False, "planned"),
        ("OP-2026-0894", "ZARA PORTUGAL", "TSHIRT-BASIC", "A", 2000, 14.5, origin + timedelta(days=14), False, "planned"),
    ]
    backlog = [
        ("OP-2026-0891", "ZARA PORTUGAL", "TSHIRT-BASIC", 2000, 14.5),
        ("OP-2026-0892", "Mango", "POLO-PIQUE", 1500, 22),
        ("OP-2026-0893", "Massimo Dutti", "CASACO-SARJA", 800, 45),
        ("OP-2026-0895", "ZARA PORTUGAL", "SWEAT-HOOD", 1200, 14.5),
        ("OP-2026-0896", "Mango", "CAMISA-TWILL", 900, 28),
        ("OP-2026-0897", "ZARA PORTUGAL", "POLO-PIQUE", 600, 22),
        ("OP-2026-0898", "Massimo Dutti", "CASACO-SARJA", 400, 45),
        ("OP-2026-0899", "Mango", "TSHIRT-BASIC", 1800, 14.5),
    ]

    def _make(order_no, client_name, style_ref, line_key, qty, sam, start, urgent, status):
        nonlocal created
        customer = customers.get(client_name) or zara
        style = styles[style_ref]
        hours = order_hours(qty, sam)
        duration = duration_days(hours)
        start_day = next_workday(start) if status != "backlog" else today
        end, _ = end_from_start(start_day, duration, 0, origin)
        promised = end + timedelta(days=7)
        sales = SalesOrder(
            company_id=company_id, customer_id=(customer or zara).id, order_no=f"EC-{order_no}",
            order_date=today - timedelta(days=10), delivery_date=promised, status="confirmed",
        )
        db.add(sales)
        db.flush()
        sales_line = SalesOrderLine(
            company_id=company_id, sales_order_id=sales.id, style_id=style.id,
            description=style.description, quantity=qty, unit_price=12.2, delivery_date=promised,
        )
        db.add(sales_line)
        db.flush()
        line = lines.get(line_key) if status != "backlog" else None
        order = ProductionOrder(
            company_id=company_id, sales_order_line_id=sales_line.id, style_id=style.id,
            line_id=line.id if line else None, order_no=order_no, quantity=qty,
            planned_start=None if status == "backlog" else start_day,
            planned_end=promised, status="in_progress" if status == "in_progress" else "planned",
            priority=1 if urgent else 3, current_stage="backlog" if status == "backlog" else "confeção",
            custom_data={"pmap": True, "client": client_name, "article": style.description},
        )
        db.add(order)
        db.flush()
        plan = SewingPlan(
            company_id=company_id, code=f"PLAN-{order_no}", production_order_id=order.id, style_id=style.id,
            line_id=line.id if line else None, source_type="confirmed", allocation_type="internal",
            start_date=start_day, end_date=end, quantity=qty, sam_minutes=sam, efficiency_pct=100,
            required_minutes=round(hours * 60, 2), probability_pct=100, priority=order.priority, status=status,
            notes=json.dumps({"pmap": True, "client": client_name, "article": style.description, "sf": 0, "line_key": line_key or "A", "urgent": urgent}, ensure_ascii=False),
        )
        db.add(plan)
        created += 1

    for row in scheduled:
        _make(*row)
    for order_no, client_name, style_ref, qty, sam in backlog:
        _make(order_no, client_name, style_ref, "A", qty, sam, today, False, "backlog")
    return created
