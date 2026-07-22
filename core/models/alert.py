# Logan AI — Modelo de Alerta

"""
Modelo de dados para alertas gerados pelos Workers.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from core.enums import AlertCategory, AlertLevel


@dataclass(slots=True)
class Alert:
    """Alerta gerado por um Worker ao detectar anomalia.

    Attributes:
        alert_id: ID único do alerta.
        category: Categoria do alerta (temperatura, combustível, etc).
        level: Nível de gravidade.
        message: Mensagem descritiva.
        value: Valor que disparou o alerta.
        threshold: Limiar que foi excedido.
        source: Worker que gerou.
        timestamp: Momento da criação.
        acknowledged: Se foi reconhecido pelo usuário.
        resolved: Se a condição foi resolvida.
        metadata: Dados extras.
    """

    category: AlertCategory
    level: AlertLevel
    message: str
    value: float | None = None
    threshold: float | None = None
    source: str = ""
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False
    resolved: bool = False
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
