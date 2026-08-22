from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from math import ceil

POSTS_PER_LINE = 10
PLANT_POSTS = 30
NOMINAL_HOURS_PERSON = 8
EXTRA_HOURS_PERSON = 2
LINE_HOURS_DAY = 80
LINE_HOURS_DAY_EXTRA = 100
PLANT_HOURS_DAY = 240
PLANT_HOURS_DAY_EXTRA = 300
PLANT_HOURS_WEEK = 1200
PLANT_HOURS_WEEK_EXTRA = 1500
OVERTIME_PREMIUM_EUR = 6.6
FACCAO_SHARE = 0.22
HORIZON_WEEKS = 6
MAX_PARALLEL_ORDERS_PER_LINE = 2

LINE_CATALOG = (
    {
        "key": "A", "code": "LA", "name": "Linha A", "family": "Malhas & T-Shirts",
        "posts": "1–10", "pcs_hour": 160, "color": "green",
        "keywords": ("t-shirt", "tshirt", "malha", "sweat", "jersey", "hoodie"),
    },
    {
        "key": "B", "code": "LB", "name": "Linha B", "family": "Camisaria & Polos",
        "posts": "11–20", "pcs_hour": 75, "color": "blue",
        "keywords": ("polo", "camisa", "camisaria", "twill", "oxford"),
    },
    {
        "key": "C", "code": "LC", "name": "Linha C", "family": "Casacos & Sarjas",
        "posts": "21–30", "pcs_hour": 35, "color": "pink",
        "keywords": ("casaco", "sarja", "jacket", "park", "blazer", "gabardine"),
    },
)


def order_hours(quantity: float, sam_minutes: float) -> float:
    return round((quantity or 0) * (sam_minutes or 0) / 60.0, 6)


def duration_days(hours: float, line_hours_per_day: float = LINE_HOURS_DAY) -> float:
    if line_hours_per_day <= 0:
        return 0.0
    return hours / line_hours_per_day


def display_duration(days: float) -> float:
    return round(days, 1)


def occupancy_tone(pct: float) -> str:
    if pct > 100:
        return "red"
    if pct >= 80:
        return "yellow"
    return "green"


def line_hours_per_day(extra_hours: bool) -> float:
    return LINE_HOURS_DAY_EXTRA if extra_hours else LINE_HOURS_DAY


def plant_hours_per_day(extra_hours: bool) -> float:
    return PLANT_HOURS_DAY_EXTRA if extra_hours else PLANT_HOURS_DAY


def plant_hours_per_week(extra_hours: bool) -> float:
    return PLANT_HOURS_WEEK_EXTRA if extra_hours else PLANT_HOURS_WEEK


def is_workday(day: date) -> bool:
    return day.weekday() < 5


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def iso_week(day: date) -> int:
    return day.isocalendar()[1]


def next_workday(day: date) -> date:
    current = day
    while not is_workday(current):
        current += timedelta(days=1)
    return current


def add_workdays(start: date, days: int) -> date:
    current = next_workday(start)
    step = 0
    while step < days:
        current += timedelta(days=1)
        if is_workday(current):
            step += 1
    return current


