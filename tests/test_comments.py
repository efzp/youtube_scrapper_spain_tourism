from datetime import datetime, timezone

from src.youtube.comment_service import fetch_video_comments


class FakeCommentClient:
    def __init__(self) -> None:
        self.thread_calls: list[dict[str, object]] = []
        self.reply_calls: list[dict[str, object]] = []

    def comment_threads(self, **parameters: object) -> dict[str, object]:
        self.thread_calls.append(parameters)
        return {
            "items": [
                {
                    "id": "thread-1",
                    "snippet": {
                        "videoId": "video-1",
                        "totalReplyCount": 2,
                        "topLevelComment": {
                            "id": "comment-1",
                            "snippet": {
                                "videoId": "video-1",
                                "textOriginal": "¡Excelente visita!",
                                "textDisplay": "¡Excelente visita!",
                                "authorDisplayName": "Álvaro",
                                "likeCount": 3,
                                "publishedAt": "2026-01-01T00:00:00Z",
                            },
                        },
                    },
                }
            ]
        }

    def comments(self, **parameters: object) -> dict[str, object]:
        self.reply_calls.append(parameters)
        return {
            "items": [
                {
                    "id": "reply-1",
                    "snippet": {
                        "parentId": "comment-1",
                        "textOriginal": "素晴らしい",
                    },
                },
                {
                    "id": "reply-2",
                    "snippet": {
                        "parentId": "comment-1",
                        "textOriginal": "مكان جميل",
                    },
                },
            ]
        }


def test_fetches_top_level_and_all_replies_without_language_filter() -> None:
    client = FakeCommentClient()
    outcome = fetch_video_comments(
        client,  # type: ignore[arg-type]
        "video-1",
        now=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    assert [item["comment_id"] for item in outcome.comments] == [
        "comment-1",
        "reply-1",
        "reply-2",
    ]
    assert [item["text_original"] for item in outcome.comments] == [
        "¡Excelente visita!",
        "素晴らしい",
        "مكان جميل",
    ]
    assert client.thread_calls[0]["textFormat"] == "plainText"
    assert "relevanceLanguage" not in client.thread_calls[0]
    assert client.reply_calls[0]["parentId"] == "comment-1"
