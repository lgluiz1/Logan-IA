# Logan AI — Recovery Worker

"""
Gerencia tentativas automáticas de reconexão quando um Driver perde conexão.
"""

from __future__ import annotations

import asyncio

from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.constants import (
    OBD_MAX_RETRY_ATTEMPTS,
    OBD_RETRY_DELAY_S,
    STREAM_STATE_CHANGES,
)
from core.event_bus import EventBus
from core.models.event import LoganEvent


class RecoveryWorker(BaseWorker):
    """Worker de recuperação automática de conexões.

    Quando um Driver perde conexão, este Worker:
    1. Aguarda um delay antes de tentar
    2. Tenta reconectar com backoff exponencial
    3. Publica resultado no Event Bus
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="recovery_worker",
            event_bus=event_bus,
            config=config,
        )
        self._active_recoveries: dict[str, asyncio.Task] = {}

    async def _setup_subscriptions(self) -> None:
        """Escuta pedidos de recovery."""
        self._event_bus.subscribe_stream(
            STREAM_STATE_CHANGES, self._safe_handle_event
        )

    async def handle_event(self, event: LoganEvent) -> None:
        """Processa pedidos de recovery."""
        if event.event_type != "recovery.request":
            return

        target = event.payload.get("target", "")
        reason = event.payload.get("reason", "unknown")

        self._logger.info(
            f"Pedido de recovery recebido: target={target}, reason={reason}"
        )

        # Evita múltiplas tentativas simultâneas para o mesmo target
        if target in self._active_recoveries:
            task = self._active_recoveries[target]
            if not task.done():
                self._logger.info(f"Recovery já em andamento para: {target}")
                return

        # Inicia recovery em background
        task = asyncio.create_task(self._attempt_recovery(target, reason))
        self._active_recoveries[target] = task

    async def _attempt_recovery(self, target: str, reason: str) -> None:
        """Tenta recuperar a conexão com backoff exponencial."""
        max_attempts = OBD_MAX_RETRY_ATTEMPTS
        base_delay = OBD_RETRY_DELAY_S

        for attempt in range(1, max_attempts + 1):
            delay = base_delay * (2 ** (attempt - 1))
            delay = min(delay, 120.0)  # Cap em 2 minutos

            self._logger.info(
                f"Recovery tentativa {attempt}/{max_attempts} para {target} "
                f"(aguardando {delay:.0f}s)"
            )

            await asyncio.sleep(delay)

            # Publica evento pedindo ao Driver para reconectar
            await self.publish(
                event_type=f"driver.{target}.reconnect",
                payload={
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                },
                stream=STREAM_STATE_CHANGES,
            )

            # Aguarda um pouco para ver se a reconexão funcionou
            await asyncio.sleep(5.0)

            # Nota: em uma implementação mais robusta, verificaríamos
            # se recebemos um evento de reconexão bem-sucedida
            # Por ora, o Recovery Worker apenas emite os pedidos

        self._logger.warning(
            f"Todas as tentativas de recovery falharam para: {target}"
        )

        # Notifica falha completa
        await self.publish(
            event_type="recovery.failed",
            payload={
                "target": target,
                "attempts": max_attempts,
            },
            stream=STREAM_STATE_CHANGES,
            priority=85,
        )

    async def _on_stop(self) -> None:
        """Cancela todas as recoveries em andamento."""
        for _target, task in self._active_recoveries.items():
            if not task.done():
                task.cancel()
        self._active_recoveries.clear()
