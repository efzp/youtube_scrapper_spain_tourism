"""Transformacion de recursos `video` directos y metricas derivadas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import isodate


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _duration_seconds(value: str | None) -> int | None:
    if not value:
        return None
    try:
        duration = isodate.parse_duration(value)
        if hasattr(duration, "total_seconds"):
            return int(duration.total_seconds())
        return int(duration.totimedelta(datetime.now(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def _thumbnail_url(snippet: dict[str, Any]) -> str | None:
    thumbnails = snippet.get("thumbnails") or {}
    for size in ("maxres", "standard", "high", "medium", "default"):
        url = (thumbnails.get(size) or {}).get("url")
        if url:
            return url
    return None


def transform_video(item: dict[str, Any], retrieved_at: datetime) -> dict[str, Any]:
    """Extrae campos publicos sin fallar cuando un bloque opcional no existe."""
    snippet = item.get("snippet") or {}
    content = item.get("contentDetails") or {}
    statistics = item.get("statistics") or {}
    status = item.get("status") or {}
    topics = item.get("topicDetails") or {}
    recording = item.get("recordingDetails") or {}
    restrictions = content.get("regionRestriction") or {}
    paid = item.get("paidProductPlacementDetails") or {}
    video_id = item.get("id")
    duration_iso = content.get("duration")
    return {
        "video_id": video_id,
        "video_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
        "channel_id": snippet.get("channelId"),
        "channel_title": snippet.get("channelTitle"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "tags": snippet.get("tags"),
        "published_at": snippet.get("publishedAt"),
        "category_id": snippet.get("categoryId"),
        "default_language": snippet.get("defaultLanguage"),
        "default_audio_language": snippet.get("defaultAudioLanguage"),
        "duration_iso": duration_iso,
        "duration_seconds": _duration_seconds(duration_iso),
        "definition": content.get("definition"),
        "dimension": content.get("dimension"),
        "projection": content.get("projection"),
        "caption_available": (
            str(content.get("caption")).lower() == "true"
            if content.get("caption") is not None
            else None
        ),
        "licensed_content": content.get("licensedContent"),
        "view_count": _integer(statistics.get("viewCount")),
        "like_count": _integer(statistics.get("likeCount")),
        "comment_count": _integer(statistics.get("commentCount")),
        "privacy_status": status.get("privacyStatus"),
        "embeddable": status.get("embeddable"),
        "public_stats_viewable": status.get("publicStatsViewable"),
        "made_for_kids": status.get("madeForKids"),
        "paid_product_placement": paid.get("hasPaidProductPlacement"),
        "contains_synthetic_media": status.get("containsSyntheticMedia"),
        "thumbnail_url": _thumbnail_url(snippet),
        "topic_categories": topics.get("topicCategories"),
        "recording_date": recording.get("recordingDate"),
        "location_description": recording.get("locationDescription"),
        "regions_allowed": restrictions.get("allowed"),
        "regions_blocked": restrictions.get("blocked"),
        "retrieved_at": retrieved_at.astimezone(timezone.utc).isoformat(),
    }


def derive_video_metrics(
    video: dict[str, Any], *, short_max_seconds: int = 180, recent_days: int = 365
) -> dict[str, Any]:
    """Calcula metricas propias, separadas de los datos directos de YouTube."""
    retrieved = datetime.fromisoformat(str(video["retrieved_at"]).replace("Z", "+00:00"))
    published_raw = video.get("published_at")
    age_days: int | None = None
    if published_raw:
        try:
            published = datetime.fromisoformat(str(published_raw).replace("Z", "+00:00"))
            age_days = max(0, (retrieved - published.astimezone(timezone.utc)).days)
        except ValueError:
            age_days = None
    views = video.get("view_count")
    likes = video.get("like_count")
    comments = video.get("comment_count")
    duration = video.get("duration_seconds")
    valid_views = isinstance(views, int) and views > 0
    return {
        "video_id": video.get("video_id"),
        "duration_minutes": duration / 60 if isinstance(duration, int) else None,
        "age_days": age_days,
        "views_per_day": views / max(age_days, 1) if isinstance(views, int) and age_days is not None else None,
        "like_rate": likes / views if valid_views and isinstance(likes, int) else None,
        "comment_rate": comments / views if valid_views and isinstance(comments, int) else None,
        "engagement_rate": (
            ((likes or 0) + (comments or 0)) / views
            if valid_views and (isinstance(likes, int) or isinstance(comments, int))
            else None
        ),
        "is_short_candidate": (
            0 < duration <= short_max_seconds if isinstance(duration, int) else None
        ),
        "has_comments": comments > 0 if isinstance(comments, int) else None,
        "is_recent": age_days <= recent_days if age_days is not None else None,
        "derived_at": retrieved.astimezone(timezone.utc).isoformat(),
    }

