from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl.worksheet.table import Table

from src.catalog.excel_reader import CatalogReadError, read_excel_table


def _workbook(path: Path, *, table_name: str = "tbl_lugares") -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Nombre variable"
    sheet.append(["place_id", "municipio", "activo"])
    sheet.append(["ES-001", "Sevilla", 1])
    sheet.add_table(Table(displayName=table_name, ref="A1:C2"))
    workbook.save(path)


def test_reads_named_table_without_relying_on_sheet_name(tmp_path: Path) -> None:
    path = tmp_path / "catalog.xlsx"
    _workbook(path)

    assert read_excel_table(path) == [
        {"place_id": "ES-001", "municipio": "Sevilla", "activo": 1}
    ]


def test_rejects_missing_table(tmp_path: Path) -> None:
    path = tmp_path / "catalog.xlsx"
    _workbook(path, table_name="otra_tabla")

    with pytest.raises(CatalogReadError, match="tbl_lugares"):
        read_excel_table(path)


def test_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CatalogReadError, match="No existe"):
        read_excel_table(tmp_path / "missing.xlsx")

