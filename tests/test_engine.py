from __future__ import annotations

from datetime import date
from pathlib import Path
import json

from openpyxl import Workbook

from deviation_risk_generator.engine import DeviationRiskEngine
from deviation_risk_generator.knowledge_base import load_knowledge_base


def _create_csv_plan(tmp_path: Path, batch_date: date, product: str, room_class: str) -> Path:
    plan_path = tmp_path / "plan.csv"
    plan_path.write_text(
        f"date,product,room_class\n{batch_date.isoformat()},{product},{room_class}\n",
        encoding="utf-8",
    )
    return plan_path


def _create_kb(tmp_path: Path) -> Path:
    kb = {
        "sops": {
            "risk_assessment": "QMS-SOP-RA-001",
            "deviation": "QMS-SOP-DEV-003",
            "alarm_handling": "QMS-SOP-BMS-ALM-002",
            "capa": "QMS-SOP-CAPA-001",
        },
        "layouts": {
            "sensors": {
                "BMS-101": {
                    "location": "Granulation-01",
                    "room_class": "C",
                    "parameter": "temperature",
                    "unit": "degC",
                    "limits": {"min": 18, "max": 25},
                },
            },
            "room_time_windows": {
                "Granulation-01": [["08:00", "12:00"]],
            },
        },
        "products": {
            "Product-A": {
                "criticality": "High",
                "risk_factors": ["Temperature-sensitive"],
            },
        },
        "capa_actions": {
            "immediate": ["Acknowledge alarm"],
            "corrective": ["Investigate cause"],
            "preventive": ["Trend recurring alarms"],
        },
    }
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(json.dumps(kb), encoding="utf-8")
    return kb_path


def _create_plan(tmp_path: Path, batch_date: date, product: str, room_class: str) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(["date", "product", "room_class"])
    ws.append([batch_date.isoformat(), product, room_class])
    plan_path = tmp_path / "plan.xlsx"
    wb.save(plan_path)
    return plan_path


def test_starts_deviation_when_outside_window_and_production_active(tmp_path: Path) -> None:
    kb_path = _create_kb(tmp_path)
    plan_path = _create_plan(tmp_path, date(2026, 9, 23), "Product-A", "C")

    engine = DeviationRiskEngine(load_knowledge_base(kb_path))
    result = engine.evaluate(
        sensor_number="BMS-101",
        trend_image_path="trend_20260923_1330.png",
        product_name="Product-A",
        production_plan_xlsx=str(plan_path),
    )

    assert result.start_deviation is True
    assert result.criticality == "High"
    assert "GAMP5-aligned" in result.risk_assessment
    assert "raw" in result.qa_mail_draft["message"]


def test_skips_deviation_when_within_window(tmp_path: Path) -> None:
    kb_path = _create_kb(tmp_path)
    plan_path = _create_plan(tmp_path, date(2026, 9, 23), "Product-A", "C")

    engine = DeviationRiskEngine(load_knowledge_base(kb_path))
    result = engine.evaluate(
        sensor_number="BMS-101",
        trend_image_path="trend_20260923_0930.png",
        product_name="Product-A",
        production_plan_xlsx=str(plan_path),
    )

    assert result.start_deviation is False
    assert "within accepted window" in result.reason


def test_handles_real_world_sensor_and_product_variants(tmp_path: Path) -> None:
    kb_path = _create_kb(tmp_path)
    plan_path = _create_plan(tmp_path, date(2026, 9, 23), "Product-A", "C")

    engine = DeviationRiskEngine(load_knowledge_base(kb_path))
    result = engine.evaluate(
        sensor_number="bms101",
        trend_image_path="sensor_bms101_20260923_1330.png",
        product_name=" product a ",
        production_plan_xlsx=str(plan_path),
    )

    assert result.start_deviation is True
    assert result.room == "Granulation-01"
    assert result.criticality == "High"


def test_reads_csv_production_plan(tmp_path: Path) -> None:
    kb_path = _create_kb(tmp_path)
    plan_path = _create_csv_plan(tmp_path, date(2026, 9, 23), "Product-A", "C")

    engine = DeviationRiskEngine(load_knowledge_base(kb_path))
    result = engine.evaluate(
        sensor_number="BMS-101",
        trend_image_path="trend_20260923_1330.png",
        product_name="Product-A",
        production_plan_xlsx=str(plan_path),
    )

    assert result.start_deviation is True


def test_accepts_overnight_room_window(tmp_path: Path) -> None:
    kb_path = _create_kb(tmp_path)
    kb = json.loads(kb_path.read_text(encoding="utf-8"))
    kb["layouts"]["room_time_windows"]["Granulation-01"] = [["22:00", "06:00"]]
    kb_path.write_text(json.dumps(kb), encoding="utf-8")
    plan_path = _create_plan(tmp_path, date(2026, 9, 23), "Product-A", "C")

    engine = DeviationRiskEngine(load_knowledge_base(kb_path))
    result = engine.evaluate(
        sensor_number="BMS-101",
        trend_image_path="trend_20260923_2330.png",
        product_name="Product-A",
        production_plan_xlsx=str(plan_path),
    )

    assert result.start_deviation is False
    assert "within accepted window" in result.reason


def test_includes_sensor_limits_room_controls_and_capa(tmp_path: Path) -> None:
    kb_path = _create_kb(tmp_path)
    plan_path = _create_plan(tmp_path, date(2026, 9, 23), "Product-A", "C")

    engine = DeviationRiskEngine(load_knowledge_base(kb_path))
    result = engine.evaluate(
        sensor_number="BMS-101",
        trend_image_path="trend_20260923_0930.png",
        product_name="Product-A",
        production_plan_xlsx=str(plan_path),
        alarm_value=27,
        alarm_trend="high",
    )

    assert result.start_deviation is True
    assert result.limit_status == "out_of_limit"
    assert result.capa_actions["corrective"] == ["Investigate cause"]
    assert "Sensor limits: 18 to 25" in result.risk_assessment
