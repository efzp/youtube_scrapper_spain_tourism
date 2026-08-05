"""Normalizacion y validacion de registros del catalogo."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Iterable

from src.models import PlaceRecord, SearchTask

QUERY_COLUMNS = (
    "consulta_es_turismo",
    "consulta_es_opiniones",
    "consulta_en_review",
    "consulta_en_que_hacer",
    "consulta_1",
    "consulta_2",
    "consulta_3",
    "consulta_4",
)
REQUIRED_COLUMNS = ("place_id", "municipio", "provincia", "comunidad_autonoma", "activo")


class CatalogValidationError(ValueError):
    """Agrupa errores encontrados en filas activas del catalogo."""


def _is_active(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value).strip().lower() in {"1", "true", "si", "sí", "yes"}


def _required_text(row: dict[str, Any], field: str, row_number: int) -> str:
    value = row.get(field)
    if value is None or not str(value).strip():
        raise CatalogValidationError(f"Fila {row_number}: falta {field}.")
    return str(value).strip()


def _published_after(value: Any, row_number: int) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise CatalogValidationError(
                f"Fila {row_number}: fecha_desde no es una fecha ISO valida."
            ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_catalog(rows: Iterable[dict[str, Any]]) -> list[PlaceRecord]:
    """Filtra filas activas, valida campos y devuelve municipios normalizados."""
    records: list[PlaceRecord] = []
    errors: list[str] = []
    for row_number, row in enumerate(rows, start=2):
        if not _is_active(row.get("activo")):
            continue
        try:
            missing_columns = [column for column in REQUIRED_COLUMNS if column not in row]
            if missing_columns:
                raise CatalogValidationError(
                    f"Fila {row_number}: faltan columnas {', '.join(missing_columns)}."
                )
            queries = tuple(
                dict.fromkeys(
                    str(row[column]).strip()
                    for column in QUERY_COLUMNS
                    if row.get(column) is not None and str(row[column]).strip()
                )
            )
            if not queries:
                raise CatalogValidationError(f"Fila {row_number}: no contiene consultas.")
            max_results_raw = row.get("max_resultados_consulta", row.get("max_videos", 25))
            max_results = int(max_results_raw or 25)
            if not 1 <= max_results <= 500:
                raise CatalogValidationError(
                    f"Fila {row_number}: max_resultados_consulta debe estar entre 1 y 500."
                )
            records.append(
                PlaceRecord(
                    place_id=_required_text(row, "place_id", row_number),
                    municipio=_required_text(row, "municipio", row_number),
                    provincia=_required_text(row, "provincia", row_number),
                    comunidad_autonoma=_required_text(
                        row, "comunidad_autonoma", row_number
                    ),
                    queries=queries,
                    region_code=str(row.get("region_code") or "ES").strip().upper(),
                    relevance_language=str(
                        row.get("relevance_language", row.get("idioma", "es")) or "es"
                    ).strip(),
                    published_after=_published_after(row.get("fecha_desde"), row_number),
                    max_results_per_query=max_results,
                    search_order=str(
                        row.get("orden_busqueda", row.get("search_order", "relevance"))
                        or "relevance"
                    ).strip(),
                    priority=int(row.get("prioridad") or 999),
                    batch=(
                        str(row.get("lote_carga", row.get("lote"))).strip()
                        if row.get("lote_carga", row.get("lote")) is not None
                        else None
                    ),
                )
            )
        except (CatalogValidationError, TypeError, ValueError) as exc:
            errors.append(str(exc))
    if errors:
        raise CatalogValidationError("Catalogo invalido:\n- " + "\n- ".join(errors))
    return sorted(records, key=lambda item: (item.priority, item.place_id))


def build_search_tasks(
    places: Iterable[PlaceRecord], max_queries_per_place: int | None = None
) -> list[SearchTask]:
    """Expande municipios en tareas y permite limitar consultas en pruebas."""
    tasks: list[SearchTask] = []
    for place in places:
        queries = place.queries[:max_queries_per_place]
        tasks.extend(SearchTask(place=place, query=query) for query in queries)
    return tasks

