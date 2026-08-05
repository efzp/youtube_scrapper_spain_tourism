from src.models import SearchResult
from src.youtube.search_service import unique_video_ids
from src.youtube.video_service import chunks, fetch_videos


class FakeVideoClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def videos(self, **parameters: object) -> dict[str, object]:
        self.calls.append(parameters)
        ids = str(parameters["id"]).split(",")
        return {"items": [{"id": video_id} for video_id in ids]}


def _result(video_id: str) -> SearchResult:
    return SearchResult(
        run_id="run", place_id="place", municipio="Madrid", provincia="Madrid",
        comunidad_autonoma="Madrid", video_id=video_id, search_query="q",
        search_order="relevance", search_position=1, region_code="ES",
        relevance_language="es", published_after=None, retrieved_at="2026-01-01T00:00:00+00:00",
    )


def test_deduplicates_video_ids_preserving_order() -> None:
    assert unique_video_ids([_result("a"), _result("b"), _result("a")]) == ["a", "b"]


def test_chunks_never_exceed_fifty() -> None:
    batches = chunks([str(index) for index in range(121)])
    assert [len(batch) for batch in batches] == [50, 50, 21]


def test_fetches_more_than_fifty_ids_in_batches_and_deduplicates() -> None:
    client = FakeVideoClient()
    ids = [str(index) for index in range(51)] + ["0"]
    outcome = fetch_videos(client, ids)  # type: ignore[arg-type]
    assert outcome.calls == 2
    assert len(outcome.videos) == 51
    assert len(client.calls[0]["id"].split(",")) == 50  # type: ignore[union-attr]
    assert "maxResults" not in client.calls[0]
