# YouTube Spain Tourism

MVP local y académico para buscar videos sobre municipios turísticos de España con YouTube Data API v3. Conserva cada relación municipio–consulta–video, descarga una sola vez los metadatos de cada `video_id` por ejecución y escribe resultados locales de forma atómica.

No implementa comentarios, NLP, Azure SQL, Azure Functions, Power Automate ni SharePoint.

## Requisitos e instalación

- Python 3.11 o posterior. El entorno reproducible incluido usa Python 3.13.
- Una clave de YouTube Data API v3 en `YOUTUBE_API_KEY`.
- [`uv`](https://docs.astral.sh/uv/) o una instalación estándar de Python/pip.

Con `uv`:

```powershell
uv sync --extra dev
Copy-Item .env.example .env
```

Edita `.env` localmente y reemplaza únicamente el marcador de `YOUTUBE_API_KEY`. `.env` está excluido de Git.

## Catálogo real

El libro entregado contiene 122 filas de datos en `tbl_lugares`, hoja `Lugares`. El lector localiza la tabla por nombre, no por la hoja. Sus nombres difieren del esquema orientativo:

| Concepto esperado | Columna real |
|---|---|
| `nombre_lugar` / `categoria` | `municipio` / `tipologia_principal` |
| `consulta_1` … `consulta_4` | `consulta_es_turismo`, `consulta_es_opiniones`, `consulta_en_review`, `consulta_en_que_hacer` |
| `idioma` | `relevance_language` |
| `max_videos` | `max_resultados_consulta` |
| `lote` | `lote_carga` |
| orden de búsqueda | `orden_busqueda` |

El validador entiende también los alias orientativos de consultas, idioma, máximo y lote para facilitar una evolución futura.

## Piloto de cinco municipios

El Excel está actualmente en la raíz del repositorio. Con la clave ya definida en `.env`, ejecuta tú mismo:

```powershell
uv run python -m src.main --catalog-path ".\catalogo_municipios_turisticos_espana_youtube.xlsx" --max-places 5
```

Para reducir aún más el piloto, añade `--max-queries-per-place 1`. Para generar CSV además de Parquet, añade `--csv`.

La CLI procesa como máximo cinco municipios por defecto. No existe un comando que lance automáticamente las 122 filas.

## Salidas

Se crean en `output/`:

- `youtube_search_results.parquet`: una fila por combinación de municipio, consulta y video.
- `youtube_video_metadata.parquet`: una fila de campos directos por `video_id`.
- `youtube_video_derived.parquet`: métricas calculadas, separadas explícitamente.
- `youtube_run_summary.json`: estado, errores, conteos de llamadas y cuota estimada.

La estimación sigue la referencia actual: una unidad por llamada a `search.list` y a `videos.list`; `search.list` tiene además su propio límite de llamadas. Consulta la [referencia de búsqueda](https://developers.google.com/youtube/v3/docs/search/list), la [referencia de videos](https://developers.google.com/youtube/v3/docs/videos/list) y el [cálculo de cuota](https://developers.google.com/youtube/v3/determine_quota_cost).

## Pruebas

```powershell
uv run python -m pytest
```

Todas las respuestas de YouTube se simulan. Las pruebas no leen `YOUTUBE_API_KEY` ni consumen cuota real.

