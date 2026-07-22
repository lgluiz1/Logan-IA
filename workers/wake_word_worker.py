# Logan AI — Wake Word Worker (Placeholder)

"""
Worker de ativação por voz.
Desativado nesta versão unificada pois o UserSpeechWorker gerencia o VAD e a validação.
"""

from __future__ import annotations

from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.event_bus import EventBus
from core.models.event import LoganEvent


class WakeWordWorker(BaseWorker):
    """Placeholder inofensivo para manter compatibilidade com registros no supervisor."""

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="wake_word_worker",
            event_bus=event_bus,
            config=config,
        )

    async def _setup_subscriptions(self) -> None:
        pass

    async def handle_event(self, event: LoganEvent) -> None:
        pass

    async def start(self) -> None:
        await super().start()
        self._logger.info("WakeWordWorker inicializado (Placeholder - inativo).")

    async def stop(self) -> None:
        await super().stop()
