"""Contrato desacoplado para permitir un futuro escritor de Azure SQL."""

from __future__ import annotations

from typing import Any, Protocol


class ResultWriter(Protocol):
    """Contrato minimo para persistir las salidas de una ejecucion."""

    def write_table(
        self, name: str, records: list[dict[str, Any]], columns: list[str]
    ) -> None:
        """Persiste una tabla de registros."""
        ...

    def write_json(self, name: str, payload: dict[str, Any]) -> None:
        """Persiste un documento JSON."""
        ...

