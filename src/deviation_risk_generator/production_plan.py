from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from openpyxl import load_workbook


@dataclass(frozen=True)
class PlannedBatch:
    date: date
    product: str
    room_class: str


def load_planned_batches(xlsx_path: str | Path) -> list[PlannedBatch]:
    workbook = load_workbook(filename=str(xlsx_path), data_only=True)
    sheet = workbook.active
    headers = [str(c.value).strip().lower() if c.value else "" for c in sheet[1]]

    required = {"date", "product", "room_class"}
    if not required.issubset(set(headers)):
        raise ValueError("Production plan must include headers: date, product, room_class")

    idx = {name: headers.index(name) for name in required}
    batches: list[PlannedBatch] = []

    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not any(row):
            continue
        raw_date = row[idx["date"]]
        if hasattr(raw_date, "date"):
            batch_date = raw_date.date()
        else:
            batch_date = date.fromisoformat(str(raw_date))

        batches.append(
            PlannedBatch(
                date=batch_date,
                product=str(row[idx["product"]]).strip(),
                room_class=str(row[idx["room_class"]]).strip(),
            )
        )

    return batches
