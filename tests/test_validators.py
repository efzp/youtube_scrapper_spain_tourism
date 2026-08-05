from copy import deepcopy
from datetime import timezone

import pytest

from src.catalog.validators import CatalogValidationError, build_search_tasks, validate_catalog


def test_filters_inactive_rows_and_normalizes_real_columns(active_row: dict[str, object]) -> None:
    inactive = deepcopy(active_row)
    inactive["place_id"] = "ES-002"
    inactive["activo"] = 0

    places = validate_catalog([inactive, active_row])

    assert [place.place_id for place in places] == ["ES-001"]
    assert len(places[0].queries) == 2
    assert places[0].published_after is not None
    assert places[0].published_after.tzinfo == timezone.utc


def test_rejects_missing_required_field(active_row: dict[str, object]) -> None:
    active_row["municipio"] = ""
    with pytest.raises(CatalogValidationError, match="municipio"):
        validate_catalog([active_row])


def test_rejects_missing_required_column(active_row: dict[str, object]) -> None:
    del active_row["provincia"]
    with pytest.raises(CatalogValidationError, match="provincia"):
        validate_catalog([active_row])


def test_rejects_empty_queries(active_row: dict[str, object]) -> None:
    for key in list(active_row):
        if key.startswith("consulta_"):
            active_row[key] = " "
    with pytest.raises(CatalogValidationError, match="no contiene consultas"):
        validate_catalog([active_row])


def test_limits_queries_per_place(active_row: dict[str, object]) -> None:
    place = validate_catalog([active_row])[0]
    tasks = build_search_tasks([place], max_queries_per_place=1)
    assert len(tasks) == 1
    assert tasks[0].query == '"Sevilla" turismo'

