# YouTube Spain Tourism

Pipeline para recopilar datos crudos de videos turísticos de España con YouTube Data API v3. Puede ejecutarse localmente desde el Excel o en Azure mediante Power Automate, Azure Functions, Queue Storage y Azure SQL Database.

## Arquitectura de Azure

Se despliega una sola **Aplicación de funciones** que contiene tres funciones:

1. `StartYoutubeJob`: recibe el `POST` de Power Automate y publica el trabajo en la cola `youtube-jobs`.
2. `ProcessYoutubeJob`: consulta YouTube y guarda búsquedas, videos, estadísticas y comentarios en las tablas `dbo`.
3. `GetYoutubeJob`: permite consultar el estado mediante `run_id`.

La cola evita que Power Automate espere mientras se recorren videos y comentarios. Las búsquedas usan inglés, `relevanceLanguage=en` y `regionCode=ES`. Los comentarios se conservan en su idioma original y no se aplica un filtro de idioma.

La guía completa está en [docs/AZURE_DEPLOYMENT.md](docs/AZURE_DEPLOYMENT.md).

## Contrato del POST

Ruta: `POST /api/youtube/jobs`

```json
{
  "flow_run_id": "power-automate-run-001",
  "place_id": "ES-41091",
  "municipio": "Sevilla",
  "provincia": "Sevilla",
  "comunidad_autonoma": "Andalucía",
  "tipologia_principal": "Turismo cultural",
  "queries": [
    {
      "question_id": "Q001",
      "query_text": "Seville, Seville, Spain travel review"
    },
    {
      "question_id": "Q002",
      "query_text": "things to do in Seville, Seville, Spain"
    }
  ],
  "published_after": "2025-01-01T00:00:00Z",
  "max_results_per_query": 25,
  "max_comments_per_video": 100,
  "search_order": "relevance"
}
```

El catálogo separa `tbl_lugares` de `tbl_preguntas`. Power Automate sustituye los marcadores de cada `plantilla_en` activa y envía `queries` como una lista de objetos. Por compatibilidad, la Function también acepta una lista de textos o las antiguas columnas `consulta_en_*`.

El modelo de prioridad es `0 = enviado/procesado`, `1 = lote actual` y `2 = pendiente`. Al terminar correctamente un lote, sus filas pasan a `0` y el siguiente lote pasa de `2` a `1`.

Para conservar `question_id` en los datos crudos, ejecute una vez [sql/002_add_source_question_id.sql](sql/002_add_source_question_id.sql). La Function sigue funcionando con el esquema anterior, pero no podrá persistir ese identificador hasta aplicar la migración.

Respuesta aceptada:

```json
{
  "run_id": "2f6fb262-e2af-4bc4-aefd-8ac451a1d295",
  "status": "RECEIVED",
  "status_url": "/api/youtube/jobs/2f6fb262-e2af-4bc4-aefd-8ac451a1d295"
}
```

`flow_run_id` hace idempotente un reintento de Power Automate: el mismo valor genera el mismo `run_id`.

## Configuración

Variables requeridas:

- `AzureWebJobsStorage`: conexión a la cuenta de almacenamiento de la Function App.
- `YOUTUBE_API_KEY`: clave de YouTube Data API v3.
- `SQL_CONNECTION_STRING`: conexión a Azure SQL mediante identidad administrada.
- `YOUTUBE_MAX_COMMENTS_PER_VIDEO`: límite predeterminado opcional. Si queda vacío y el POST no envía otro límite, se recorren todos los comentarios disponibles.

Ejemplo de conexión en Azure:

```text
Server=<servidor>.database.windows.net;Database=<base>;Authentication=ActiveDirectoryMSI;Encrypt=yes;TrustServerCertificate=no;
```

No se guarda ninguna respuesta completa como JSON. Solo los atributos directos definidos en las tablas `dbo`; los campos multivalor propios del video (`tags`, miniaturas, temas y restricciones regionales) permanecen en sus columnas JSON.

## Desarrollo local

Requisitos: Python 3.11 o posterior, `uv` y una clave de YouTube.

```powershell
uv sync --extra dev
Copy-Item .env.example .env
uv run python -m pytest
```

Para ejecutar el pipeline local del Excel:

```powershell
uv run python -m src.main --catalog-path ".\catalogo_municipios_turisticos_espana_youtube.xlsx" --max-places 5
```

Las pruebas usan respuestas simuladas y no consumen cuota de YouTube.
