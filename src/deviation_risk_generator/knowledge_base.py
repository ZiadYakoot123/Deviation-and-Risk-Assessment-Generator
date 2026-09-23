from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class KnowledgeBase:
    sops: dict
    layouts: dict
    products: dict


def load_knowledge_base(path: str | Path) -> KnowledgeBase:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return KnowledgeBase(
        sops=data.get("sops", {}),
        layouts=data.get("layouts", {}),
        products=data.get("products", {}),
    )
