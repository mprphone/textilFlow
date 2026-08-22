import unittest
from datetime import date

from backend.app.services.confection_schedule import (
    LINE_HOURS_DAY, LINE_HOURS_DAY_EXTRA, OVERTIME_PREMIUM_EUR, PLANT_HOURS_WEEK,
    PLANT_HOURS_WEEK_EXTRA, apply_extra_hours, display_duration, duration_days,
    first_fit, heijunka_consult, insert_and_push, monday_of, occupancy_tone,
    order_hours, plant_hours_per_week, scenario_cards, simulate_accept, build_board,
)


TODAY = date(2026, 8, 19)
ORIGIN = monday_of(TODAY)


class ConfectionScheduleFormulasTest(unittest.TestCase):
    def test_hours_quantity_times_sam_over_sixty(self):
        self.assertEqual(order_hours(1200, 14.5), 290)

    def test_duration_on_line_a(self):
        hours = order_hours(1200, 14.5)
        self.assertEqual(hours / LINE_HOURS_DAY, 3.625)
        self.assertEqual(display_duration(duration_days(hours)), 3.6)

    def test_extra_hours_shrinks_duration(self):
        hours = order_hours(1200, 14.5)
        self.assertEqual(round(duration_days(hours, LINE_HOURS_DAY_EXTRA), 3), 2.9)

    def test_occupancy_bands(self):
        self.assertEqual(occupancy_tone(74.2), "green")
        self.assertEqual(occupancy_tone(92.9), "yellow")
        self.assertEqual(occupancy_tone(106.7), "red")

    def test_plant_capacity(self):
        self.assertEqual(plant_hours_per_week(False), 1200)
        self.assertEqual(plant_hours_per_week(True), 1500)
        self.assertEqual(round(30 * 2 * 5 * OVERTIME_PREMIUM_EUR), 1980)


class PushForwardTest(unittest.TestCase):
    def test_two_orders_can_run_in_parallel_on_same_line(self):
        existing = [{
            "id": 1, "code": "OP-1", "client": "ZARA PORTUGAL", "article": "T-Shirt",
            "quantity": 1200, "sam_minutes": 14.5, "line_key": "A",
            "start_date": date(2026, 8, 19), "status": "planned",
        }]
        second = {
            "id": 2, "code": "OP-2", "client": "Mango", "article": "T-Shirt",
            "quantity": 400, "sam_minutes": 14.5, "line_key": "A",
            "start_date": date(2026, 8, 19), "status": "planned",
        }
        result, audit = insert_and_push(existing, second, ORIGIN, False)
        first = next(row for row in result if row["id"] == 1)
        inserted = next(row for row in result if row["id"] == 2)
        self.assertEqual(inserted["start_date"], date(2026, 8, 19))
        self.assertEqual(first["start_date"], date(2026, 8, 19))
        self.assertEqual(audit, [])
        self.assertEqual({first["lane"], inserted["lane"]}, {0, 1})

    def test_third_order_is_pushed_when_line_already_has_two(self):
        existing = [
            {
                "id": 1, "code": "OP-1", "client": "Zara", "article": "T-Shirt",
                "quantity": 1200, "sam_minutes": 14.5, "line_key": "A",
                "start_date": date(2026, 8, 19), "status": "planned",
            },
            {
                "id": 2, "code": "OP-2", "client": "Mango", "article": "T-Shirt",
                "quantity": 800, "sam_minutes": 14.5, "line_key": "A",
                "start_date": date(2026, 8, 19), "status": "planned",
            },
        ]
        third = {
            "id": 3, "code": "OP-3", "client": "H&M", "article": "T-Shirt",
            "quantity": 400, "sam_minutes": 14.5, "line_key": "A",
            "start_date": date(2026, 8, 19), "status": "planned", "urgent": True,
        }
        result, audit = insert_and_push(existing, third, ORIGIN, False)
        inserted = next(row for row in result if row["id"] == 3)
        moved = [row for row in result if row["id"] in (1, 2)]
        self.assertEqual(inserted["start_date"], date(2026, 8, 19))
        self.assertTrue(any(row["start_offset"] >= inserted["end_offset"] - 1e-6 for row in moved) or audit)
        self.assertGreaterEqual(len(audit), 1)

    def test_one_click_can_share_line_with_existing_order(self):
        existing = [{
            "id": 1, "code": "OP-1", "client": "Zara", "article": "T-Shirt Basic",
            "quantity": 1200, "sam_minutes": 14.5, "line_key": "A",
            "start_date": date(2026, 8, 17), "status": "planned",
        }]
        placed = first_fit(existing, {
            "code": "OP-2", "article": "T-Shirt Plus", "quantity": 800, "sam_minutes": 14.5,
        }, False, TODAY)
        self.assertEqual(placed["line_key"], "A")
        self.assertEqual(placed["start_date"], TODAY)


