# Logan AI — Base Service

"""
Classe base abstrata para Services.
Services são componentes compartilhados (AI Gateway, Knowledge Base, etc).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.config_manager import ConfigManager
from core.event_bus import EventBus
from core.logger import get_logger


class BaseService(ABC):
    """Classe base para Services do Logan AI.

    Services são singleton compartilhados entre Workers.
    Exemplos: AI Gateway, Knowledge Base, Memory, Phrase Selector.
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        self._name = name
        self._event_bus = event_bus
        self._config = config
        self._logger = get_logger(f"service.{name}")
        self._initialized = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @abstractmethod
    async def initialize(self) -> None:
        """Inicializa o serviço (chamado uma vez na startup)."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Encerra o serviço graciosamente."""
        ...

    async def health_check(self) -> bool:
        """Verifica se o serviço está saudável."""
        return self._initialized
