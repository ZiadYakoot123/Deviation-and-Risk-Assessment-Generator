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
- Captures new BMS alarm rows from a MySQL binlog and routes them through the same assessment engine.

## Connected workflow

```text
MySQL binlog (alarms INSERT)
  -> CDC listener
  -> ALCOA+ input validation and normalization
  -> knowledge base sensor/product/SOP lookup
  -> production plan and room-window decision
  -> traceable deviation/risk assessment
  -> Gmail-compatible QA draft payload
  -> timestamped audit log
```

The implementation provides software controls supporting a GAMP5 Category 5
workflow: controlled configuration, input validation, exception logging,
assessment traceability, deterministic decision logic, and retained output
payloads. Site validation, approved SOPs, access control, MySQL binlog
configuration, qualification, and QA approval remain deployment
responsibilities and are not replaced by this sample software.

## Install

```bash
pip install -e .[dev]
```

## How to Use

1. Create a knowledge-base JSON file that includes:
   - `sops` (alarm handling, deviation, risk assessment, CAPA, and controlled GMP references)
   - `layouts.sensors` (location, room class, parameter, unit, approved limits, and alarm actions)
   - `layouts.room_classes` (differential-pressure range, door-open maximum, interlock requirement, and control note)
   - `layouts.room_time_windows` (accepted room time windows)
   - `products` (criticality, risk factors, and CAPA focus)
   - `capa_actions` (immediate, corrective, and preventive action templates)
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

## Run the MySQL CDC listener

Install the package, then provide the database credentials through environment
variables (credentials are never stored in the repository):

```bash
export BMS_DB_HOST=127.0.0.1
export BMS_DB_PORT=3306
export BMS_DB_USER=bms_cdc
export BMS_DB_PASS='your-password'
export BMS_DB_NAME=bms_database
export BMS_DB_TABLE=alarms

bms-cdc-listener \
  --kb /absolute/path/to/kb.json \
  --plan /absolute/path/to/production_plan.xlsx \
  --product Product-A \
  --qa-email qa@company.com
```

The `alarms` table must contain `sensor_number`, `time`, `value`, and `trend`
columns. Each inserted row is validated, assessed using the configured
knowledge base and production plan, and audit-logged. The resulting
`DeviationDecision` contains the existing Gmail draft payload for downstream
delivery.

For MySQL CDC, enable row-based binary logging and grant the listener a
replication client/user with access to the configured database. Use a unique
`BMS_CDC_SERVER_ID` for each active listener instance.

### Create a test MySQL alarm

The ready-to-run schema and sample alarm are in
[examples/mysql_alarms.sql](examples/mysql_alarms.sql). Execute it with a
MySQL account that can create the database and table:

```bash
mysql -u root -p < examples/mysql_alarms.sql
```

The sample insert creates an alarm for `BMS-101` at
`2026-09-23 13:30:00`, with value `24.5` and trend `high`. Start
`bms-cdc-listener` before running the script if you want to observe the row
being captured.

### Run one alarm without MySQL

For a simple local test, use `bms-local-alarm`. It creates the same
MySQL-shaped row in memory and sends it through validation, assessment, and
Gmail draft generation without connecting to a server:

```bash
bms-local-alarm \
  --kb examples/kb.json \
  --plan examples/production_plan.csv \
  --product Product-A \
  --sensor BMS-101 \
  --time 2026-09-23T13:30:00 \
  --value 24.5 \
  --trend high
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

The bundled [examples/kb.json](examples/kb.json) contains the extended
structure, including example temperature, humidity, differential-pressure,
and door-open sensors. Limits and GMP control values are illustrative
site-controlled configuration: QA must approve and replace them with current
qualified values and applicable local GMP requirements before production use.

## Test

```bash
pytest
```
