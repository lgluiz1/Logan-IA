# Logan AI — Base Worker

"""
Classe base abstrata para todos os Workers do sistema.
Fornece lifecycle management, error handling, health reporting e acesso ao Event Bus.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from core.config_manager import ConfigManager
from core.constants import STREAM_STATE_CHANGES
from core.enums import WorkerState
from core.event_bus import EventBus
from core.exceptions import CriticalError, RecoverableError
from core.logger import get_logger
from core.models.event import LoganEvent


class BaseWorker(ABC):
    """Classe base para todos os Workers do Logan AI.

    Todo Worker deve:
    - Herdar desta classe
    - Implementar `handle_event()`
    - Registrar suas assinaturas em `_setup_subscriptions()`

    O Worker NUNCA chama outro Worker diretamente.
    Toda comunicação ocorre via Event Bus.
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
        self._logger = get_logger(name)
        self._state = WorkerState.IDLE
        self._task: asyncio.Task | None = None
        self._health_ok = True
        self._error_count = 0
        self._max_errors = 5
        self._retry_delay = 2.0

    # ──────────────────────────────────────────────
    # Properties
    # ──────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> WorkerState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == WorkerState.RUNNING

    @property
    def is_paused(self) -> bool:
        return self._state == WorkerState.PAUSED

    # ──────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────

    async def start(self) -> None:
        """Inicia o Worker."""
        self._logger.info(f"Iniciando worker: {self._name}")
        await self._setup_subscriptions()
        await self._on_start()
        await self._set_state(WorkerState.RUNNING)
        self._logger.info(f"Worker iniciado: {self._name}")

    async def stop(self) -> None:
        """Para o Worker graciosamente."""
        self._logger.info(f"Parando worker: {self._name}")
        await self._on_stop()
        if self._task and not self._task.done():
            self._task.cancel()
        await self._set_state(WorkerState.STOPPED)

    async def pause(self) -> None:
        """Pausa o Worker (e.g., quando OBD desconecta)."""
        if self._state == WorkerState.RUNNING:
            self._logger.info(f"Pausando worker: {self._name}")
            await self._on_pause()
            await self._set_state(WorkerState.PAUSED)

    async def resume(self) -> None:
        """Retoma o Worker após pausa."""
        if self._state == WorkerState.PAUSED:
            self._logger.info(f"Retomando worker: {self._name}")
            await self._on_resume()
            await self._set_state(WorkerState.RUNNING)

    # ──────────────────────────────────────────────
    # Abstract methods
    # ──────────────────────────────────────────────

    @abstractmethod
    async def handle_event(self, event: LoganEvent) -> None:
        """Processa um evento recebido.

        Cada Worker implementa sua lógica específica aqui.
        Este método NUNCA deve chamar outro Worker diretamente.

        Args:
            event: Evento recebido do Event Bus.
        """
        ...

    @abstractmethod
    async def _setup_subscriptions(self) -> None:
        """Registra assinaturas no Event Bus.

        Cada Worker declara em quais canais/streams está interessado.
        """
        ...

    # ──────────────────────────────────────────────
    # Hooks para subclasses (opcionais)
    # ──────────────────────────────────────────────

    async def _on_start(self) -> None:
        """Hook chamado durante start(). Override opcional."""
        pass

    async def _on_stop(self) -> None:
        """Hook chamado durante stop(). Override opcional."""
        pass

    async def _on_pause(self) -> None:
        """Hook chamado durante pause(). Override opcional."""
        pass

    async def _on_resume(self) -> None:
        """Hook chamado durante resume(). Override opcional."""
        pass

    # ──────────────────────────────────────────────
    # Safe event handling
    # ──────────────────────────────────────────────

    async def _safe_handle_event(self, event: LoganEvent) -> None:
        """Wrapper seguro para handle_event com tratamento de erros.

        Nunca deixa uma exceção matar o Worker silenciosamente.
        Publica eventos de erro no Event Bus para rastreamento.
        """
        if self._state == WorkerState.PAUSED:
            self._logger.debug(f"Evento ignorado (pausado): {event.event_type}")
            return

        if self._state != WorkerState.RUNNING:
            return

        try:
            await self.handle_event(event)
            self._error_count = 0  # Reset no sucesso

        except RecoverableError as e:
            self._error_count += 1
            self._logger.warning(
                f"Erro recuperável: {e}",
                extra={
                    "worker": self._name,
                    "event_type": event.event_type,
                    "error_count": self._error_count,
                },
            )
            if self._error_count < self._max_errors:
                await asyncio.sleep(self._retry_delay)
                await self._safe_handle_event(event)  # Retry
            else:
                await self._enter_error_state(str(e))

        except CriticalError as e:
            self._logger.critical(
                f"Erro crítico: {e}",
                extra={"worker": self._name},
                exc_info=True,
            )
            await self._publish_error("critical", str(e))
            await self._enter_error_state(str(e))

        except Exception as e:
            self._error_count += 1
            self._logger.error(
                f"Erro inesperado: {e}",
                extra={
                    "worker": self._name,
                    "event_type": event.event_type,
                },
                exc_info=True,
            )
            if self._error_count >= self._max_errors:
                await self._enter_error_state(str(e))

    async def _enter_error_state(self, error_msg: str) -> None:
        """Entra em estado de erro."""
        self._logger.error(f"Worker entrando em estado ERROR: {error_msg}")
        await self._set_state(WorkerState.ERROR)
        await self._publish_error("error", error_msg)
        self._health_ok = False

    # ──────────────────────────────────────────────
    # Publicação de eventos (atalhos)
    # ──────────────────────────────────────────────

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        priority: int = 0,
        stream: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Publica um evento no Event Bus.

        Args:
            event_type: Tipo do evento.
            payload: Dados do evento.
            priority: Prioridade.
            stream: Stream para publicação confiável (opcional).
            correlation_id: ID de correlação.
        """
        event = LoganEvent(
            event_type=event_type,
            source=self._name,
            payload=payload,
            priority=priority,
            correlation_id=correlation_id,
        )
        await self._event_bus.publish(event, stream=stream)

    async def _publish_error(self, severity: str, message: str) -> None:
        """Publica evento de erro do Worker."""
        await self.publish(
            event_type="system.worker_error",
            payload={
                "worker": self._name,
                "error": message,
                "severity": severity,
                "state": self._state.value,
            },
            priority=85,
            stream=STREAM_STATE_CHANGES,
        )

    async def _set_state(self, new_state: WorkerState) -> None:
        """Atualiza estado e publica evento de mudança."""
        old_state = self._state
        self._state = new_state

        if old_state != new_state:
            await self.publish(
                event_type="worker.state_change",
                payload={
                    "worker": self._name,
                    "old_state": old_state.value,
                    "new_state": new_state.value,
                },
                stream=STREAM_STATE_CHANGES,
            )

    # ──────────────────────────────────────────────
    # Health Check
    # ──────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Verifica se o Worker está saudável."""
        return self._health_ok and self._state in (
            WorkerState.RUNNING,
            WorkerState.PAUSED,
            WorkerState.IDLE,
        )
