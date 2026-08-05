"""Paginacion y trazabilidad de resultados de busqueda."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.models import SearchResult, SearchTask
from src.youtube.client import YouTubeClient


def utc_now() -> datetime:
    """Devuelve la hora UTC timezone-aware."""
    return datetime.now(timezone.utc)


def to_rfc3339(value: datetime | None) -> str | None:
    """Serializa una fecha UTC en el formato aceptado por YouTube."""
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    """Resultados y contadores de una tarea de busqueda."""

    results: list[SearchResult]
    calls: int
    raw_results: int


def search_task(
    client: YouTubeClient,
    task: SearchTask,
    run_id: str,
    *,
    now: datetime | None = None,
) -> SearchOutcome:
    """Recupera hasta el limite configurado y registra la posicion global."""
    retrieved_at = (now or utc_now()).astimezone(timezone.utc).isoformat()
    published_after = to_rfc3339(task.place.published_after)
    results: list[SearchResult] = []
    seen_video_ids: set[str] = set()
    page_token: str | None = None
    page_number = 0
    calls = 0
    raw_results = 0

    while len(results) < task.place.max_results_per_query:
        remaining = task.place.max_results_per_query - len(results)
        parameters: dict[str, object] = {
            "part": "snippet",
            "q": task.query,
            "type": "video",
            "regionCode": task.place.region_code,
            "relevanceLanguage": task.place.relevance_language,
            "safeSearch": "moderate",
            "order": task.place.search_order,
            "maxResults": min(50, remaining),
        }
        if published_after:
            parameters["publishedAfter"] = published_after
        if page_token:
            parameters["pageToken"] = page_token
        response = client.search(**parameters)
        calls += 1
        page_number += 1
        items = response.get("items") or []
        raw_results += len(items)
        for item in items:
            video_id = (item.get("id") or {}).get("videoId")
            if not video_id or video_id in seen_video_ids:
                continue
            seen_video_ids.add(video_id)
            results.append(
                SearchResult(
                    run_id=run_id,
                    place_id=task.place.place_id,
                    municipio=task.place.municipio,
                    provincia=task.place.provincia,
                    comunidad_autonoma=task.place.comunidad_autonoma,
                    video_id=video_id,
                    search_query=task.query,
                    search_order=task.place.search_order,
                    search_position=len(results) + 1,
                    region_code=task.place.region_code,
                    relevance_language=task.place.relevance_language,
                    published_after=published_after,
                    retrieved_at=retrieved_at,
                    youtube_kind=(
                        str(item.get("kind")) if item.get("kind") is not None else None
                    ),
                    youtube_etag=(
                        str(item.get("etag")) if item.get("etag") is not None else None
                    ),
                    page_number=page_number,
                )
            )
            if len(results) >= task.place.max_results_per_query:
                break
        page_token = response.get("nextPageToken")
        if not page_token or not items:
            break
    return SearchOutcome(results=results, calls=calls, raw_results=raw_results)


def unique_video_ids(results: list[SearchResult]) -> list[str]:
    """Deduplica IDs conservando el orden de su primera aparicion."""
    return list(dict.fromkeys(result.video_id for result in results))
