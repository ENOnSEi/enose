"""
Contrato formal para generadores de informes de ejecución.

El pipeline solo depende de este protocolo, no de un formato concreto.
Para añadir un nuevo formato de salida (ej: HTML, PDF, notebook) basta con
implementar este protocolo sin tocar el orquestador (model/trainer.py).
"""

from typing import Protocol, runtime_checkable
from pathlib import Path

from spec.schemas.execution_report import ExecutionReport


@runtime_checkable
class ReportGeneratorProtocol(Protocol):
    """Interfaz mínima de un generador de informes."""

    def generate(self, report: ExecutionReport) -> Path:
        """
        Materializa un ExecutionReport a disco.

        Parámetros
        ----------
        report : datos completos de la ejecución ya validados.

        Retorna
        -------
        Path al artefacto principal generado (ej: el informe.md).
        """
        ...
