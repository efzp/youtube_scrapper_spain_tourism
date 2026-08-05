"""Fixtures compartidos sin acceso a la red."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.models import PlaceRecord


@pytest.fixture
def place() -> PlaceRecord:
    """Municipio minimo para pruebas de servicios."""
    return PlaceRecord(
        place_id="ES-TEST",
        municipio="Sevilla",
        provincia="Sevilla",
        comunidad_autonoma="Andalucia",
        queries=('"Sevilla" turismo',),
        published_after=datetime(2023, 1, 1, tzinfo=timezone.utc),
        max_results_per_query=25,
    )


@pytest.fixture
def active_row() -> dict[str, object]:
    """Fila con los nombres de columna reales del catalogo."""
    return {
        "place_id": "ES-001",
        "municipio": "Sevilla",
        "provincia": "Sevilla",
        "comunidad_autonoma": "Andalucia",
        "consulta_es_turismo": '"Sevilla" turismo',
        "consulta_en_review": '"Sevilla Spain" travel review',
        "region_code": "ES",
        "relevance_language": "es",
        "fecha_desde": datetime(2023, 1, 1),
        "max_resultados_consulta": 25,
        "orden_busqueda": "relevance",
        "activo": 1,
        "prioridad": 1,
        "lote_carga": 1,
    }

