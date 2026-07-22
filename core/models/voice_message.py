# Logan AI — Modelo de Mensagem de Voz

"""
Modelo de dados para mensagens de voz que transitam pelo Voice Queue.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from core.enums import AlertCategory


@dataclass(slots=True)
class VoiceMessage:
    """Mensagem de voz para ser sintetizada e reproduzida.

    Attributes:
        message_id: ID único da mensagem.
        text: Texto para síntese TTS.
        priority: Prioridade de 0-100.
        category: Categoria para cooldown/agrupamento.
        source: Worker que gerou a mensagem.
        timestamp: Momento da criação.
        interrupt: Se deve interromper a fala atual.
        cancellable: Se pode ser cancelada se condição normalizar.
        cancel_condition: Tipo de evento que cancela esta mensagem.
        metadata: Dados extras.
    """

    text: str
    priority: int = 0
    category: AlertCategory = AlertCategory.GENERAL
    source: str = ""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    interrupt: bool = False
    cancellable: bool = False
    cancel_condition: str | None = None
    metadata: dict[str, Any] | None = None

    def __lt__(self, other: VoiceMessage) -> bool:
        """Comparação para heapq: maior prioridade primeiro."""
        if self.priority != other.priority:
            return self.priority > other.priority
        return self.timestamp < other.timestamp

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
