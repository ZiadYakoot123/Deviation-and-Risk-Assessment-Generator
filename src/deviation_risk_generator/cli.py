from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import DeviationRiskEngine
from .knowledge_base import load_knowledge_base


EXAMPLE_KB = Path(__file__).resolve().parents[2] / "examples" / "kb.json"
EXAMPLE_PLAN = Path(__file__).resolve().parents[2] / "examples" / "production_plan.csv"


def _prompt_for_value(prompt: str, default: str | None = None) -> str:
    response = input(f"{prompt}{' [' + default + ']' if default else ''}: ").strip()
    if not response and default:
        return default
    if not response:
        raise ValueError(f"{prompt} is required.")
    return response


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deviation/risk assessment from KB and production inputs")
    parser.add_argument("--kb", default=str(EXAMPLE_KB), help="Path to KB JSON (SOPs/layouts/products). Defaults to bundled example KB.")
    parser.add_argument("--plan", default=str(EXAMPLE_PLAN), help="Path to daily production XLSX/CSV. Defaults to bundled example plan.")
    parser.add_argument("--sensor", help="BMS sensor number. If omitted, you will be prompted.")
    parser.add_argument("--trend-image", help="Trend image path including YYYYMMDD_HHMM. If omitted, you will be prompted.")
    parser.add_argument("--product", default="Product-A", help="Product name from production plan. Defaults to the bundled sample product.")
    parser.add_argument("--qa-email", default="qa@company.com", help="QA email for Gmail draft payload")
    args = parser.parse_args()

    sensor_number = args.sensor or _prompt_for_value("Enter BMS sensor number")
    trend_image = args.trend_image or _prompt_for_value("Enter trend image path or filename", "trend_20260923_1330.png")

    kb = load_knowledge_base(args.kb)
    engine = DeviationRiskEngine(kb, qa_email=args.qa_email)
    decision = engine.evaluate(
        sensor_number=sensor_number,
        trend_image_path=trend_image,
        product_name=args.product,
        production_plan_xlsx=args.plan,
    )

    print(json.dumps(decision.__dict__, indent=2))


if __name__ == "__main__":
    main()
