"""Extraccion de campos directos de YouTube sin metricas derivadas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def transform_video_raw(
    item: dict[str, Any], retrieved_at: datetime
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Separa metadatos y estadisticas directas de un recurso `video`."""
    snippet = item.get("snippet") or {}
    content = item.get("contentDetails") or {}
    statistics = item.get("statistics") or {}
    status = item.get("status") or {}
    topics = item.get("topicDetails") or {}
    recording = item.get("recordingDetails") or {}
    location = recording.get("location") or {}
    restrictions = content.get("regionRestriction") or {}
    paid = item.get("paidProductPlacementDetails") or {}
    timestamp = retrieved_at.astimezone(timezone.utc)
    video_id = item.get("id")
    metadata = {
        "video_id": str(video_id) if video_id is not None else None,
        "youtube_kind": item.get("kind"),
        "youtube_etag": item.get("etag"),
        "channel_id": snippet.get("channelId"),
        "channel_title": snippet.get("channelTitle"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "tags": snippet.get("tags"),
        "thumbnails": snippet.get("thumbnails"),
        "topic_categories": topics.get("topicCategories"),
        "published_at": snippet.get("publishedAt"),
        "category_id": snippet.get("categoryId"),
        "default_language": snippet.get("defaultLanguage"),
        "default_audio_language": snippet.get("defaultAudioLanguage"),
        "duration_iso": content.get("duration"),
        "definition": content.get("definition"),
        "dimension": content.get("dimension"),
        "projection": content.get("projection"),
        "caption": content.get("caption"),
        "licensed_content": content.get("licensedContent"),
        "privacy_status": status.get("privacyStatus"),
        "embeddable": status.get("embeddable"),
        "public_stats_viewable": status.get("publicStatsViewable"),
        "made_for_kids": status.get("madeForKids"),
        "paid_product_placement": paid.get("hasPaidProductPlacement"),
        "contains_synthetic_media": status.get("containsSyntheticMedia"),
        "recording_date": recording.get("recordingDate"),
        "location_description": recording.get("locationDescription"),
        "location_latitude": location.get("latitude"),
        "location_longitude": location.get("longitude"),
        "regions_allowed": restrictions.get("allowed"),
        "regions_blocked": restrictions.get("blocked"),
        "retrieved_at": timestamp,
    }
    raw_statistics = {
        "video_id": metadata["video_id"],
        "view_count": _integer(statistics.get("viewCount")),
        "like_count": _integer(statistics.get("likeCount")),
        "favorite_count": _integer(statistics.get("favoriteCount")),
        "comment_count": _integer(statistics.get("commentCount")),
        "retrieved_at": timestamp,
    }
    return metadata, raw_statistics


def transform_comment_raw(
    item: dict[str, Any],
    *,
    video_id: str,
    retrieved_at: datetime,
    comment_thread_id: str | None = None,
    parent_comment_id: str | None = None,
    total_reply_count: int | None = None,
) -> dict[str, Any]:
    """Extrae campos publicos directos de un comentario o respuesta."""
    snippet = item.get("snippet") or {}
    author_channel = snippet.get("authorChannelId") or {}
    return {
        "comment_id": str(item.get("id")) if item.get("id") is not None else None,
        "video_id": str(snippet.get("videoId") or video_id),
        "comment_thread_id": comment_thread_id,
        "parent_comment_id": snippet.get("parentId") or parent_comment_id,
        "author_channel_id": author_channel.get("value"),
        "author_display_name": snippet.get("authorDisplayName"),
        "text_original": snippet.get("textOriginal"),
        "text_display": snippet.get("textDisplay"),
        "can_rate": snippet.get("canRate"),
        "viewer_rating": snippet.get("viewerRating"),
        "like_count": _integer(snippet.get("likeCount")),
        "total_reply_count": total_reply_count,
        "moderation_status": snippet.get("moderationStatus"),
        "published_at": snippet.get("publishedAt"),
        "updated_at": snippet.get("updatedAt"),
        "retrieved_at": retrieved_at.astimezone(timezone.utc),
    }
