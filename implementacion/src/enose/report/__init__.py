"""Generación de informes de ejecución del pipeline (capa Dev)."""

from .generator import MarkdownReportGenerator, build_execution_report

__all__ = ["MarkdownReportGenerator", "build_execution_report"]
