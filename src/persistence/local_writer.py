"""Persistencia local segura en Parquet, JSON y CSV opcional."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import pandas as pd


class LocalWriter:
    """Escribe primero un temporal y lo reemplaza de forma atomica."""

    def __init__(self, output_dir: Path, *, write_csv: bool = False) -> None:
        self.output_dir = output_dir
        self.write_csv = write_csv
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, target: Path, operation: Callable[[Path], None]) -> None:
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            operation(temporary)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def write_table(
        self, name: str, records: list[dict[str, Any]], columns: list[str]
    ) -> None:
        """Escribe Parquet y, si se solicita, una copia CSV inspeccionable."""
        frame = pd.DataFrame.from_records(records, columns=columns)
        parquet_path = self.output_dir / f"{name}.parquet"
        self._atomic_write(
            parquet_path,
            lambda path: frame.to_parquet(path, index=False, engine="pyarrow"),
        )
        if self.write_csv:
            csv_frame = frame.map(
                lambda value: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (list, dict, tuple))
                else value
            )
            self._atomic_write(
                self.output_dir / f"{name}.csv",
                lambda path: csv_frame.to_csv(path, index=False, encoding="utf-8-sig"),
            )

    def write_json(self, name: str, payload: dict[str, Any]) -> None:
        """Escribe un resumen JSON legible y en UTF-8."""
        target = self.output_dir / f"{name}.json"
        self._atomic_write(
            target,
            lambda path: path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            ),
        )

