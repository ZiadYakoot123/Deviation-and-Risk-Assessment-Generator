from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import re

from .gmail import build_gmail_draft_payload
from .knowledge_base import KnowledgeBase
from .production_plan import load_planned_batches
from .trend import extract_trend_time


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


@dataclass(frozen=True)
class DeviationDecision:
    start_deviation: bool
    reason: str
    room: str
    room_class: str
    criticality: str
    risk_assessment: str
    deviation_summary: str
    qa_mail_draft: dict


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
    ) -> DeviationDecision:
        trend_time = extract_trend_time(trend_image_path)
        sensor_meta = self._get_sensor_meta(sensor_number)
        room = sensor_meta["location"]
        room_class = sensor_meta["room_class"]

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

        if not production_active:
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
        )
        subject = f"Deviation Assessment - {product_name} - {criticality}"
        body = f"Deviation summary:\n{deviation_summary}\n\nRisk assessment:\n{risk_assessment}"

        return DeviationDecision(
            start_deviation=start_deviation,
            reason=reason,
            room=room,
            room_class=room_class,
            criticality=criticality,
            risk_assessment=risk_assessment,
            deviation_summary=deviation_summary,
            qa_mail_draft=build_gmail_draft_payload(self.qa_email, subject, body),
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

    def _is_time_accepted(self, room: str, sensed_time: time) -> bool:
        windows = self.kb.layouts.get("room_time_windows", {}).get(room, [])
        if not windows:
            return True

        for start_raw, end_raw in windows:
            start = datetime.strptime(start_raw, "%H:%M").time()
            end = datetime.strptime(end_raw, "%H:%M").time()
            if start <= sensed_time <= end:
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
    ) -> str:
        # Lightweight deterministic response shaped as an LLM prompt output artifact.
        sop_risk = self.kb.sops.get("risk_assessment", "Use site risk SOP")
        sop_dev = self.kb.sops.get("deviation", "Use site deviation SOP")
        gamp5_note = "GAMP5-aligned: risk-based assessment with documented traceability to URS."

        status = "Deviation to be initiated." if start_deviation else "No deviation initiation needed."
        return (
            f"{gamp5_note}\n"
            f"Product: {product_name} | Room: {room} ({room_class}) | Criticality: {criticality}\n"
            f"Decision: {status}\n"
            f"Rationale: {reason}\n"
            f"Applicable SOPs: {sop_dev}; {sop_risk}."
        )
