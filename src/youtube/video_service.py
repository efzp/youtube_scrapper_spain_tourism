"""Recuperacion por lotes de metadatos unicos de videos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.youtube.client import YouTubeClient
from src.youtube.transformers import transform_video

VIDEO_PARTS = (
    "snippet,contentDetails,statistics,status,recordingDetails,"
    "topicDetails,paidProductPlacementDetails"
)


@dataclass(frozen=True, slots=True)
class VideoOutcome:
    """Metadatos recuperados, llamadas y IDs no devueltos."""

    videos: list[dict[str, object]]
    calls: int
    missing_video_ids: list[str]


def chunks(values: list[str], size: int = 50) -> list[list[str]]:
    """Divide valores en lotes de como maximo 50 elementos."""
    if not 1 <= size <= 50:
        raise ValueError("El tamano de lote debe estar entre 1 y 50.")
    return [values[index : index + size] for index in range(0, len(values), size)]


def fetch_videos(
    client: YouTubeClient,
    video_ids: list[str],
    *,
    now: datetime | None = None,
) -> VideoOutcome:
    """Deduplica IDs y llama `videos.list` en lotes de hasta 50."""
    unique_ids = list(dict.fromkeys(video_ids))
    retrieved_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    videos: list[dict[str, object]] = []
    returned_ids: set[str] = set()
    calls = 0
    for batch in chunks(unique_ids):
        response = client.videos(part=VIDEO_PARTS, id=",".join(batch))
        calls += 1
        for item in response.get("items") or []:
            transformed = transform_video(item, retrieved_at)
            video_id = transformed.get("video_id")
            if isinstance(video_id, str) and video_id not in returned_ids:
                returned_ids.add(video_id)
                videos.append(transformed)
    missing = [video_id for video_id in unique_ids if video_id not in returned_ids]
    return VideoOutcome(videos=videos, calls=calls, missing_video_ids=missing)
