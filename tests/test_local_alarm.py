from __future__ import annotations

import json
from pathlib import Path

from deviation_risk_generator.cdc import run_local_alarm


def test_run_local_alarm_without_mysql(
    tmp_path: Path, capsys
) -> None:
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(
        json.dumps(
            {
                "sops": {"risk_assessment": "RA-001", "deviation": "DEV-001"},
                "layouts": {
                    "sensors": {
                        "BMS-101": {"location": "Granulation-01", "room_class": "C"}
                    },
                    "room_time_windows": {"Granulation-01": [["08:00", "12:00"]]},
                },
                "products": {"Product-A": {"criticality": "High"}},
            }
        ),
        encoding="utf-8",
    )
    plan_path = tmp_path / "plan.csv"
    plan_path.write_text(
        "date,product,room_class\n2026-09-23,Product-A,C\n",
        encoding="utf-8",
    )

    run_local_alarm(
        sensor_number="BMS-101",
        alarm_time="2026-09-23T13:30:00",
        value="24.5",
        trend="high",
        knowledge_base=str(kb_path),
        production_plan=str(plan_path),
        product_name="Product-A",
    )

    result = json.loads(capsys.readouterr().out)
    assert result["start_deviation"] is True
    assert result["alarm_value"] == 24.5
    assert result["alarm_trend"] == "high"
