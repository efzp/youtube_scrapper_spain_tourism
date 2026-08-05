"""Modelos de datos internos del pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class PlaceRecord:
    """Municipio activo y su configuracion de busqueda."""

    place_id: str
    municipio: str
    provincia: str
    comunidad_autonoma: str
    queries: tuple[str, ...]
    region_code: str = "ES"
    relevance_language: str = "es"
    published_after: datetime | None = None
    max_results_per_query: int = 25
    search_order: str = "relevance"
    priority: int = 999
    batch: str | None = None


@dataclass(frozen=True, slots=True)
class SearchTask:
    """Una consulta reproducible asociada con un municipio."""

    place: PlaceRecord
    query: str


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Relacion entre ejecucion, municipio, consulta y video."""

    run_id: str
    place_id: str
    municipio: str
    provincia: str
    comunidad_autonoma: str
    video_id: str
    search_query: str
    search_order: str
    search_position: int
    region_code: str
    relevance_language: str
    published_after: str | None
    retrieved_at: str
    youtube_kind: str | None = None
    youtube_etag: str | None = None
    page_number: int | None = None


@dataclass(slots=True)
class RunSummary:
    """Metricas y estado auditable de una ejecucion."""

    run_id: str
    started_at: str
    finished_at: str | None = None
    places_processed: int = 0
    queries_executed: int = 0
    search_list_calls_estimated: int = 0
    search_list_calls: int = 0
    search_quota_units_estimated: int = 0
    videos_list_calls: int = 0
    videos_quota_units_estimated: int = 0
    total_quota_units_estimated: int = 0
    raw_results: int = 0
    unique_videos: int = 0
    videos_retrieved: int = 0
    failed_records: int = 0
    status: str = "PENDING"
    error_messages: list[str] = field(default_factory=list)

    def finish(self, *, at: str, status: str) -> None:
        """Cierra la ejecucion y calcula el consumo estimado."""
        self.finished_at = at
        self.status = status
        self.search_quota_units_estimated = self.search_list_calls
        self.videos_quota_units_estimated = self.videos_list_calls
        self.total_quota_units_estimated = (
            self.search_quota_units_estimated + self.videos_quota_units_estimated
        )

    def to_dict(self) -> dict[str, Any]:
        """Convierte el resumen a una estructura serializable."""
        return asdict(self)
