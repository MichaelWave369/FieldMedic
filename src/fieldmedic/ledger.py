from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable
from .models import EvidenceEnvelope


class EvidenceLedger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, item: EvidenceEnvelope) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(item.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")

    def append_many(self, items: Iterable[EvidenceEnvelope]) -> None:
        for item in items:
            self.append(item)
