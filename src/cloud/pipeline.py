"""Orquestacion asincorna de YouTube hacia Azure SQL."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from src.cloud.contracts import JobEnvelope
from src.models import PlaceRecord, SearchResult, SearchTask
from src.youtube.client import YouTubeClient, YouTubeRequestError
from src.youtube.comment_service import fetch_video_comments
from src.youtube.raw_video_service import fetch_videos_raw
from src.youtube.search_service import search_task, unique_video_ids


@dataclass(frozen=True, slots=True)
class RunErrorRecord:
    stage: str
    message: str
    entity_id: str | None = None
    query_text: str | None = None
    http_status: int | None = None
    error_code: str | None = None


@dataclass(slots=True)
class RawRunData:
    query_results: dict[str, list[SearchResult]] = field(default_factory=dict)
    videos: list[dict[str, object]] = field(default_factory=list)
    statistics: list[dict[str, object]] = field(default_factory=list)
    comments: list[dict[str, object]] = field(default_factory=list)
    errors: list[RunErrorRecord] = field(default_factory=list)


class CloudRunWriter(Protocol):
    def begin_run(self, envelope: JobEnvelope) -> bool:
        """Registra RUNNING y devuelve False cuando el trabajo ya termino."""
        ...

    def save_run(self, envelope: JobEnvelope, data: RawRunData, status: str) -> None:
        """Persiste atomically los datos crudos y el estado final."""
        ...


class CloudPipeline:
    """Ejecuta un municipio; cada consulta y video es recuperable por separado."""

    def __init__(self, client: YouTubeClient, writer: CloudRunWriter) -> None:
        self.client = client
        self.writer = writer

    def run(
        self,
        envelope: JobEnvelope,
        *,
        now: datetime | None = None,
    ) -> str:
        if not self.writer.begin_run(envelope):
            return "SKIPPED"
        job = envelope.job
        observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        place = PlaceRecord(
            place_id=job.place_id,
            municipio=job.municipio,
            provincia=job.provincia,
            comunidad_autonoma=job.comunidad_autonoma,
            queries=job.query_texts,
            region_code="ES",
            relevance_language="en",
            published_after=job.published_after,
            max_results_per_query=job.max_results_per_query,
            search_order=job.search_order,
        )
        data = RawRunData()
        successful_queries = 0
        for query_spec in job.queries:
            query = query_spec.query_text
            data.query_results[query] = []
            try:
                outcome = search_task(
                    self.client,
                    SearchTask(place, query),
                    envelope.run_id,
                    now=observed_at,
                )
                data.query_results[query] = outcome.results
                successful_queries += 1
            except YouTubeRequestError as exc:
                data.errors.append(
                    RunErrorRecord(
                        stage="search",
                        message=str(exc),
                        query_text=query,
                        http_status=exc.status_code,
                        error_code=exc.reason,
                    )
                )
                if exc.status_code in {400, 401, 403}:
                    break

        results = [
            result
            for query_results in data.query_results.values()
            for result in query_results
        ]
        video_ids = unique_video_ids(results)
        if video_ids:
            try:
                video_outcome = fetch_videos_raw(self.client, video_ids, now=observed_at)
                data.videos = video_outcome.videos
                data.statistics = video_outcome.statistics
                for missing_id in video_outcome.missing_video_ids:
                    data.errors.append(
                        RunErrorRecord(
                            stage="videos",
                            entity_id=missing_id,
                            message="YouTube no devolvio el video solicitado.",
                            error_code="videoNotReturned",
                        )
                    )
            except YouTubeRequestError as exc:
                data.errors.append(
                    RunErrorRecord(
                        stage="videos",
                        message=str(exc),
                        http_status=exc.status_code,
                        error_code=exc.reason,
                    )
                )

        for video in data.videos:
            video_id = video.get("video_id")
            if not isinstance(video_id, str):
                continue
            try:
                comment_outcome = fetch_video_comments(
                    self.client,
                    video_id,
                    max_comments=job.max_comments_per_video,
                    now=observed_at,
                )
                data.comments.extend(comment_outcome.comments)
            except YouTubeRequestError as exc:
                data.errors.append(
                    RunErrorRecord(
                        stage="comments",
                        entity_id=video_id,
                        message=str(exc),
                        http_status=exc.status_code,
                        error_code=exc.reason,
                    )
                )

        if successful_queries == 0:
            status = "FAILED"
        elif data.errors:
            status = "PARTIAL"
        else:
            status = "COMPLETED"
        self.writer.save_run(envelope, data, status)
        return status
