"""Contrato HTTP y mensaje interno del trabajo en Azure."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID, uuid4, uuid5

JOB_NAMESPACE = UUID("03c0cc51-4397-53bb-8b8b-a0dca2f58aa0")
ENGLISH_QUERY_FIELDS = ("consulta_en_review", "consulta_en_que_hacer")
VALID_SEARCH_ORDERS = frozenset({"date", "rating", "relevance", "title", "viewCount"})


class JobValidationError(ValueError):
    """Indica que el POST de Power Automate no cumple el contrato."""


def _required_text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if value is None or not str(value).strip():
        raise JobValidationError(f"El campo '{name}' es obligatorio.")
    return str(value).strip()


def _optional_text(payload: Mapping[str, Any], name: str) -> str | None:
    value = payload.get(name)
    return str(value).strip() if value is not None and str(value).strip() else None


def _datetime(value: Any, name: str) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise JobValidationError(f"El campo '{name}' debe ser una fecha ISO 8601.") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class JobQuery:
    """Consulta renderizada y su identificador en `tbl_preguntas`."""

    question_id: str | None
    query_text: str

    @classmethod
    def from_value(cls, value: Any) -> "JobQuery":
        if isinstance(value, Mapping):
            query_text = _required_text(value, "query_text")
            question_id = _optional_text(value, "question_id")
            return cls(question_id=question_id, query_text=query_text)
        if value is None or not str(value).strip():
            raise JobValidationError("Cada elemento de 'queries' debe contener query_text.")
        return cls(question_id=None, query_text=str(value).strip())

    def to_dict(self) -> dict[str, str | None]:
        return {"question_id": self.question_id, "query_text": self.query_text}


@dataclass(frozen=True, slots=True)
class JobRequest:
    """Municipio y consultas inglesas enviados por Power Automate."""

    place_id: str
    municipio: str
    provincia: str
    comunidad_autonoma: str
    queries: tuple[JobQuery, ...]
    tipologia_principal: str | None = None
    flow_run_id: str | None = None
    published_after: datetime | None = None
    max_results_per_query: int = 25
    max_comments_per_video: int | None = None
    search_order: str = "relevance"

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        default_max_comments: int | None = None,
    ) -> "JobRequest":
        supplied_queries = payload.get("queries")
        if supplied_queries is not None:
            if not isinstance(supplied_queries, list):
                raise JobValidationError("El campo 'queries' debe ser una lista.")
            query_values = supplied_queries
        else:
            query_values = [payload.get(field) for field in ENGLISH_QUERY_FIELDS]
        queries_list: list[JobQuery] = []
        seen_query_texts: set[str] = set()
        for value in query_values:
            if value is None or (not isinstance(value, Mapping) and not str(value).strip()):
                continue
            query = JobQuery.from_value(value)
            if query.query_text in seen_query_texts:
                continue
            seen_query_texts.add(query.query_text)
            queries_list.append(query)
        queries = tuple(queries_list)
        if not queries:
            raise JobValidationError(
                "Debe enviar 'queries' o al menos una consulta inglesa del Excel."
            )
        try:
            max_results = int(payload.get("max_results_per_query", 25))
        except (TypeError, ValueError) as exc:
            raise JobValidationError("max_results_per_query debe ser un entero.") from exc
        if not 1 <= max_results <= 500:
            raise JobValidationError("max_results_per_query debe estar entre 1 y 500.")
        raw_max_comments = payload.get("max_comments_per_video", default_max_comments)
        if raw_max_comments in (None, ""):
            max_comments = None
        else:
            try:
                max_comments = int(raw_max_comments)
            except (TypeError, ValueError) as exc:
                raise JobValidationError("max_comments_per_video debe ser un entero.") from exc
            if max_comments < 1:
                raise JobValidationError("max_comments_per_video debe ser positivo.")
        search_order = str(payload.get("search_order") or "relevance").strip()
        if search_order not in VALID_SEARCH_ORDERS:
            raise JobValidationError(
                "search_order debe ser date, rating, relevance, title o viewCount."
            )
        return cls(
            place_id=_required_text(payload, "place_id"),
            municipio=_required_text(payload, "municipio"),
            provincia=_required_text(payload, "provincia"),
            comunidad_autonoma=_required_text(payload, "comunidad_autonoma"),
            tipologia_principal=_optional_text(payload, "tipologia_principal"),
            flow_run_id=_optional_text(payload, "flow_run_id"),
            queries=queries,
            published_after=_datetime(payload.get("published_after"), "published_after"),
            max_results_per_query=max_results,
            max_comments_per_video=max_comments,
            search_order=search_order,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["queries"] = [query.to_dict() for query in self.queries]
        payload["published_after"] = (
            self.published_after.astimezone(timezone.utc).isoformat()
            if self.published_after
            else None
        )
        return payload

    @property
    def query_texts(self) -> tuple[str, ...]:
        return tuple(query.query_text for query in self.queries)


@dataclass(frozen=True, slots=True)
class JobEnvelope:
    """Mensaje estable enviado a Azure Queue Storage."""

    run_id: str
    enqueued_at: datetime
    job: JobRequest

    @classmethod
    def create(cls, job: JobRequest) -> "JobEnvelope":
        run_uuid = uuid5(JOB_NAMESPACE, job.flow_run_id) if job.flow_run_id else uuid4()
        return cls(str(run_uuid), datetime.now(timezone.utc), job)

    def to_json(self) -> str:
        return json.dumps(
            {
                "run_id": self.run_id,
                "enqueued_at": self.enqueued_at.astimezone(timezone.utc).isoformat(),
                "job": self.job.to_dict(),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, value: str) -> "JobEnvelope":
        try:
            payload = json.loads(value)
            run_id = str(UUID(str(payload["run_id"])))
            enqueued_at = _datetime(payload["enqueued_at"], "enqueued_at")
            job = JobRequest.from_mapping(payload["job"])
        except (KeyError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise JobValidationError("El mensaje de cola no es valido.") from exc
        if enqueued_at is None:
            raise JobValidationError("El mensaje no contiene enqueued_at.")
        return cls(run_id, enqueued_at, job)
