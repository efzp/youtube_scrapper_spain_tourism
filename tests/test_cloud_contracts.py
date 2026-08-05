from datetime import timezone

import pytest

from src.cloud.contracts import JobEnvelope, JobRequest, JobValidationError


def _payload() -> dict[str, object]:
    return {
        "flow_run_id": "power-automate-run-1",
        "place_id": "ES-001",
        "municipio": "Sevilla",
        "provincia": "Sevilla",
        "comunidad_autonoma": "Andalucia",
        "consulta_es_turismo": "consulta que debe ignorarse",
        "consulta_en_review": '"Seville Spain" travel review',
        "consulta_en_que_hacer": '"Seville Spain" things to do',
        "published_after": "2025-01-01T00:00:00Z",
    }


def test_accepts_only_english_excel_columns() -> None:
    job = JobRequest.from_mapping(_payload())

    assert job.queries == (
        '"Seville Spain" travel review',
        '"Seville Spain" things to do',
    )
    assert job.published_after is not None
    assert job.published_after.tzinfo == timezone.utc


def test_queue_envelope_is_deterministic_for_flow_retry() -> None:
    job = JobRequest.from_mapping(_payload())

    first = JobEnvelope.create(job)
    second = JobEnvelope.create(job)
    restored = JobEnvelope.from_json(first.to_json())

    assert first.run_id == second.run_id
    assert restored.run_id == first.run_id
    assert restored.job.queries == job.queries


def test_rejects_request_without_english_queries() -> None:
    payload = _payload()
    payload["consulta_en_review"] = ""
    payload["consulta_en_que_hacer"] = None

    with pytest.raises(JobValidationError, match="consulta inglesa"):
        JobRequest.from_mapping(payload)
