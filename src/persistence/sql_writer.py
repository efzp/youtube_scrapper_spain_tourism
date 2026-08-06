"""Persistencia transaccional de datos crudos en Azure SQL Database."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from src.cloud.contracts import JobEnvelope
from src.cloud.pipeline import RawRunData

ConnectionFactory = Callable[[], Any]


class SqlConfigurationError(RuntimeError):
    """Indica que falta configuracion para conectar a Azure SQL."""


def _default_connection_factory() -> Any:
    connection_string = os.getenv("SQL_CONNECTION_STRING", "").strip()
    if not connection_string:
        raise SqlConfigurationError("Falta la variable SQL_CONNECTION_STRING.")
    import mssql_python

    last_error: Exception | None = None
    for delay in (0, 5, 15, 30):
        if delay:
            time.sleep(delay)
        try:
            return mssql_python.connect(connection_string)
        except Exception as exc:  # la base gratuita puede estar reanudandose
            last_error = exc
    assert last_error is not None
    raise last_error


def _datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _json(value: object) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class SqlRunWriter:
    """Escritor Azure SQL con transacciones cortas e inserciones por lotes."""

    def __init__(self, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connection_factory or _default_connection_factory

    def begin_run(self, envelope: JobEnvelope) -> bool:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT status FROM dbo.pipeline_runs WHERE run_id = ?",
                (envelope.run_id,),
            )
            existing = cursor.fetchone()
            if existing and str(existing[0]) in {"COMPLETED", "PARTIAL"}:
                connection.rollback()
                return False
            job = envelope.job
            cursor.execute(
                """
                MERGE dbo.places WITH (HOLDLOCK) AS target
                USING (SELECT ? AS place_id) AS source
                    ON target.place_id = source.place_id
                WHEN MATCHED THEN UPDATE SET
                    municipio = ?,
                    provincia = ?,
                    comunidad_autonoma = ?,
                    tipologia_principal = ?,
                    updated_at = SYSUTCDATETIME()
                WHEN NOT MATCHED THEN INSERT
                    (place_id, municipio, provincia, comunidad_autonoma, tipologia_principal)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    job.place_id,
                    job.municipio,
                    job.provincia,
                    job.comunidad_autonoma,
                    job.tipologia_principal,
                    job.place_id,
                    job.municipio,
                    job.provincia,
                    job.comunidad_autonoma,
                    job.tipologia_principal,
                ),
            )
            if existing:
                cursor.execute(
                    """
                    UPDATE dbo.pipeline_runs
                    SET flow_run_id = ?, status = 'RUNNING',
                        started_at = SYSUTCDATETIME(), completed_at = NULL
                    WHERE run_id = ?
                    """,
                    (job.flow_run_id, envelope.run_id),
                )
            else:
                cursor.execute(
                    """
                    INSERT dbo.pipeline_runs
                        (run_id, flow_run_id, status, requested_at, started_at)
                    VALUES (?, ?, 'RUNNING', ?, SYSUTCDATETIME())
                    """,
                    (envelope.run_id, job.flow_run_id, envelope.enqueued_at),
                )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_run(self, envelope: JobEnvelope, data: RawRunData, status: str) -> None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            run_id = envelope.run_id
            for table in (
                "dbo.run_errors",
                "dbo.video_statistics_raw",
                "dbo.video_comments_raw",
                "dbo.search_results_raw",
                "dbo.videos_raw",
                "dbo.search_queries",
            ):
                cursor.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))

            cursor.execute(
                "SELECT COL_LENGTH(N'dbo.search_queries', N'source_question_id')"
            )
            supports_question_id = cursor.fetchone()[0] is not None
            query_ids: dict[str, int] = {}
            for order, query in enumerate(envelope.job.queries, start=1):
                query_text = query.query_text
                if supports_question_id:
                    cursor.execute(
                        """
                        INSERT dbo.search_queries
                            (run_id, place_id, source_question_id, query_text,
                             query_order, query_language, relevance_language,
                             region_code, requested_max_results, published_after)
                        OUTPUT INSERTED.query_id
                        VALUES (?, ?, ?, ?, ?, 'en', 'en', 'ES', ?, ?)
                        """,
                        (
                            run_id,
                            envelope.job.place_id,
                            query.question_id,
                            query_text,
                            order,
                            envelope.job.max_results_per_query,
                            envelope.job.published_after,
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT dbo.search_queries
                            (run_id, place_id, query_text, query_order,
                             query_language, relevance_language, region_code,
                             requested_max_results, published_after)
                        OUTPUT INSERTED.query_id
                        VALUES (?, ?, ?, ?, 'en', 'en', 'ES', ?, ?)
                        """,
                        (
                            run_id,
                            envelope.job.place_id,
                            query_text,
                            order,
                            envelope.job.max_results_per_query,
                            envelope.job.published_after,
                        ),
                    )
                row = cursor.fetchone()
                query_ids[query_text] = int(row[0])

            search_rows: list[tuple[object, ...]] = []
            for query_text, results in data.query_results.items():
                query_id = query_ids[query_text]
                search_rows.extend(
                    (
                        run_id,
                        query_id,
                        result.video_id,
                        result.search_position,
                        result.page_number,
                        result.youtube_kind,
                        result.youtube_etag,
                        _datetime(result.retrieved_at),
                    )
                    for result in results
                )
            if search_rows:
                cursor.executemany(
                    """
                    INSERT dbo.search_results_raw
                        (run_id, query_id, video_id, search_position, page_number,
                         youtube_kind, youtube_etag, retrieved_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    search_rows,
                )

            if data.videos:
                cursor.executemany(
                    """
                    INSERT dbo.videos_raw
                        (run_id, video_id, youtube_kind, youtube_etag,
                         channel_id, channel_title, title, description,
                         tags_json, thumbnails_json, topic_categories_json,
                         published_at, category_id, default_language,
                         default_audio_language, duration_iso, definition,
                         dimension, projection, caption, licensed_content,
                         privacy_status, embeddable, public_stats_viewable,
                         made_for_kids, paid_product_placement,
                         contains_synthetic_media, recording_date,
                         location_description, location_latitude,
                         location_longitude, regions_allowed_json,
                         regions_blocked_json, retrieved_at)
                    VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                         ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            run_id,
                            video.get("video_id"),
                            video.get("youtube_kind"),
                            video.get("youtube_etag"),
                            video.get("channel_id"),
                            video.get("channel_title"),
                            video.get("title"),
                            video.get("description"),
                            _json(video.get("tags")),
                            _json(video.get("thumbnails")),
                            _json(video.get("topic_categories")),
                            _datetime(video.get("published_at")),
                            video.get("category_id"),
                            video.get("default_language"),
                            video.get("default_audio_language"),
                            video.get("duration_iso"),
                            video.get("definition"),
                            video.get("dimension"),
                            video.get("projection"),
                            video.get("caption"),
                            video.get("licensed_content"),
                            video.get("privacy_status"),
                            video.get("embeddable"),
                            video.get("public_stats_viewable"),
                            video.get("made_for_kids"),
                            video.get("paid_product_placement"),
                            video.get("contains_synthetic_media"),
                            _datetime(video.get("recording_date")),
                            video.get("location_description"),
                            video.get("location_latitude"),
                            video.get("location_longitude"),
                            _json(video.get("regions_allowed")),
                            _json(video.get("regions_blocked")),
                            _datetime(video.get("retrieved_at")),
                        )
                        for video in data.videos
                    ],
                )

            if data.statistics:
                cursor.executemany(
                    """
                    INSERT dbo.video_statistics_raw
                        (run_id, video_id, view_count, like_count,
                         favorite_count, comment_count, retrieved_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            run_id,
                            item.get("video_id"),
                            item.get("view_count"),
                            item.get("like_count"),
                            item.get("favorite_count"),
                            item.get("comment_count"),
                            _datetime(item.get("retrieved_at")),
                        )
                        for item in data.statistics
                    ],
                )

            comment_rows = [
                (
                    run_id,
                    item.get("comment_id"),
                    item.get("video_id"),
                    item.get("comment_thread_id"),
                    item.get("parent_comment_id"),
                    item.get("author_channel_id"),
                    item.get("author_display_name"),
                    item.get("text_original"),
                    item.get("text_display"),
                    item.get("can_rate"),
                    item.get("viewer_rating"),
                    item.get("like_count"),
                    item.get("total_reply_count"),
                    item.get("moderation_status"),
                    _datetime(item.get("published_at")),
                    _datetime(item.get("updated_at")),
                    _datetime(item.get("retrieved_at")),
                )
                for item in data.comments
                if item.get("comment_id")
            ]
            if comment_rows:
                cursor.executemany(
                    """
                    INSERT dbo.video_comments_raw
                        (run_id, comment_id, video_id, comment_thread_id,
                         parent_comment_id, author_channel_id,
                         author_display_name, text_original, text_display,
                         can_rate, viewer_rating, like_count, total_reply_count,
                         moderation_status, published_at, updated_at, retrieved_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    comment_rows,
                )

            if data.errors:
                cursor.executemany(
                    """
                    INSERT dbo.run_errors
                        (run_id, query_id, stage, entity_id, http_status,
                         error_code, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            run_id,
                            query_ids.get(error.query_text) if error.query_text else None,
                            error.stage,
                            error.entity_id,
                            error.http_status,
                            error.error_code,
                            error.message,
                        )
                        for error in data.errors
                    ],
                )

            cursor.execute(
                """
                UPDATE dbo.pipeline_runs
                SET status = ?, completed_at = SYSUTCDATETIME()
                WHERE run_id = ?
                """,
                (status, run_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_failed(self, run_id: str, message: str) -> None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                UPDATE dbo.pipeline_runs
                SET status = 'FAILED', completed_at = SYSUTCDATETIME()
                WHERE run_id = ?
                """,
                (run_id,),
            )
            cursor.execute(
                """
                INSERT dbo.run_errors (run_id, stage, error_message)
                SELECT ?, 'worker', ?
                WHERE EXISTS (
                    SELECT 1 FROM dbo.pipeline_runs WHERE run_id = ?
                )
                """,
                (run_id, message[:4000], run_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_run(self, run_id: str) -> dict[str, object] | None:
        connection = self._connection_factory()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT run_id, flow_run_id, status, requested_at,
                       started_at, completed_at
                FROM dbo.pipeline_runs
                WHERE run_id = ?
                """,
                (run_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            names = (
                "run_id",
                "flow_run_id",
                "status",
                "requested_at",
                "started_at",
                "completed_at",
            )
            return {
                name: (
                    value.isoformat()
                    if isinstance(value, datetime)
                    else str(value)
                    if isinstance(value, UUID)
                    else value
                )
                for name, value in zip(names, row, strict=True)
            }
        finally:
            connection.close()
