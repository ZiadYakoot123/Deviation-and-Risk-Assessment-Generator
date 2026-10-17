from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Callable, Iterator

from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.row_event import WriteRowsEvent

from .engine import DeviationRiskEngine


logger = logging.getLogger(__name__)


class CDCConfigurationError(ValueError):
    """Raised when required CDC connection configuration is missing or invalid."""


@dataclass(frozen=True)
class CDCConfig:
    host: str
    port: int
    user: str
    password: str
    database: str = "bms_database"
    table: str = "alarms"
    server_id: int = 100

    @classmethod
    def from_env(cls) -> CDCConfig:
        user = os.getenv("BMS_DB_USER")
        password = os.getenv("BMS_DB_PASS")
        if not user or not password:
            raise CDCConfigurationError(
                "BMS_DB_USER and BMS_DB_PASS environment variables are required"
            )

        try:
            port = int(os.getenv("BMS_DB_PORT", "3306"))
            server_id = int(os.getenv("BMS_CDC_SERVER_ID", "100"))
        except ValueError as exc:
            raise CDCConfigurationError("BMS_DB_PORT and BMS_CDC_SERVER_ID must be integers") from exc

        return cls(
            host=os.getenv("BMS_DB_HOST", "127.0.0.1"),
            port=port,
            user=user,
            password=password,
            database=os.getenv("BMS_DB_NAME", "bms_database"),
            table=os.getenv("BMS_DB_TABLE", "alarms"),
            server_id=server_id,
        )

    def connection_settings(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "passwd": self.password,
        }


def configure_logging(log_path: str = "bms_cdc_audit.log") -> None:
    """Configure timestamped audit output for the CDC process."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | User: SYSTEM | %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )


def validate_alarm_data(event_data: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the alarm columns used by the assessment engine."""
    required_fields = ("sensor_number", "time", "value", "trend")
    for field in required_fields:
        if field not in event_data or event_data[field] is None:
            raise ValueError(f"Data Integrity Failure: Missing critical field '{field}'")

    try:
        if isinstance(event_data["time"], datetime):
            timestamp = event_data["time"].isoformat()
        else:
            timestamp = datetime.fromisoformat(str(event_data["time"])).isoformat()
        trend = str(event_data["trend"]).strip()
        if not trend:
            raise ValueError("trend must not be empty")
        value = float(event_data["value"])
        if not isfinite(value):
            raise ValueError("value must be finite")
        return {
            "sensor_number": str(event_data["sensor_number"]),
            "timestamp": timestamp,
            "value": value,
            "trend": trend,
        }
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Data Integrity Failure: Invalid data format - {exc}") from exc


def _trend_path(alarm_data: dict[str, Any]) -> str:
    trend = alarm_data["trend"]
    if trend and ("/" in trend or "\\" in trend or "." in trend):
        return trend
    timestamp = datetime.fromisoformat(alarm_data["timestamp"]).strftime("%Y%m%d_%H%M")
    return f"trend_{timestamp}.png"


def build_ai_agent_handler(
    engine: DeviationRiskEngine,
    product_name: str,
    production_plan: str,
) -> Callable[[dict[str, Any]], Any]:
    """Create the CDC callback that sends an alarm to the assessment engine."""

    def handle_alarm(alarm_data: dict[str, Any]) -> Any:
        decision = engine.evaluate(
            sensor_number=alarm_data["sensor_number"],
            trend_image_path=_trend_path(alarm_data),
            product_name=product_name,
            production_plan_xlsx=production_plan,
            alarm_value=alarm_data["value"],
            alarm_trend=alarm_data["trend"],
        )
        logger.info(
            "AI assessment completed | Assessment: %s | Sensor: %s | Start deviation: %s",
            decision.assessment_id,
            alarm_data["sensor_number"],
            decision.start_deviation,
        )
        return decision

    return handle_alarm


class MySQLCDCListener:
    """Capture alarm INSERTs from MySQL binlogs and forward them to an AI callback."""

    def __init__(
        self,
        config: CDCConfig,
        on_alarm: Callable[[dict[str, Any]], Any],
        stream_factory: Callable[..., Iterator[Any]] = BinLogStreamReader,
    ) -> None:
        self.config = config
        self.on_alarm = on_alarm
        self.stream_factory = stream_factory

    def run(self) -> None:
        stream = None
        try:
            stream = self.stream_factory(
                connection_settings=self.config.connection_settings(),
                server_id=self.config.server_id,
                blocking=True,
                resume_stream=True,
                only_events=[WriteRowsEvent],
                only_tables=[self.config.table],
                only_schemas=[self.config.database],
            )
            logger.info("CDC stream connected successfully. Listening for alarm events.")

            for binlog_event in stream:
                for row in binlog_event.rows:
                    event_data = row["values"]
                    try:
                        validated_alarm = validate_alarm_data(event_data)
                        self.on_alarm(validated_alarm)
                    except ValueError as exc:
                        logger.error("%s | Raw payload: %s", exc, event_data)
                    except Exception:
                        logger.exception("Unexpected alarm processing error | Raw payload: %s", event_data)
        except KeyboardInterrupt:
            logger.info("System shutdown initiated by operator.")
        except Exception:
            logger.exception("Fatal CDC system error")
            raise
        finally:
            if stream is not None:
                stream.close()
                logger.info("CDC stream disconnected securely.")


def main() -> None:
    import argparse
    from .knowledge_base import load_knowledge_base

    parser = argparse.ArgumentParser(description="Capture BMS alarms from MySQL binlogs")
    parser.add_argument("--kb", required=True, help="Path to the knowledge-base JSON")
    parser.add_argument("--plan", required=True, help="Path to the production plan XLSX/CSV")
    parser.add_argument("--product", required=True, help="Product name for the AI assessment")
    parser.add_argument("--qa-email", default="qa@company.com")
    parser.add_argument("--log-file", default="bms_cdc_audit.log")
    args = parser.parse_args()

    configure_logging(args.log_file)
    config = CDCConfig.from_env()
    engine = DeviationRiskEngine(load_knowledge_base(args.kb), qa_email=args.qa_email)
    listener = MySQLCDCListener(
        config,
        build_ai_agent_handler(engine, args.product, args.plan),
    )
    listener.run()
