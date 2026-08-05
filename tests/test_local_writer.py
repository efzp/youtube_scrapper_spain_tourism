import json
from pathlib import Path

import pandas as pd

from src.models import RunSummary
from src.persistence.local_writer import LocalWriter


def test_writes_parquet_csv_and_json(tmp_path: Path) -> None:
    writer = LocalWriter(tmp_path, write_csv=True)
    writer.write_table("table", [{"id": "a", "tags": ["x", "y"]}], ["id", "tags"])
    writer.write_json("summary", {"status": "COMPLETED"})

    assert pd.read_parquet(tmp_path / "table.parquet").iloc[0]["id"] == "a"
    assert (tmp_path / "table.csv").is_file()
    assert json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))["status"] == "COMPLETED"
    assert not list(tmp_path.glob("*.tmp"))


def test_run_summary_calculates_estimated_quota() -> None:
    summary = RunSummary("run", "start", search_list_calls=2, videos_list_calls=3)
    summary.finish(at="end", status="COMPLETED")
    assert summary.search_quota_units_estimated == 2
    assert summary.videos_quota_units_estimated == 3
    assert summary.total_quota_units_estimated == 5
