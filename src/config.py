"""Configuracion desde entorno y argumentos de linea de comandos."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Indica que falta configuracion obligatoria o que es invalida."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuracion inmutable de una ejecucion."""

    api_key: str
    catalog_path: Path
    output_dir: Path
    max_places: int = 5
    max_queries_per_place: int | None = None
    write_csv: bool = False
    short_max_seconds: int = 180

    @classmethod
    def from_env(
        cls,
        *,
        catalog_path: Path | None = None,
        output_dir: Path | None = None,
        max_places: int | None = None,
        max_queries_per_place: int | None = None,
        write_csv: bool = False,
    ) -> "Settings":
        """Carga `.env` y aplica argumentos explicitos con mayor prioridad."""
        load_dotenv()
        api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
        if not api_key or api_key == "REEMPLAZAR_CON_TU_CLAVE":
            raise ConfigurationError(
                "Falta YOUTUBE_API_KEY. Definala en el entorno o en un archivo .env local."
            )
        env_catalog = os.getenv(
            "YOUTUBE_CATALOG_PATH",
            "config/catalogo_municipios_turisticos_espana_youtube.xlsx",
        )
        env_output = os.getenv("YOUTUBE_OUTPUT_DIR", "output")
        try:
            resolved_limit = max_places if max_places is not None else int(
                os.getenv("YOUTUBE_MAX_PLACES", "5")
            )
        except ValueError as exc:
            raise ConfigurationError("YOUTUBE_MAX_PLACES debe ser un entero positivo.") from exc
        if resolved_limit < 1:
            raise ConfigurationError("YOUTUBE_MAX_PLACES debe ser un entero positivo.")
        if max_queries_per_place is not None and max_queries_per_place < 1:
            raise ConfigurationError("--max-queries-per-place debe ser positivo.")
        return cls(
            api_key=api_key,
            catalog_path=catalog_path or Path(env_catalog),
            output_dir=output_dir or Path(env_output),
            max_places=resolved_limit,
            max_queries_per_place=max_queries_per_place,
            write_csv=write_csv,
        )

