"""Recuperacion paginada de comentarios y todas sus respuestas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.youtube.client import YouTubeClient
from src.youtube.raw_transformers import transform_comment_raw


@dataclass(frozen=True, slots=True)
class CommentOutcome:
    comments: list[dict[str, object]]
    comment_thread_calls: int
    reply_calls: int


def fetch_video_comments(
    client: YouTubeClient,
    video_id: str,
    *,
    max_comments: int | None = None,
    now: datetime | None = None,
) -> CommentOutcome:
    """Recupera comentarios sin filtrar idioma y pagina todas las respuestas."""
    if max_comments is not None and max_comments < 1:
        raise ValueError("max_comments debe ser positivo o None.")
    retrieved_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    records: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    thread_token: str | None = None
    thread_calls = 0
    reply_calls = 0

    def has_capacity() -> bool:
        return max_comments is None or len(records) < max_comments

    def append_comment(record: dict[str, object]) -> None:
        comment_id = record.get("comment_id")
        if isinstance(comment_id, str) and comment_id not in seen_ids and has_capacity():
            seen_ids.add(comment_id)
            records.append(record)

    while has_capacity():
        parameters: dict[str, object] = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": 100,
            "order": "time",
            "textFormat": "plainText",
        }
        if thread_token:
            parameters["pageToken"] = thread_token
        response = client.comment_threads(**parameters)
        thread_calls += 1
        items = response.get("items") or []
        for thread in items:
            if not has_capacity():
                break
            thread_id = str(thread.get("id")) if thread.get("id") is not None else None
            thread_snippet = thread.get("snippet") or {}
            top_level = thread_snippet.get("topLevelComment") or {}
            top_id = top_level.get("id")
            total_replies = int(thread_snippet.get("totalReplyCount") or 0)
            append_comment(
                transform_comment_raw(
                    top_level,
                    video_id=video_id,
                    retrieved_at=retrieved_at,
                    comment_thread_id=thread_id,
                    total_reply_count=total_replies,
                )
            )
            if not top_id or total_replies < 1 or not has_capacity():
                continue
            reply_token: str | None = None
            while has_capacity():
                reply_parameters: dict[str, object] = {
                    "part": "snippet",
                    "parentId": str(top_id),
                    "maxResults": 100,
                    "textFormat": "plainText",
                }
                if reply_token:
                    reply_parameters["pageToken"] = reply_token
                reply_response = client.comments(**reply_parameters)
                reply_calls += 1
                reply_items = reply_response.get("items") or []
                for reply in reply_items:
                    append_comment(
                        transform_comment_raw(
                            reply,
                            video_id=video_id,
                            retrieved_at=retrieved_at,
                            comment_thread_id=thread_id,
                            parent_comment_id=str(top_id),
                        )
                    )
                    if not has_capacity():
                        break
                reply_token = reply_response.get("nextPageToken")
                if not reply_token or not reply_items:
                    break
        thread_token = response.get("nextPageToken")
        if not thread_token or not items:
            break
    return CommentOutcome(records, thread_calls, reply_calls)
