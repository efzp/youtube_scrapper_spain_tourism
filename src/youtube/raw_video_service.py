"""Recuperacion de metadatos y estadisticas directas por lotes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.youtube.client import YouTubeClient
from src.youtube.raw_transformers import transform_video_raw
from src.youtube.video_service import VIDEO_PARTS, chunks


@dataclass(frozen=True, slots=True)
class RawVideoOutcome:
    videos: list[dict[str, object]]
    statistics: list[dict[str, object]]
    calls: int
    missing_video_ids: list[str]


def fetch_videos_raw(
    client: YouTubeClient,
    video_ids: list[str],
    *,
    now: datetime | None = None,
) -> RawVideoOutcome:
    """Descarga cada `video_id` una vez sin calcular campos derivados."""
    unique_ids = list(dict.fromkeys(video_ids))
    retrieved_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    videos: list[dict[str, object]] = []
    statistics: list[dict[str, object]] = []
    returned_ids: set[str] = set()
    calls = 0
    for batch in chunks(unique_ids):
        response = client.videos(part=VIDEO_PARTS, id=",".join(batch))
        calls += 1
        for item in response.get("items") or []:
            metadata, raw_statistics = transform_video_raw(item, retrieved_at)
            video_id = metadata.get("video_id")
            if isinstance(video_id, str) and video_id not in returned_ids:
                returned_ids.add(video_id)
                videos.append(metadata)
                statistics.append(raw_statistics)
    missing = [video_id for video_id in unique_ids if video_id not in returned_ids]
    return RawVideoOutcome(videos, statistics, calls, missing)
