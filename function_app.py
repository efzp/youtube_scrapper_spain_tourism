"""Puntos de entrada de Azure Functions para Power Automate y el worker."""

from __future__ import annotations

import json
import logging
import os
from uuid import UUID

import azure.functions as func

from src.cloud.contracts import JobEnvelope, JobRequest, JobValidationError
from src.cloud.pipeline import CloudPipeline
from src.persistence.sql_writer import SqlConfigurationError, SqlRunWriter
from src.youtube.client import YouTubeClient

LOGGER = logging.getLogger(__name__)
app = func.FunctionApp()


def _json_response(payload: dict[str, object], status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
        charset="utf-8",
    )


def _default_max_comments() -> int | None:
    value = os.getenv("YOUTUBE_MAX_COMMENTS_PER_VIDEO", "").strip()
    if not value:
        return None
    parsed = int(value)
    if parsed < 1:
        raise ValueError("YOUTUBE_MAX_COMMENTS_PER_VIDEO debe ser positivo.")
    return parsed


@app.function_name(name="StartYoutubeJob")
@app.route(
    route="youtube/jobs",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION,
)
@app.queue_output(
    arg_name="job_message",
    queue_name="youtube-jobs",
    connection="AzureWebJobsStorage",
)
def start_youtube_job(
    req: func.HttpRequest,
    job_message: func.Out[str],
) -> func.HttpResponse:
    """Valida un municipio y lo publica para procesamiento asincrono."""
    try:
        payload = req.get_json()
        if not isinstance(payload, dict):
            raise JobValidationError("El cuerpo JSON debe ser un objeto.")
        job = JobRequest.from_mapping(
            payload,
            default_max_comments=_default_max_comments(),
        )
        envelope = JobEnvelope.create(job)
    except ValueError as exc:
        return _json_response({"error": str(exc)}, 400)
    job_message.set(envelope.to_json())
    return _json_response(
        {
            "run_id": envelope.run_id,
            "status": "RECEIVED",
            "status_url": f"/api/youtube/jobs/{envelope.run_id}",
        },
        202,
    )


@app.function_name(name="ProcessYoutubeJob")
@app.queue_trigger(
    arg_name="message",
    queue_name="youtube-jobs",
    connection="AzureWebJobsStorage",
)
def process_youtube_job(message: func.QueueMessage) -> None:
    """Consume la cola, recupera YouTube y persiste el lote en Azure SQL."""
    envelope = JobEnvelope.from_json(message.get_body().decode("utf-8"))
    writer = SqlRunWriter()
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        error = "Falta la variable YOUTUBE_API_KEY."
        try:
            writer.begin_run(envelope)
            writer.mark_failed(envelope.run_id, error)
        except Exception:
            LOGGER.exception(
                "No se pudo registrar la configuracion faltante",
                extra={"run_id": envelope.run_id},
            )
        raise RuntimeError(error)
    try:
        status = CloudPipeline(YouTubeClient(api_key), writer).run(envelope)
        LOGGER.info(
            "Trabajo de YouTube finalizado",
            extra={"run_id": envelope.run_id, "status": status},
        )
    except Exception as exc:
        LOGGER.exception("Fallo no recuperable del worker", extra={"run_id": envelope.run_id})
        try:
            writer.mark_failed(envelope.run_id, str(exc))
        except Exception:
            LOGGER.exception(
                "No se pudo registrar el fallo del worker",
                extra={"run_id": envelope.run_id},
            )
        raise


@app.function_name(name="GetYoutubeJob")
@app.route(
    route="youtube/jobs/{run_id}",
    methods=["GET"],
    auth_level=func.AuthLevel.FUNCTION,
)
def get_youtube_job(req: func.HttpRequest) -> func.HttpResponse:
    """Devuelve el estado persistido de una ejecucion."""
    raw_run_id = req.route_params.get("run_id", "")
    try:
        run_id = str(UUID(raw_run_id))
        record = SqlRunWriter().get_run(run_id)
    except ValueError:
        return _json_response({"error": "run_id no es un UUID valido."}, 400)
    except SqlConfigurationError as exc:
        LOGGER.error("Configuracion SQL invalida: %s", exc)
        return _json_response({"error": "Servicio no configurado."}, 500)
    if record is None:
        return _json_response(
            {"run_id": run_id, "status": "QUEUED"},
            202,
        )
    return _json_response(record, 200)
