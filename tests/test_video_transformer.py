from datetime import datetime, timezone

from src.youtube.transformers import derive_video_metrics, transform_video


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_transforms_duration_and_statistics() -> None:
    item = {
        "id": "abc",
        "snippet": {
            "title": "Sevilla",
            "publishedAt": "2025-12-22T00:00:00Z",
            "tags": ["viaje"],
            "thumbnails": {"high": {"url": "https://image"}},
        },
        "contentDetails": {"duration": "PT1H2M3S", "caption": "true"},
        "statistics": {"viewCount": "100", "likeCount": "5"},
        "status": {"privacyStatus": "public"},
    }

    video = transform_video(item, NOW)
    derived = derive_video_metrics(video)

    assert video["duration_seconds"] == 3723
    assert video["comment_count"] is None
    assert video["caption_available"] is True
    assert "favorite_count" not in video
    assert derived["age_days"] == 10
    assert derived["views_per_day"] == 10
    assert derived["like_rate"] == 0.05


def test_optional_blocks_and_invalid_duration_do_not_fail() -> None:
    video = transform_video({"id": "abc", "contentDetails": {"duration": "bad"}}, NOW)
    assert video["title"] is None
    assert video["duration_seconds"] is None
    assert video["view_count"] is None


def test_derived_rates_avoid_division_by_zero() -> None:
    video = transform_video(
        {
            "id": "abc",
            "snippet": {"publishedAt": "2025-01-01T00:00:00Z"},
            "statistics": {"viewCount": "0", "likeCount": "3", "commentCount": "1"},
        },
        NOW,
    )
    derived = derive_video_metrics(video)
    assert derived["like_rate"] is None
    assert derived["comment_rate"] is None
    assert derived["engagement_rate"] is None

