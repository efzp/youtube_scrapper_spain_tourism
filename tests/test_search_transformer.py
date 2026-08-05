from dataclasses import replace
from datetime import datetime, timezone

from src.models import SearchTask
from src.youtube.search_service import search_task


class FakeSearchClient:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, object]] = []

    def search(self, **parameters: object) -> dict[str, object]:
        self.calls.append(parameters)
        return next(self.responses)


def test_empty_search_results(place) -> None:
    client = FakeSearchClient([{"items": []}])
    outcome = search_task(client, SearchTask(place, place.queries[0]), "run-1")  # type: ignore[arg-type]
    assert outcome.results == []
    assert outcome.calls == 1
    assert outcome.raw_results == 0


def test_records_position_query_and_paginates(place) -> None:
    place = replace(place, max_results_per_query=3)
    client = FakeSearchClient(
        [
            {
                "items": [{"id": {"videoId": "a"}}, {"id": {"videoId": "b"}}],
                "nextPageToken": "next",
            },
            {"items": [{"id": {"videoId": "b"}}, {"id": {"videoId": "c"}}]},
        ]
    )
    task = SearchTask(place, place.queries[0])

    outcome = search_task(
        client, task, "run-1", now=datetime(2026, 1, 1, tzinfo=timezone.utc)  # type: ignore[arg-type]
    )

    assert [result.video_id for result in outcome.results] == ["a", "b", "c"]
    assert [result.search_position for result in outcome.results] == [1, 2, 3]
    assert outcome.raw_results == 4
    assert client.calls[1]["pageToken"] == "next"
    assert client.calls[0]["publishedAfter"] == "2023-01-01T00:00:00Z"
    assert client.calls[0]["part"] == "snippet"
    assert client.calls[0]["type"] == "video"
