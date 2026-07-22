# Logan AI — Logger Estruturado

"""
Logger centralizado com saída estruturada em JSON.
Todos os componentes usam este logger para rastreabilidade.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Formata logs em JSON estruturado para fácil parsing e indexação."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self._format_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Adiciona campos extras se presentes
        if hasattr(record, "worker"):
            log_entry["worker"] = record.worker
        if hasattr(record, "driver"):
            log_entry["driver"] = record.driver
        if hasattr(record, "correlation_id"):
            log_entry["correlation_id"] = record.correlation_id
        if hasattr(record, "event_type"):
            log_entry["event_type"] = record.event_type
        if hasattr(record, "action"):
            log_entry["action"] = record.action
        if hasattr(record, "value"):
            log_entry["value"] = record.value
        if hasattr(record, "threshold"):
            log_entry["threshold"] = record.threshold

        # Adiciona informação de exceção se presente
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        # Qualquer extra genérico
        extra = getattr(record, "_extra", None)
        if extra and isinstance(extra, dict):
            log_entry["extra"] = extra

        return json.dumps(log_entry, ensure_ascii=False, default=str)

    @staticmethod
    def _format_timestamp(created: float) -> str:
        """Formata timestamp em ISO 8601."""
        return time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.localtime(created)
        ) + f".{int((created % 1) * 1000):03d}Z"


class HumanFormatter(logging.Formatter):
    """Formatter legível para desenvolvimento (console)."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[41m",  # Red background
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))

        # Componente
        component = ""
        if hasattr(record, "worker"):
            component = f"[{record.worker}]"
        elif hasattr(record, "driver"):
            component = f"[{record.driver}]"
        else:
            component = f"[{record.name.split('.')[-1]}]"

        msg = f"{color}{ts} {record.levelname:<8}{self.RESET} {component:<25} {record.getMessage()}"

        # Valores extras relevantes
        extras = []
        for attr in ("value", "threshold", "action", "event_type"):
            val = getattr(record, attr, None)
            if val is not None:
                extras.append(f"{attr}={val}")
        if extras:
            msg += f"  ({', '.join(extras)})"

        if record.exc_info and record.exc_info[0] is not None:
            msg += f"\n  ⚠ {record.exc_info[0].__name__}: {record.exc_info[1]}"

        return msg


def setup_logger(
    name: str = "logan",
    level: str = "INFO",
    log_dir: str | None = None,
    json_output: bool = True,
    console_output: bool = True,
) -> logging.Logger:
    """Configura e retorna o logger principal do Logan AI.

    Args:
        name: Nome do logger.
        level: Nível mínimo de log.
        log_dir: Diretório para arquivo de log (None = sem arquivo).
        json_output: Se True, saída JSON estruturada no arquivo.
        console_output: Se True, saída legível no console.

    Returns:
        Logger configurado.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    # Console handler (legível para humanos)
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(HumanFormatter())
        logger.addHandler(console_handler)

    # File handler (JSON estruturado)
    if log_dir and json_output:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_path / "logan.log",
            encoding="utf-8",
        )
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)

    return logger


def get_logger(component: str) -> logging.Logger:
    """Obtém um logger filho para um componente específico.

    Args:
        component: Nome do componente (e.g., "temperature_worker").

    Returns:
        Logger filho configurado.
    """
    return logging.getLogger(f"logan.{component}")