def workdays_between(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        if is_workday(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def horizon_workdays(today: date, weeks: int = HORIZON_WEEKS) -> list[date]:
    start = monday_of(today)
    end = start + timedelta(weeks=weeks, days=-3)
    return workdays_between(start, end)


def offset_of(origin: date, day: date, fraction: float = 0.0) -> float:
    origin = monday_of(origin)
    count = 0
    current = origin
    target = next_workday(day)
    while current < target:
        if is_workday(current):
            count += 1
        current += timedelta(days=1)
    return count + max(0.0, min(0.999, fraction))


def date_from_offset(origin: date, offset: float, as_end: bool = False) -> tuple[date, float]:
    origin = monday_of(origin)
    value = max(0.0, offset)
    if as_end:
        if value <= 0:
            return next_workday(origin), 0.0
        whole = int(value) if value % 1 else int(value) - 1
        fraction = value - whole if value % 1 else 1.0
    else:
        whole = int(value)
        fraction = round(value - whole, 6)
    current = origin
    seen = 0
    while True:
        if is_workday(current):
            if seen == whole:
                return current, fraction
            seen += 1
        current += timedelta(days=1)


def end_from_start(start: date, duration: float, start_fraction: float = 0.0, origin: date | None = None) -> tuple[date, float]:
    origin = monday_of(origin or start)
    start_offset = offset_of(origin, start, start_fraction)
    return date_from_offset(origin, start_offset + max(0.0, duration), as_end=True)


def preferred_line_key(article: str) -> str:
    text = (article or "").lower()
    for line in LINE_CATALOG:
        if any(word in text for word in line["keywords"]):
            return line["key"]
    return "A"


def _block_payload(item: dict, extra_hours: bool, origin: date) -> dict:
    hours = order_hours(item.get("quantity") or 0, item.get("sam_minutes") or 0)
    hours_day = line_hours_per_day(extra_hours)
    duration = duration_days(hours, hours_day)
    start = next_workday(item["start_date"]) if item.get("start_date") else None
    fraction = float(item.get("start_fraction") or 0)
    start_offset = offset_of(origin, start, fraction) if start else None
    end_date, end_fraction = end_from_start(start, duration, fraction, origin) if start else (None, 0)
    end_offset = (start_offset + duration) if start_offset is not None else None
    promised = item.get("promised_date")
    return {
        **item,
        "hours": hours,
        "duration_days": duration,
        "duration_display": display_duration(duration),
        "line_hours_day": hours_day,
        "start_date": start.isoformat() if start else None,
        "start_fraction": fraction,
        "start_offset": start_offset,
        "end_date": end_date.isoformat() if end_date else None,
        "end_fraction": end_fraction,
        "end_offset": end_offset,
        "late": bool(promised and end_date and end_date > promised),
    }


def _parse_day(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def normalize_item(raw: dict) -> dict:
    allocation = raw.get("allocation_type") or "internal"
    work_days = [str(day)[:10] for day in (raw.get("work_days") or []) if day]
    return {
        "id": raw.get("id"),
        "code": raw.get("code") or raw.get("order_no"),
        "order_id": raw.get("order_id") or raw.get("production_order_id"),
        "client": raw.get("client") or "Cliente",
        "article": raw.get("article") or "Artigo",
        "quantity": float(raw.get("quantity") or 0),
        "sam_minutes": float(raw.get("sam_minutes") or 0),
        "hours": raw.get("hours"),
        "days_needed": raw.get("days_needed"),
        "days_planned": raw.get("days_planned") or len(work_days),
        "days_left": raw.get("days_left"),
        "work_days": work_days,
        "day_share": raw.get("day_share") or {},
        "hours_day": raw.get("hours_day"),
        "source_type": raw.get("source_type") or "confirmed",
        "allocation_type": allocation,
        "supplier_id": raw.get("supplier_id"),
        "supplier_name": raw.get("supplier_name"),
        "line_key": None if allocation == "external" else (raw.get("line_key") or preferred_line_key(raw.get("article") or "")),
        "status": raw.get("status") or "planned",
        "urgent": bool(raw.get("urgent")),
        "start_date": _parse_day(raw.get("start_date")),
        "start_fraction": float(raw.get("start_fraction") or 0),
        "promised_date": _parse_day(raw.get("promised_date")),
        "due_in_days": raw.get("due_in_days"),
        "fabric_ready": raw.get("fabric_ready"),
        "fabric_label": raw.get("fabric_label"),
        "fabric_needed": raw.get("fabric_needed"),
        "fabric_unit": raw.get("fabric_unit"),
        "fabric_missing": raw.get("fabric_missing"),
        "fabric_covered": raw.get("fabric_covered"),
        "fabric_issued": raw.get("fabric_issued"),
        "notes": raw.get("notes") or "",
    }


def _intervals_overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return start_a < end_b and start_b < end_a


def max_concurrent(blocks: list[dict], start: float, end: float) -> int:
    events = []
    for block in blocks:
        lo = max(block["start_offset"], start)
        hi = min(block["end_offset"], end)
        if lo < hi:
            events.append((lo, 1))
            events.append((hi, -1))
    events.sort(key=lambda item: (item[0], item[1]))
    current = peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def earliest_parallel_slot(blocks: list[dict], duration: float, from_offset: float, limit: int = MAX_PARALLEL_ORDERS_PER_LINE) -> float:
    cursor = max(0.0, from_offset)
    if duration <= 0:
        return cursor
    while True:
        overlapping = [
            block for block in blocks
            if _intervals_overlap(cursor, cursor + duration, block["start_offset"], block["end_offset"])
        ]
        if max_concurrent(overlapping, cursor, cursor + duration) < limit:
            return cursor
        ends = [block["end_offset"] for block in overlapping if block["end_offset"] > cursor]
        if not ends:
            return cursor
        cursor = min(ends)


def assign_lanes(items: list[dict], limit: int = MAX_PARALLEL_ORDERS_PER_LINE) -> list[dict]:
    grouped: dict[str, list] = {}
    leftover = []
    for row in items:
        key = row.get("line_key") or "A"
        if row.get("start_offset") is None:
            leftover.append(row)
            continue
        grouped.setdefault(key, []).append(row)
    for key, rows in grouped.items():
        rows.sort(key=lambda row: (row["start_offset"], row.get("id") or 0))
        lane_free = [0.0] * limit
        for row in rows:
            lane = 0
            for index, free_at in enumerate(lane_free):
                if free_at <= row["start_offset"] + 1e-9:
                    lane = index
                    break
            else:
                lane = min(range(limit), key=lambda index: lane_free[index])
            row["lane"] = lane
            row["parallel"] = any(
                other.get("id") != row.get("id") and other.get("line_key") == row.get("line_key")
                and other.get("start_offset") is not None
                and _intervals_overlap(row["start_offset"], row["end_offset"], other["start_offset"], other["end_offset"])
                for other in rows
            )
            lane_free[lane] = row["end_offset"]
    return leftover + [row for rows in grouped.values() for row in rows]


def _prepare_timed(row: dict, origin: date, hours_day: float, fallback_start: date | None = None) -> dict:
    item = normalize_item(row)
    item["duration_days"] = duration_days(order_hours(item["quantity"], item["sam_minutes"]), hours_day)
    start = next_workday(item["start_date"] or fallback_start or origin) if (item.get("start_date") or fallback_start) else next_workday(origin)
    item["start_date"] = start
    item["start_offset"] = offset_of(origin, start, item.get("start_fraction") or 0)
    item["end_offset"] = item["start_offset"] + item["duration_days"]
    return item


def insert_and_push(items: list[dict], new_item: dict, origin: date, extra_hours: bool) -> tuple[list[dict], list[dict]]:
    hours_day = line_hours_per_day(extra_hours)
    placed = _prepare_timed(new_item, origin, hours_day, origin)
    line_items = [
        _prepare_timed(row, origin, hours_day, placed["start_date"])
        for row in items
        if row.get("line_key") == placed["line_key"] and row.get("id") != placed.get("id") and row.get("start_date")
    ]
    others = [
        normalize_item(row) for row in items
        if not (row.get("line_key") == placed["line_key"] and row.get("id") != placed.get("id") and row.get("start_date"))
        and row.get("id") != placed.get("id")
    ]
    line_items.sort(key=lambda row: (row["start_offset"], row.get("id") or 0))
    assigned = [placed]
    audit = []
    for row in line_items:
        duration = row["duration_days"]
        start_off = row["start_offset"]
        if max_concurrent(assigned, start_off, start_off + duration) >= MAX_PARALLEL_ORDERS_PER_LINE:
            cursor = earliest_parallel_slot(assigned, duration, start_off)
            if cursor > start_off + 1e-9:
                old_start = row["start_date"]
                old_end, _ = end_from_start(old_start, duration, row.get("start_fraction") or 0, origin)
                row["start_offset"] = cursor
                row["start_date"], row["start_fraction"] = date_from_offset(origin, cursor)
                row["end_offset"] = cursor + duration
                new_end, _ = end_from_start(row["start_date"], duration, row["start_fraction"], origin)
                audit.append({
                    "code": row["code"],
                    "client": row["client"],
                    "article": row["article"],
                    "line_key": row["line_key"],
                    "old_start": old_start.isoformat(),
                    "old_end": old_end.isoformat(),
                    "new_start": row["start_date"].isoformat(),
                    "new_end": new_end.isoformat(),
                    "delay_days": round(row["start_offset"] - offset_of(origin, old_start, 0), 2),
                })
        assigned.append(row)
    assign_lanes(assigned)
    return others + assigned, audit


def shift_block(items: list[dict], block_id, days: int, origin: date, extra_hours: bool) -> tuple[list[dict], list[dict]]:
    target = next((row for row in items if row.get("id") == block_id), None)
    if not target or not target.get("start_date"):
        return items, []
    start = _parse_day(target["start_date"])
    if days >= 0:
        start = add_workdays(start, days)
    else:
        current = start
        remaining = -days
        while remaining:
            current -= timedelta(days=1)
            if is_workday(current):
                remaining -= 1
        start = current
    moved = {**target, "start_date": start, "start_fraction": 0}
    remaining_items = [row for row in items if row.get("id") != block_id]
    return insert_and_push(remaining_items, moved, origin, extra_hours)


def apply_extra_hours(items: list[dict], extra_hours: bool, origin: date) -> list[dict]:
    hours_day = line_hours_per_day(extra_hours)
    leftover = []
    grouped = defaultdict(list)
    for row in items:
        item = normalize_item(row)
        if not item.get("start_date"):
            leftover.append(item)
            continue
        item["duration_days"] = duration_days(order_hours(item["quantity"], item["sam_minutes"]), hours_day)
        item["start_offset"] = offset_of(origin, item["start_date"], item.get("start_fraction") or 0)
        item["end_offset"] = item["start_offset"] + item["duration_days"]
        grouped[item["line_key"]].append(item)
    result = []
    for line in grouped.values():
        line.sort(key=lambda row: (row["start_offset"], row.get("id") or 0))
        assigned = []
        for row in line:
            duration = row["duration_days"]
            if assigned and max_concurrent(assigned, row["start_offset"], row["start_offset"] + duration) >= MAX_PARALLEL_ORDERS_PER_LINE:
                row["start_offset"] = earliest_parallel_slot(assigned, duration, row["start_offset"])
                row["start_date"], row["start_fraction"] = date_from_offset(origin, row["start_offset"])
                row["end_offset"] = row["start_offset"] + duration
            assigned.append(row)
        assign_lanes(assigned)
        result.extend(assigned)
    return leftover + result


def daily_allocation(items: list[dict], workdays: list[date], extra_hours: bool, origin: date) -> list[dict]:
    hours_day = line_hours_per_day(extra_hours)
    plant = plant_hours_per_day(extra_hours)
    rows = []
    prepared = [_block_payload(normalize_item(row), extra_hours, origin) for row in items if row.get("start_date")]
    for day in workdays:
        day_index = offset_of(origin, day, 0)
        by_line = defaultdict(float)
        for block in prepared:
            start = block["start_offset"]
            end = block["end_offset"]
            overlap = max(0.0, min(end, day_index + 1) - max(start, day_index))
            if overlap > 0:
                by_line[block["line_key"]] += overlap * hours_day
        total = sum(by_line.values())
        pct = (total / plant * 100) if plant else 0
        remaining = plant - total
        rows.append({
            "date": day.isoformat(),
            "weekday": day.strftime("%a"),
            "iso_week": iso_week(day),
            "hours": round(total, 1),
            "capacity": plant,
            "occupancy_pct": round(pct, 1),
            "tone": occupancy_tone(pct),
            "free_hours": round(max(0, remaining), 1),
            "overload_hours": round(max(0, -remaining), 1),
            "lines": {key: round(value, 1) for key, value in by_line.items()},
        })
    return rows


def weekly_heatmap(daily: list[dict], extra_hours: bool, items: list[dict]) -> list[dict]:
    plant_week = plant_hours_per_week(extra_hours)
    groups: dict[int, list] = {}
    for row in daily:
        groups.setdefault(row["iso_week"], []).append(row)
    weeks = []
    first_free = None
    for week_no in sorted(groups):
        rows = groups[week_no]
        hours = sum(row["hours"] for row in rows)
        pct = hours / plant_week * 100 if plant_week else 0
        start = rows[0]["date"]
        ops = []
        for item in items:
            start_date = _parse_day(item.get("start_date"))
            if not start_date:
                continue
            if iso_week(start_date) == week_no or any(iso_week(date.fromisoformat(row["date"])) == week_no and True for row in rows):
                hours_item = order_hours(item.get("quantity") or 0, item.get("sam_minutes") or 0)
                end = _parse_day(item.get("end_date")) or start_date
                week_start = date.fromisoformat(start)
                week_end = date.fromisoformat(rows[-1]["date"])
                if end < week_start or start_date > week_end:
                    continue
                ops.append({
                    "code": item.get("code"),
                    "client": item.get("client"),
                    "article": item.get("article"),
                    "quantity": item.get("quantity"),
                    "hours": round(hours_item, 1),
                    "line_key": item.get("line_key"),
                })
        unique_ops = []
        seen = set()
        for op in ops:
            if op["code"] in seen:
                continue
            seen.add(op["code"])
            unique_ops.append(op)
        blocked = pct > 100
        if first_free is None and pct < 80:
            first_free = week_no
        weeks.append({
            "iso_week": week_no,
            "start": start,
            "end": rows[-1]["date"],
            "hours": round(hours, 1),
            "capacity": plant_week,
            "occupancy_pct": round(pct, 1),
            "tone": occupancy_tone(pct),
            "overload": blocked,
            "orders": unique_ops,
            "free": not blocked and pct < 80,
        })
    if first_free is None:
        for week in weeks:
            if week["occupancy_pct"] <= 100:
                first_free = week["iso_week"]
                break
    for week in weeks:
        week["first_free"] = week["iso_week"] == first_free
    return weeks


def gap_hint(items: list[dict], line_key: str, day: date, extra_hours: bool, origin: date) -> dict:
    hours_day = line_hours_per_day(extra_hours)
    blocks = [_block_payload(normalize_item(row), extra_hours, origin) for row in items if row.get("line_key") == line_key and row.get("start_date")]
    day_off = offset_of(origin, day, 0)
    concurrent = max_concurrent(blocks, day_off, day_off + 1)
    occupied = concurrent >= MAX_PARALLEL_ORDERS_PER_LINE
    parallel_free = concurrent == 1
    start_off = earliest_parallel_slot(blocks, 0.8, day_off)
    if parallel_free:
        start_off = day_off
    next_release = min((block["end_offset"] for block in blocks if block["end_offset"] > day_off), default=day_off + 8)
    gap = max(0.0, next_release - start_off) if occupied else 8.0
    return {
        "occupied": occupied,
        "parallel_free": parallel_free,
        "concurrent": concurrent,
        "free_days": round(max(0, gap), 2),
        "free_hours": round(max(0, gap) * hours_day, 1),
        "start_offset": start_off,
    }


def simulate_accept(items: list[dict], quantity: float, sam_minutes: float, promised: date | None, extra_hours: bool, today: date, article: str = "") -> dict:
    hours = order_hours(quantity, sam_minutes)
    duration = duration_days(hours, line_hours_per_day(extra_hours))
    origin = monday_of(today)
    days = horizon_workdays(today, HORIZON_WEEKS)
    daily = daily_allocation(items, days, extra_hours, origin)
    weekly = weekly_heatmap(daily, extra_hours, [_block_payload(normalize_item(row), extra_hours, origin) for row in items if row.get("start_date")])
    plant_day = plant_hours_per_day(extra_hours)
    free_before = 0.0
    limit = promised or days[-1]
    for row in daily:
        day = date.fromisoformat(row["date"])
        if day > limit:
            break
        if day >= today:
            free_before += row["free_hours"]
    target_week = iso_week(promised) if promised else iso_week(today)
    week_row = next((row for row in weekly if row["iso_week"] == target_week), None)
    alternatives = [row for row in weekly if row["occupancy_pct"] + hours / plant_hours_per_week(extra_hours) * 100 <= 100 or row["free"]]
    viable = free_before >= hours and (not week_row or week_row["occupancy_pct"] <= 100)
    needs_schedule = bool(week_row and week_row["occupancy_pct"] > 100)
    if needs_schedule:
        verdict = "REQUER ESCALONAMENTO"
        detail = f"A semana {target_week} está a {week_row['occupancy_pct']:.1f}% (>100%)."
    elif viable:
        verdict = "VIÁVEL / PODE ACEITAR"
        detail = f"Há {round(free_before, 1)} h livres antes da data prometida para {round(hours, 1)} h necessárias."
    else:
        verdict = "REQUER ESCALONAMENTO"
        detail = "Capacidade livre insuficiente até à data prometida."
    line_key = preferred_line_key(article)
    return {
        "hours": round(hours, 1),
        "duration_days": display_duration(duration),
        "verdict": verdict,
        "viable": viable and not needs_schedule,
        "needs_scheduling": needs_schedule or not viable,
        "detail": detail,
        "target_week": target_week,
        "week_occupancy_pct": week_row["occupancy_pct"] if week_row else None,
        "free_hours_before": round(free_before, 1),
        "preferred_line": line_key,
        "alternatives": [
            {
                "iso_week": row["iso_week"],
                "occupancy_pct": row["occupancy_pct"],
                "start": row["start"],
                "label": f"Semana {row['iso_week']} · {row['occupancy_pct']:.1f}%",
            }
            for row in alternatives[:4]
        ],
        "plant_hours_day": plant_day,
    }


def scenario_cards(weekly: list[dict], extra_hours: bool, items: list[dict]) -> list[dict]:
    focus = next((row for row in weekly if row["overload"]), weekly[1] if len(weekly) > 1 else weekly[0] if weekly else None)
    week_no = focus["iso_week"] if focus else 35
    hours = focus["hours"] if focus else 0
    normal_pct = hours / PLANT_HOURS_WEEK * 100 if PLANT_HOURS_WEEK else 0
    extra_pct = hours / PLANT_HOURS_WEEK_EXTRA * 100 if PLANT_HOURS_WEEK_EXTRA else 0
    extra_hours_week = PLANT_POSTS * EXTRA_HOURS_PERSON * 5
    extra_cost = extra_hours_week * OVERTIME_PREMIUM_EUR
    pulled = 0.0
    for item in items:
        hours_item = order_hours(item.get("quantity") or 0, item.get("sam_minutes") or 0)
        pulled += duration_days(hours_item, LINE_HOURS_DAY) - duration_days(hours_item, LINE_HOURS_DAY_EXTRA)
    faccao_hours = max(0, hours - PLANT_HOURS_WEEK)
    internal_after = hours - max(faccao_hours, hours * FACCAO_SHARE if hours > PLANT_HOURS_WEEK else hours * 0.1)
    faccao_pct = internal_after / PLANT_HOURS_WEEK * 100 if PLANT_HOURS_WEEK else 0
    return [
        {
            "id": 1,
            "name": "Cenário 1 — Regime Normal",
            "capacity_week": PLANT_HOURS_WEEK,
            "week": week_no,
            "occupancy_pct": round(normal_pct, 1),
            "tone": occupancy_tone(normal_pct),
            "label": "Sobrecarga" if normal_pct > 100 else "Viável",
            "current": not extra_hours,
            "detail": f"{PLANT_POSTS} postos × {NOMINAL_HOURS_PERSON}h = {PLANT_HOURS_WEEK:.0f}h/semana",
        },
        {
            "id": 2,
            "name": "Cenário 2 — Horas Extra (+2h/dia)",
            "capacity_week": PLANT_HOURS_WEEK_EXTRA,
            "week": week_no,
            "occupancy_pct": round(extra_pct, 1),
            "tone": occupancy_tone(extra_pct),
            "label": "Viável" if extra_pct <= 100 else "Sobrecarga",
            "current": extra_hours,
            "anticipation_days": round(pulled, 1),
            "extra_cost": round(extra_cost, 0),
            "detail": f"+{extra_hours_week:.0f}h/semana · antecipação {round(pulled, 1)} dias · +€{extra_cost:,.0f}".replace(",", "."),
        },
        {
            "id": 3,
            "name": "Cenário 3 — Facção Externa",
            "capacity_week": PLANT_HOURS_WEEK,
            "week": week_no,
            "occupancy_pct": round(min(faccao_pct, 99.9), 1),
            "tone": occupancy_tone(min(faccao_pct, 99.9)),
            "label": "Viável",
            "current": False,
            "external_hours": round(max(faccao_hours, hours * FACCAO_SHARE if focus and focus["overload"] else hours * 0.12), 1),
            "detail": "Parte do lote vai para oficinas parceiras, libertando a semana crítica.",
        },
    ]


def heijunka_consult(items: list[dict], extra_hours: bool, today: date) -> dict:
    origin = monday_of(today)
    scheduled = [normalize_item(row) for row in items if row.get("start_date")]
    backlog = [normalize_item(row) for row in items if not row.get("start_date")]
    days = horizon_workdays(today, HORIZON_WEEKS)
    daily = daily_allocation(scheduled, days, extra_hours, origin)
    prepared = [_block_payload(row, extra_hours, origin) for row in scheduled]
    weekly = weekly_heatmap(daily, extra_hours, prepared)
    by_line = defaultdict(list)
    for row in prepared:
        by_line[row["line_key"]].append(row)
    hours_by_line = {key: round(sum(order_hours(row["quantity"], row["sam_minutes"]) for row in rows), 1) for key, rows in by_line.items()}
    mean = (sum(hours_by_line.values()) / len(hours_by_line)) if hours_by_line else 0
    suggestions = []
    overloaded = sorted(hours_by_line, key=hours_by_line.get, reverse=True)
    underloaded = sorted(hours_by_line, key=hours_by_line.get)
    if hours_by_line and hours_by_line[overloaded[0]] - hours_by_line[underloaded[0]] > LINE_HOURS_DAY:
        donor = overloaded[0]
        receiver = underloaded[0]
        candidates = sorted(by_line[donor], key=lambda row: row["hours"])
        movable = next((row for row in candidates if preferred_line_key(row["article"]) == receiver or row["hours"] < mean * 0.25), candidates[0] if candidates else None)
        if movable:
            suggestions.append({
                "type": "move",
                "code": movable["code"],
                "from_line": donor,
                "to_line": receiver,
                "reason": (
                    f"Heijunka: {movable['code']} ({round(movable['hours'], 1)} h) deve passar de Linha {donor} "
                    f"({hours_by_line[donor]} h) para Linha {receiver} ({hours_by_line[receiver]} h) para nivelar a carga."
                ),
            })
    for week in weekly:
        if week["overload"]:
            suggestions.append({
                "type": "week",
                "code": None,
                "from_line": None,
                "to_line": None,
                "reason": (
                    f"Semana {week['iso_week']} está a {week['occupancy_pct']}% (>100%). "
                    f"Adiar 1 OP desta semana ou ligar horas extra reduz a sobrecarga."
                ),
            })
    for row in prepared:
        if row.get("late"):
            suggestions.append({
                "type": "deadline",
                "code": row["code"],
                "from_line": row["line_key"],
                "to_line": None,
                "reason": f"{row['code']} termina a {row['end_date']}, depois da data prometida {row['promised_date']}.",
            })
    bottlenecks = [row for row in daily if row["occupancy_pct"] > 100]
    if bottlenecks:
        first = bottlenecks[0]
        suggestions.append({
            "type": "bottleneck",
            "code": None,
            "from_line": max(first["lines"], key=first["lines"].get),
            "to_line": min(first["lines"], key=first["lines"].get),
            "reason": (
                f"Gargalo a {date.fromisoformat(first['date']).strftime('%d/%m')}: {first['hours']} h "
                f"para {first['capacity']} h ({first['occupancy_pct']}%). "
                f"Linha {max(first['lines'], key=first['lines'].get)} concentra {max(first['lines'].values())} h."
            ),
        })
    for row in backlog[:3]:
        line = preferred_line_key(row["article"])
        suggestions.append({
            "type": "backlog",
            "code": row["code"],
            "from_line": None,
            "to_line": line,
            "reason": f"Encaixar {row['code']} na Linha {line} (família {row['article']}) no primeiro intervalo livre.",
        })
    if not suggestions:
        suggestions.append({
            "type": "ok",
            "code": None,
            "from_line": None,
            "to_line": None,
            "reason": "Carga equilibrada nas linhas. Sem movimentos Heijunka obrigatórios.",
        })
    load_summary = " · ".join(f"{key} {hours_by_line[key]} h" for key in sorted(hours_by_line)) or "sem carga"
    return {
        "summary": (
            f"Carga por linha: {load_summary}. "
            f"{len(scheduled)} OPs no Gantt, {len(backlog)} no backlog."
        ),
        "hours_by_line": hours_by_line,
        "overloaded_days": len(bottlenecks),
        "suggestions": suggestions[:8],
    }


def first_fit(items: list[dict], new_item: dict, extra_hours: bool, today: date) -> dict:
    origin = monday_of(today)
    placed = normalize_item(new_item)
    placed["line_key"] = placed.get("line_key") or preferred_line_key(placed["article"])
    hours_day = line_hours_per_day(extra_hours)
    duration = duration_days(order_hours(placed["quantity"], placed["sam_minutes"]), hours_day)
    line_blocks = [_block_payload(normalize_item(row), extra_hours, origin) for row in items if row.get("line_key") == placed["line_key"] and row.get("start_date")]
    cursor = earliest_parallel_slot(line_blocks, duration, offset_of(origin, next_workday(today), 0))
    start, frac = date_from_offset(origin, cursor)
    placed["start_date"] = start
    placed["start_fraction"] = frac
    return placed


def build_board(items: list[dict], today: date, extra_hours: bool = False, weeks: int = HORIZON_WEEKS, catalog: list[dict] | None = None) -> dict:
    origin = monday_of(today)
    lines = list(catalog) if catalog else list(LINE_CATALOG)
    hours_day = line_hours_per_day(extra_hours)
    plant_day = round(sum((row.get("hours_day") or hours_day) for row in lines) * (LINE_HOURS_DAY_EXTRA / LINE_HOURS_DAY if extra_hours else 1), 1)
    plant_week = round(plant_day * 5, 1)
    scheduled_raw = [normalize_item(row) for row in items if row.get("status") != "backlog" and row.get("start_date")]
    backlog_raw = [normalize_item(row) for row in items if row.get("status") == "backlog" or not row.get("start_date")]
    scheduled = [_block_payload(row, extra_hours, origin) for row in scheduled_raw]
    assign_lanes(scheduled)
    backlog = [_block_payload({**row, "start_date": None}, extra_hours, origin) for row in backlog_raw]
    for row in backlog:
        row["start_date"] = None
        row["end_date"] = None
        row["start_offset"] = None
        row["end_offset"] = None
        row["duration_display"] = display_duration(duration_days(row["hours"], hours_day))
    days = horizon_workdays(today, weeks)
    daily = daily_allocation(scheduled_raw, days, extra_hours, origin)
    weekly = weekly_heatmap(daily, extra_hours, scheduled)
    backlog_hours = sum(row["hours"] for row in backlog)
    return {
        "today": today.isoformat(),
        "today_label": today.strftime("%d/%m/%Y"),
        "weekday_label": ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"][today.weekday()],
        "iso_week": iso_week(today),
        "origin": origin.isoformat(),
        "extra_hours": extra_hours,
        "line_hours_day": hours_day,
        "max_parallel": MAX_PARALLEL_ORDERS_PER_LINE,
        "plant_hours_day": plant_day if catalog else plant_hours_per_day(extra_hours),
        "plant_hours_week": plant_week if catalog else plant_hours_per_week(extra_hours),
        "lines": [
            {
                **{k: v for k, v in line.items() if k != "keywords"},
                "hours_day": line.get("hours_day") or hours_day,
                "posts_count": line.get("posts_count") or POSTS_PER_LINE,
            }
            for line in lines
        ],
        "workdays": [
            {
                "date": day.isoformat(),
                "iso_week": iso_week(day),
                "weekday": ["Seg", "Ter", "Qua", "Qui", "Sex"][day.weekday()],
                "day": day.strftime("%d/%m"),
                "is_today": day == today,
            }
            for day in days
        ],
        "scheduled": scheduled,
        "backlog": backlog,
        "daily": daily,
        "weekly": weekly,
        "scenarios": scenario_cards(weekly, extra_hours, scheduled_raw),
        "backlog_totals": {
            "count": len(backlog),
            "hours": round(backlog_hours, 1),
            "duration_days": display_duration(duration_days(backlog_hours, plant_hours_per_day(extra_hours))),
        },
        "first_free_week": next((row["iso_week"] for row in weekly if row.get("first_free")), None),
    }


def audit_message(audit: list[dict], title: str) -> str:
    if not audit:
        return title
    lines = [title, ""]
    for row in audit:
        lines.append(
            f"{row['code']} · {row['client']} — {row['old_end']} → {row['new_end']} "
            f"(+{row['delay_days']} dias úteis)"
        )
    return "\n".join(lines)


def deepcopy_items(items: list[dict]) -> list[dict]:
    return deepcopy(items)


def ceil_hours(value: float) -> int:
    return int(ceil(value))
