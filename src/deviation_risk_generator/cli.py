from __future__ import annotations

import argparse
import json

from .engine import DeviationRiskEngine
from .knowledge_base import load_knowledge_base


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deviation/risk assessment from KB and production inputs")
    parser.add_argument("--kb", required=True, help="Path to KB JSON (SOPs/layouts/products)")
    parser.add_argument("--plan", required=True, help="Path to daily production XLSX")
    parser.add_argument("--sensor", required=True, help="BMS sensor number")
    parser.add_argument("--trend-image", required=True, help="Trend image path including YYYYMMDD_HHMM")
    parser.add_argument("--product", required=True, help="Product name from production plan")
    parser.add_argument("--qa-email", default="qa@company.com", help="QA email for Gmail draft payload")
    args = parser.parse_args()

    kb = load_knowledge_base(args.kb)
    engine = DeviationRiskEngine(kb, qa_email=args.qa_email)
    decision = engine.evaluate(
        sensor_number=args.sensor,
        trend_image_path=args.trend_image,
        product_name=args.product,
        production_plan_xlsx=args.plan,
    )

    print(json.dumps(decision.__dict__, indent=2))


if __name__ == "__main__":
    main()
