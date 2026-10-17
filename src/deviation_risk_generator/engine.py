from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from math import isfinite
import re
from uuid import uuid4

from .gmail import build_gmail_draft_payload
from .knowledge_base import KnowledgeBase
from .production_plan import load_planned_batches
from .trend import extract_trend_time


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


@dataclass(frozen=True)
class DeviationDecision:
    assessment_id: str
    start_deviation: bool
    reason: str
    room: str
    room_class: str
    criticality: str
    risk_assessment: str
    deviation_summary: str
    qa_mail_draft: dict
    alarm_value: float | None = None
    alarm_trend: str | None = None
    parameter: str | None = None
    unit: str | None = None
    limit_status: str | None = None
    capa_actions: dict | None = None


class DeviationRiskEngine:
    """Simple GAMP5/URS-oriented orchestration with KB-backed lookups (RAG-ready design)."""

    def __init__(self, knowledge_base: KnowledgeBase, qa_email: str = "qa@company.com") -> None:
        self.kb = knowledge_base
        self.qa_email = qa_email

    def evaluate(
        self,
        sensor_number: str,
        trend_image_path: str,
        product_name: str,
        production_plan_xlsx: str,
        alarm_value: float | None = None,
        alarm_trend: str | None = None,
        assessment_id: str | None = None,
    ) -> DeviationDecision:
        if alarm_value is not None and not isfinite(alarm_value):
            raise ValueError("Alarm value must be finite")
        trend_time = extract_trend_time(trend_image_path)
        sensor_meta = self._get_sensor_meta(sensor_number)
        room = sensor_meta["location"]
        room_class = sensor_meta["room_class"]
        parameter = sensor_meta.get("parameter")
        unit = sensor_meta.get("unit")
        limit_status = self._get_limit_status(sensor_meta, alarm_value)
        room_controls = self._get_room_controls(room_class)

        production_day = trend_time.date()
        planned_batches = load_planned_batches(production_plan_xlsx)
        normalized_product_name = _normalize_key(product_name)
        production_active = any(
            batch.date == production_day
            and _normalize_key(batch.product) == normalized_product_name
            and _normalize_key(batch.room_class) == _normalize_key(room_class)
            for batch in planned_batches
        )

        time_accepted = self._is_time_accepted(room, trend_time.time())
        product_rule = self._get_product_rule(product_name)
        criticality = str(product_rule.get("criticality", "Medium"))

        if limit_status == "out_of_limit":
            reason = f"{parameter or 'Sensor'} value is outside approved limits."
            start_deviation = True
        elif not production_active:
            reason = "No matching production in daily plan; no deviation workflow required."
            start_deviation = False
        elif time_accepted:
            reason = "Sensor trend time is within accepted window for this room."
            start_deviation = False
        else:
            reason = "Production is active and trend time is outside accepted room window."
            start_deviation = True

        deviation_summary = (
            f"Sensor {sensor_number} in {room} ({room_class}) at {trend_time.isoformat()} "
            f"for product {product_name}. {reason}"
        )
        risk_assessment = self._generate_risk_assessment(
            product_name=product_name,
            room=room,
            room_class=room_class,
            criticality=criticality,
            start_deviation=start_deviation,
            reason=reason,
            limit_status=limit_status,
            room_controls=room_controls,
            sensor_meta=sensor_meta,
            product_rule=product_rule,
        )
        subject = f"Deviation Assessment - {product_name} - {criticality}"
        assessment_id = assessment_id or str(uuid4())
        alarm_context = (
            f"\nAlarm value: {alarm_value}"
            f"\nAlarm trend: {alarm_trend}"
            f"\nParameter: {parameter} ({unit})"
            f"\nLimit status: {limit_status}"
            if alarm_value is not None or alarm_trend is not None
            else ""
        )
        body = (
            f"Assessment ID: {assessment_id}\n"
            f"Deviation summary:\n{deviation_summary}\n"
            f"{alarm_context}\n\nRisk assessment:\n{risk_assessment}"
        )

        return DeviationDecision(
            assessment_id=assessment_id,
            start_deviation=start_deviation,
            reason=reason,
            room=room,
            room_class=room_class,
            criticality=criticality,
            risk_assessment=risk_assessment,
            deviation_summary=deviation_summary,
            qa_mail_draft=build_gmail_draft_payload(self.qa_email, subject, body),
            alarm_value=alarm_value,
            alarm_trend=alarm_trend,
            parameter=parameter,
            unit=unit,
            limit_status=limit_status,
            capa_actions=self._get_capa_actions(),
        )

    def _get_sensor_meta(self, sensor_number: str) -> dict:
        sensors = self.kb.layouts.get("sensors", {})
        normalized_target = _normalize_key(sensor_number)
        for sensor_key, sensor_meta in sensors.items():
            if _normalize_key(sensor_key) == normalized_target:
                return sensor_meta
        raise KeyError(f"Sensor '{sensor_number}' not found in layout knowledge base")

    def _get_product_rule(self, product_name: str) -> dict:
        products = self.kb.products
        normalized_target = _normalize_key(product_name)
        for product_key, product_meta in products.items():
            if _normalize_key(product_key) == normalized_target:
                return product_meta
        return {}

    def _get_room_controls(self, room_class: str) -> dict:
        return self.kb.layouts.get("room_classes", {}).get(room_class, {})

    @staticmethod
    def _get_limit_status(sensor_meta: dict, alarm_value: float | None) -> str:
        if alarm_value is None:
            return "not_evaluated"
        limits = sensor_meta.get("limits")
        if not limits:
            return "not_configured"
        if alarm_value < limits["min"] or alarm_value > limits["max"]:
            return "out_of_limit"
        return "within_limit"

    def _get_capa_actions(self) -> dict:
        return self.kb.capa_actions

    def _is_time_accepted(self, room: str, sensed_time: time) -> bool:
        windows = self.kb.layouts.get("room_time_windows", {}).get(room, [])
        if not windows:
            return True

        for start_raw, end_raw in windows:
            start = datetime.strptime(start_raw, "%H:%M").time()
            end = datetime.strptime(end_raw, "%H:%M").time()
            accepted = (
                start <= sensed_time <= end
                if start <= end
                else sensed_time >= start or sensed_time <= end
            )
            if accepted:
                return True
        return False

    def _generate_risk_assessment(
        self,
        product_name: str,
        room: str,
        room_class: str,
        criticality: str,
        start_deviation: bool,
        reason: str,
        limit_status: str,
        room_controls: dict,
        sensor_meta: dict,
        product_rule: dict,
    ) -> str:
        # Lightweight deterministic response shaped as an LLM prompt output artifact.
        sop_risk = self.kb.sops.get("risk_assessment", "Use site risk SOP")
        sop_dev = self.kb.sops.get("deviation", "Use site deviation SOP")
        sop_alarm = self.kb.sops.get("alarm_handling", "Use site alarm SOP")
        sop_capa = self.kb.sops.get("capa", "Use site CAPA SOP")
        gamp5_note = "GAMP5-aligned: risk-based assessment with documented traceability to URS."

        status = "Deviation to be initiated." if start_deviation else "No deviation initiation needed."
        limits = sensor_meta.get("limits", {})
        pressure = room_controls.get("differential_pressure_pa", {})
        product_factors = ", ".join(product_rule.get("risk_factors", [])) or "Not specified"
        return (
            f"{gamp5_note}\n"
            f"Product: {product_name} | Room: {room} ({room_class}) | Criticality: {criticality}\n"
            f"Decision: {status}\n"
            f"Rationale: {reason}\n"
            f"Sensor limits: {limits.get('min', 'N/A')} to {limits.get('max', 'N/A')}\n"
            f"Room differential pressure requirement: {pressure.get('min', 'N/A')} to {pressure.get('max', 'N/A')} Pa\n"
            f"Door-open maximum: {room_controls.get('door_open_max_seconds', 'N/A')} seconds; "
            f"interlock required: {room_controls.get('door_interlock_required', 'N/A')}\n"
            f"Product risk factors: {product_factors}\n"
            f"Applicable SOPs: {sop_dev}; {sop_risk}; {sop_alarm}; {sop_capa}.\n"
            "GMP reference: Use the current approved site interpretation of applicable GMP guidance; "
            "the values above are controlled site configuration, not universal regulatory limits."
        )
