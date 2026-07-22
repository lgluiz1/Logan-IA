# Logan AI — Modelo de Evento

"""
Modelo de dados central do sistema: LoganEvent.
Todo dado que transita pelo Event Bus é encapsulado nesta estrutura.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=False, slots=True)
class LoganEvent:
    """
    Evento que transita pelo Event Bus.

    Attributes:
        event_id: Identificador único UUID do evento.
        event_type: Tipo do evento (e.g., "alert.temperature").
        source: Componente que originou o evento (e.g., "temperature_worker").
        timestamp: Unix timestamp da criação.
        priority: Prioridade de 0 a 100 (maior = mais urgente).
        payload: Dados do evento (dicionário livre).
        correlation_id: ID para rastreamento de cadeia de eventos.
        ttl: Time-to-live em segundos (evento expira após TTL).
        metadata: Metadados opcionais extras.
    """

    event_type: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    correlation_id: str | None = None
    ttl: int = 60
    metadata: dict[str, Any] | None = None

    def is_expired(self) -> bool:
        """Verifica se o evento expirou com base no TTL."""
        return (time.time() - self.timestamp) > self.ttl

    def to_dict(self) -> dict[str, Any]:
        """Serializa o evento para dicionário."""
        return asdict(self)

    def to_json(self) -> str:
        """Serializa o evento para JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoganEvent:
        """Reconstrói um evento a partir de dicionário."""
        return cls(**{k: v for k, v in data.items() if k in cls.__slots__})

    @classmethod
    def from_json(cls, json_str: str) -> LoganEvent:
        """Reconstrói um evento a partir de JSON string."""
        return cls.from_dict(json.loads(json_str))

    def with_correlation(self, parent_event: LoganEvent) -> LoganEvent:
        """Cria uma cópia do evento com correlation_id herdado do evento pai."""
        self.correlation_id = parent_event.correlation_id or parent_event.event_id
        return self

    def __lt__(self, other: LoganEvent) -> bool:
        """Comparação para uso em heapq (menor prioridade sai primeiro).

        Invertemos porque heapq é min-heap, mas queremos maior prioridade primeiro.
        """
        if self.priority != other.priority:
            return self.priority > other.priority  # Maior prioridade = mais urgente
        return self.timestamp < other.timestamp  # Mais antigo primeiro em empate
