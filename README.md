# Deviation-and-Risk-Assessment-Generator

Simple Python project for pharmaceutical deviation decision support aligned with **GAMP5** and **URS** expectations.

## What it does

- Loads a local knowledge base (SOPs, room layouts/sensors, product criticality) as a lightweight RAG source.
- Loads daily production plan from **XLSX**.
- Accepts manual BMS sensor number and trend image path.
- Extracts trend timestamp from image filename (`YYYYMMDD_HHMM`) and maps sensor -> room via KB.
- Checks if sensed time is inside accepted room time windows.
- Starts deviation process only when production is active and time is outside accepted window.
- Produces deviation summary, risk assessment text, and Gmail API draft payload for QA.

## Install

```bash
pip install -e .[dev]
```

## How to Use

1. Create a knowledge-base JSON file that includes:
   - `sops` (deviation and risk assessment SOP references)
   - `layouts.sensors` (BMS sensor number to room mapping)
   - `layouts.room_time_windows` (accepted room time windows)
   - `products` (product criticality)
2. Prepare the daily production plan as an XLSX file with these headers in row 1:
   - `date`
   - `product`
   - `room_class`
3. Provide the BMS sensor number manually (for example `BMS-101`).
4. Use a trend image filename that contains timestamp in `YYYYMMDD_HHMM` format
   (example: `trend_20260923_1330.png`).
5. Run the CLI command:

```bash
deviation-risk-generator \
  --kb /absolute/path/to/kb.json \
  --plan /absolute/path/to/production_plan.xlsx \
  --sensor BMS-101 \
  --trend-image /absolute/path/to/trend_20260923_1330.png \
  --product Product-A \
  --qa-email qa@company.com
```

6. Review JSON output:
   - `start_deviation` indicates whether deviation process should start.
   - `risk_assessment` contains the generated GAMP5/URS-style assessment.
   - `qa_mail_draft` contains Gmail API draft payload.

## Run

```bash
deviation-risk-generator \
  --kb /absolute/path/to/kb.json \
  --plan /absolute/path/to/production_plan.xlsx \
  --sensor BMS-101 \
  --trend-image /absolute/path/to/trend_20260923_1330.png \
  --product Product-A \
  --qa-email qa@company.com
```

## Knowledge-base JSON example

```json
{
  "sops": {
    "risk_assessment": "QMS-SOP-RA-001",
    "deviation": "QMS-SOP-DEV-003"
  },
  "layouts": {
    "sensors": {
      "BMS-101": {"location": "Granulation-01", "room_class": "C"}
    },
    "room_time_windows": {
      "Granulation-01": [["08:00", "12:00"]]
    }
  },
  "products": {
    "Product-A": {"criticality": "High"}
  }
}
```

## Test

```bash
pytest
```
