"""Orquestador y linea de comandos del MVP local."""

from __future__ import annotations

import argparse
import logging
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence
from uuid import uuid4

from src.catalog.excel_reader import read_excel_table
from src.catalog.validators import build_search_tasks, validate_catalog
from src.config import ConfigurationError, Settings
from src.models import RunSummary, SearchResult
from src.observability.logging_config import configure_logging
from src.persistence.base_writer import ResultWriter
from src.persistence.local_writer import LocalWriter
from src.youtube.client import YouTubeClient, YouTubeRequestError
from src.youtube.search_service import search_task, unique_video_ids
from src.youtube.transformers import derive_video_metrics
from src.youtube.video_service import fetch_videos

LOGGER = logging.getLogger(__name__)

SEARCH_COLUMNS = [
    "run_id", "place_id", "municipio", "provincia", "comunidad_autonoma",
    "video_id", "search_query", "search_order", "search_position", "region_code",
    "relevance_language", "published_after", "retrieved_at",
]
VIDEO_COLUMNS = [
    "video_id", "video_url", "channel_id", "channel_title", "title", "description",
    "tags", "published_at", "category_id", "default_language",
    "default_audio_language", "duration_iso", "duration_seconds", "definition",
    "dimension", "projection", "caption_available", "licensed_content", "view_count",
    "like_count", "comment_count", "privacy_status", "embeddable",
    "public_stats_viewable", "made_for_kids", "paid_product_placement",
    "contains_synthetic_media", "thumbnail_url", "topic_categories", "recording_date",
    "location_description", "regions_allowed", "regions_blocked", "retrieved_at",
]
DERIVED_COLUMNS = [
    "video_id", "duration_minutes", "age_days", "views_per_day", "like_rate",
    "comment_rate", "engagement_rate", "is_short_candidate", "has_comments",
    "is_recent", "derived_at",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_error(error: Exception, api_key: str) -> str:
    message = str(error)
    return message.replace(api_key, "[REDACTED]") if api_key else message


def _write_outputs(
    writer: ResultWriter,
    search_results: list[SearchResult],
    videos: list[dict[str, object]],
    derived: list[dict[str, object]],
    summary: RunSummary,
) -> None:
    writer.write_table(
        "youtube_search_results",
        [asdict(result) for result in search_results],
        SEARCH_COLUMNS,
    )
    writer.write_table("youtube_video_metadata", videos, VIDEO_COLUMNS)
    writer.write_table("youtube_video_derived", derived, DERIVED_COLUMNS)
    writer.write_json("youtube_run_summary", summary.to_dict())


def run_pipeline(
    settings: Settings,
    *,
    client: YouTubeClient | None = None,
    writer: ResultWriter | None = None,
    now_factory: Callable[[], datetime] = _utc_now,
) -> RunSummary:
    """Ejecuta el pipeline completo; admite cliente y escritor simulados en pruebas."""
    run_id = str(uuid4())
    summary = RunSummary(run_id=run_id, started_at=now_factory().isoformat(), status="RUNNING")
    output_writer = writer or LocalWriter(settings.output_dir, write_csv=settings.write_csv)
    search_results: list[SearchResult] = []
    videos: list[dict[str, object]] = []
    derived: list[dict[str, object]] = []
    LOGGER.info("Ejecucion iniciada", extra={"run_id": run_id, "status": "RUNNING"})

    try:
        rows = read_excel_table(settings.catalog_path)
        places = validate_catalog(rows)[: settings.max_places]
        if not places:
            raise ValueError("El catalogo no contiene municipios activos para procesar.")
        tasks = build_search_tasks(places, settings.max_queries_per_place)
        summary.places_processed = len(places)
        summary.search_list_calls_estimated = sum(
            math.ceil(task.place.max_results_per_query / 50) for task in tasks
        )
        youtube = client or YouTubeClient(settings.api_key)

        for task in tasks:
            try:
                outcome = search_task(youtube, task, run_id, now=now_factory())
                search_results.extend(outcome.results)
                summary.queries_executed += 1
                summary.search_list_calls += outcome.calls
                summary.raw_results += outcome.raw_results
            except Exception as exc:  # cada consulta es una unidad recuperable
                summary.failed_records += 1
                message = _safe_error(exc, settings.api_key)
                summary.error_messages.append(
                    f"Busqueda fallida para {task.place.place_id}: {message}"
                )
                LOGGER.error(
                    "Busqueda fallida: %s",
                    message,
                    extra={"run_id": run_id, "place_id": task.place.place_id, "query": task.query},
                )
                if isinstance(exc, YouTubeRequestError) and exc.status_code in {400, 401, 403}:
                    break

        ids = unique_video_ids(search_results)
        summary.unique_videos = len(ids)
        if ids:
            try:
                video_outcome = fetch_videos(youtube, ids, now=now_factory())
                videos = video_outcome.videos
                summary.videos_list_calls = video_outcome.calls
                summary.videos_retrieved = len(videos)
                summary.failed_records += len(video_outcome.missing_video_ids)
                if video_outcome.missing_video_ids:
                    summary.error_messages.append(
                        f"YouTube no devolvio {len(video_outcome.missing_video_ids)} videos."
                    )
                derived = [
                    derive_video_metrics(video, short_max_seconds=settings.short_max_seconds)
                    for video in videos
                ]
            except Exception as exc:
                summary.failed_records += len(ids)
                message = _safe_error(exc, settings.api_key)
                summary.error_messages.append(f"Descarga de videos fallida: {message}")
                LOGGER.error("Descarga de videos fallida: %s", message, extra={"run_id": run_id})

        if summary.error_messages and summary.queries_executed == 0:
            final_status = "FAILED"
        elif summary.error_messages:
            final_status = "PARTIAL"
        else:
            final_status = "COMPLETED"
        summary.finish(at=now_factory().isoformat(), status=final_status)
        _write_outputs(output_writer, search_results, videos, derived, summary)
    except Exception as exc:
        message = _safe_error(exc, settings.api_key)
        summary.failed_records += 1
        summary.error_messages.append(message)
        summary.finish(at=now_factory().isoformat(), status="FAILED")
        try:
            _write_outputs(output_writer, search_results, videos, derived, summary)
        except Exception as write_error:
            LOGGER.error(
                "No se pudo escribir el resumen fallido: %s",
                _safe_error(write_error, settings.api_key),
                extra={"run_id": run_id},
            )
        LOGGER.error("Ejecucion fallida: %s", message, extra={"run_id": run_id, "status": "FAILED"})
    LOGGER.info(
        "Ejecucion finalizada",
        extra={"run_id": run_id, "status": summary.status},
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    """Construye la interfaz de linea de comandos."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-path", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-places", type=int)
    parser.add_argument("--max-queries-per-place", type=int)
    parser.add_argument("--csv", action="store_true", help="Genera copias CSV adicionales.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada comprobable de la CLI."""
    configure_logging()
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env(
            catalog_path=args.catalog_path,
            output_dir=args.output_dir,
            max_places=args.max_places,
            max_queries_per_place=args.max_queries_per_place,
            write_csv=args.csv,
        )
    except ConfigurationError as exc:
        LOGGER.error("Configuracion invalida: %s", exc)
        return 2
    summary = run_pipeline(settings)
    return 0 if summary.status in {"COMPLETED", "PARTIAL"} else 1


def cli() -> None:
    """Entry point instalado por el paquete."""
    raise SystemExit(main())


if __name__ == "__main__":
    cli()
