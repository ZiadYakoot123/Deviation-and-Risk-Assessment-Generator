from __future__ import annotations

from datetime import datetime
import base64
from email import message_from_bytes
import json
from pathlib import Path

import pytest

from deviation_risk_generator.cdc import (
    CDCConfig,
    CDCConfigurationError,
    build_ai_agent_handler,
    validate_alarm_data,
)
from deviation_risk_generator.engine import DeviationRiskEngine
from deviation_risk_generator.knowledge_base import load_knowledge_base


def test_validate_alarm_data_normalizes_alarm_row() -> None:
    result = validate_alarm_data(
        {
            "sensor_number": "BMS-101",
            "time": datetime(2026, 9, 23, 13, 30),
            "value": "24.5",
            "trend": "high",
        }
    )

    assert result == {
        "sensor_number": "BMS-101",
        "timestamp": "2026-09-23T13:30:00",
        "value": 24.5,
        "trend": "high",
    }


def test_validate_alarm_data_rejects_missing_field() -> None:
    with pytest.raises(ValueError, match="Missing critical field 'trend'"):
        validate_alarm_data(
            {
                "sensor_number": "BMS-101",
                "time": datetime(2026, 9, 23, 13, 30),
                "value": 24.5,
            }
        )


def test_cdc_config_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BMS_DB_USER", raising=False)
    monkeypatch.delenv("BMS_DB_PASS", raising=False)

    with pytest.raises(CDCConfigurationError):
        CDCConfig.from_env()


def test_cdc_alarm_reaches_engine_and_builds_gmail_draft(tmp_path: Path) -> None:
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(
        json.dumps(
            {
                "sops": {
                    "risk_assessment": "QMS-SOP-RA-001",
                    "deviation": "QMS-SOP-DEV-003",
                },
                "layouts": {
                    "sensors": {
                        "BMS-101": {"location": "Granulation-01", "room_class": "C"}
                    },
                    "room_time_windows": {
                        "Granulation-01": [["08:00", "12:00"]]
                    },
                },
                "products": {"Product-A": {"criticality": "High"}},
            }
        ),
        encoding="utf-8",
    )
    plan_path = tmp_path / "plan.csv"
    plan_path.write_text(
        "DATE,PRODUCT,ROOM_CLASS\n2026-09-23,Product-A,C\n",
        encoding="utf-8",
    )

    handler = build_ai_agent_handler(
        DeviationRiskEngine(load_knowledge_base(kb_path), qa_email="qa@example.com"),
        "Product-A",
        str(plan_path),
    )
    decision = handler(
        validate_alarm_data(
            {
                "sensor_number": "BMS-101",
                "time": datetime(2026, 9, 23, 13, 30),
                "value": "24.5",
                "trend": "high",
            }
        )
    )

    raw = decision.qa_mail_draft["message"]["raw"]
    message = message_from_bytes(base64.urlsafe_b64decode(raw))
    body = message.get_payload(decode=True).decode()
    assert decision.start_deviation is True
    assert decision.alarm_value == 24.5
    assert decision.alarm_trend == "high"
    assert decision.assessment_id in body
    assert "Alarm value: 24.5" in body
    assert message["To"] == "qa@example.com"
