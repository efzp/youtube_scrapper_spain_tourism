from datetime import datetime, timezone

from src.cloud.contracts import JobEnvelope, JobRequest
from src.cloud.pipeline import CloudPipeline, RawRunData


class FakeCloudClient:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, object]] = []

    def search(self, **parameters: object) -> dict[str, object]:
        self.search_calls.append(parameters)
        return {"items": [{"kind": "youtube#searchResult", "id": {"videoId": "v1"}}]}

    def videos(self, **parameters: object) -> dict[str, object]:
        return {
            "items": [
                {
                    "id": "v1",
                    "snippet": {
                        "title": "Seville guide",
                        "publishedAt": "2025-01-01T00:00:00Z",
                    },
                    "contentDetails": {"duration": "PT5M"},
                    "statistics": {"viewCount": "10", "commentCount": "0"},
                }
            ]
        }

    def comment_threads(self, **parameters: object) -> dict[str, object]:
        return {"items": []}

    def comments(self, **parameters: object) -> dict[str, object]:
        raise AssertionError("No debe pedir respuestas sin comentarios principales.")


class MemoryCloudWriter:
    def __init__(self) -> None:
        self.saved: tuple[JobEnvelope, RawRunData, str] | None = None

    def begin_run(self, envelope: JobEnvelope) -> bool:
        return True

    def save_run(self, envelope: JobEnvelope, data: RawRunData, status: str) -> None:
        self.saved = (envelope, data, status)


def test_cloud_pipeline_uses_english_search_and_keeps_only_raw_fields() -> None:
    job = JobRequest(
        place_id="ES-001",
        municipio="Sevilla",
        provincia="Sevilla",
        comunidad_autonoma="Andalucia",
        queries=('"Seville Spain" travel review',),
        max_comments_per_video=10,
    )
    envelope = JobEnvelope.create(job)
    client = FakeCloudClient()
    writer = MemoryCloudWriter()

    status = CloudPipeline(client, writer).run(  # type: ignore[arg-type]
        envelope,
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    assert status == "COMPLETED"
    assert client.search_calls[0]["relevanceLanguage"] == "en"
    assert client.search_calls[0]["regionCode"] == "ES"
    assert writer.saved is not None
    _, data, _ = writer.saved
    assert data.videos[0]["duration_iso"] == "PT5M"
    assert "duration_seconds" not in data.videos[0]
    assert data.statistics[0]["view_count"] == 10