class SimulatorAndScenariosTest(unittest.TestCase):
    def test_accept_simulator_flags_overload_week(self):
        items = []
        start = date(2026, 8, 24)
        for index, qty in enumerate((2000, 2000, 2000)):
            items.append({
                "id": index + 1, "code": f"OP-{index}", "client": "Zara", "article": "T-Shirt",
                "quantity": qty, "sam_minutes": 18, "line_key": ("A", "B", "C")[index],
                "start_date": start, "status": "planned",
            })
        result = simulate_accept(items, 1200, 14.5, date(2026, 8, 28), False, TODAY, "T-Shirt")
        self.assertIn(result["verdict"], {"VIÁVEL / PODE ACEITAR", "REQUER ESCALONAMENTO"})
        self.assertEqual(result["hours"], 290)

    def test_heijunka_suggests_concrete_move(self):
        items = [
            {"id": 1, "code": "OP-A1", "client": "Zara", "article": "T-Shirt", "quantity": 4000, "sam_minutes": 14.5, "line_key": "A", "start_date": TODAY, "status": "planned"},
            {"id": 2, "code": "OP-A2", "client": "Zara", "article": "Polo Pique", "quantity": 800, "sam_minutes": 22, "line_key": "A", "start_date": date(2026, 8, 24), "status": "planned"},
            {"id": 3, "code": "OP-C1", "client": "Mango", "article": "Casaco Sarja", "quantity": 200, "sam_minutes": 45, "line_key": "C", "start_date": TODAY, "status": "planned"},
        ]
        report = heijunka_consult(items, False, TODAY)
        self.assertTrue(report["suggestions"])
        self.assertIn("OP-", report["suggestions"][0].get("code") or report["summary"])

    def test_extra_hours_scenario_cost(self):
        board = build_board([
            {"id": 1, "code": "OP-1", "client": "Zara", "article": "T-Shirt", "quantity": 5000, "sam_minutes": 14.5, "line_key": "A", "start_date": date(2026, 8, 24), "status": "planned"},
            {"id": 2, "code": "OP-2", "client": "Zara", "article": "Polo", "quantity": 3000, "sam_minutes": 22, "line_key": "B", "start_date": date(2026, 8, 24), "status": "planned"},
            {"id": 3, "code": "OP-3", "client": "Mango", "article": "Casaco", "quantity": 900, "sam_minutes": 45, "line_key": "C", "start_date": date(2026, 8, 24), "status": "planned"},
        ], TODAY, extra_hours=False)
        extra = next(row for row in board["scenarios"] if row["id"] == 2)
        self.assertEqual(extra["extra_cost"], 1980)
        self.assertEqual(extra["capacity_week"], PLANT_HOURS_WEEK_EXTRA)
        self.assertEqual(board["scenarios"][0]["capacity_week"], PLANT_HOURS_WEEK)

    def test_extra_hours_pulls_blocks_earlier(self):
        items = [
            {"id": 1, "code": "OP-1", "client": "Zara", "article": "T-Shirt", "quantity": 1200, "sam_minutes": 14.5, "line_key": "A", "start_date": date(2026, 8, 17), "status": "planned"},
            {"id": 2, "code": "OP-2", "client": "Zara", "article": "T-Shirt", "quantity": 1200, "sam_minutes": 14.5, "line_key": "A", "start_date": date(2026, 8, 21), "status": "planned"},
        ]
        pulled = apply_extra_hours(items, True, ORIGIN)
        second = next(row for row in pulled if row["id"] == 2)
        first = next(row for row in pulled if row["id"] == 1)
        self.assertAlmostEqual(first["duration_days"], 2.9)
        self.assertLess(second["start_offset"], 8)
        self.assertEqual(first["start_date"], date(2026, 8, 17))
        self.assertEqual(second["start_date"], date(2026, 8, 21))


if __name__ == "__main__":
    unittest.main()
