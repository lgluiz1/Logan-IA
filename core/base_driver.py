# Logan AI — Base Driver

"""
Classe base abstrata para todos os Drivers do sistema.
Drivers acessam hardware (OBD, ESP32, USB, GPS, Bluetooth).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

from core.config_manager import ConfigManager
from core.enums import DriverState
from core.event_bus import EventBus
from core.exceptions import ConnectionLostError, DriverInitError
from core.logger import get_logger
from core.models.event import LoganEvent


class BaseDriver(ABC):
    """Classe base para todos os Drivers de hardware do Logan AI.

    Todo Driver deve:
    - Herdar desta classe
    - Implementar connect(), disconnect(), is_connected()
    - Publicar dados no Event Bus (nunca retornar dados diretamente)

    Os Workers NUNCA acessam hardware diretamente.
    Recebem dados publicados pelo Driver via Event Bus.
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
        self._logger = get_logger(f"driver.{name}")
        self._state = DriverState.DISCONNECTED
        self._reconnect_task: asyncio.Task | None = None
        self._max_reconnect_attempts = 10
        self._reconnect_delay = 5.0

    # ──────────────────────────────────────────────
    # Properties
    # ──────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> DriverState:
        return self._state

    # ──────────────────────────────────────────────
    # Abstract methods
    # ──────────────────────────────────────────────

    @abstractmethod
    async def connect(self) -> None:
        """Conecta ao dispositivo de hardware."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Desconecta do dispositivo."""
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        """Verifica se o dispositivo está conectado."""
        ...

    # ──────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────

    async def start(self) -> None:
        """Inicia o Driver (conecta ao hardware)."""
        self._logger.info(f"Iniciando driver: {self._name}")
        self._state = DriverState.CONNECTING
        try:
            await self.connect()
            await self._setup_subscriptions()
            self._state = DriverState.CONNECTED
            self._logger.info(f"Driver conectado: {self._name}")
            await self._publish_state_change()
        except Exception as e:
            self._state = DriverState.ERROR
            self._logger.error(
                f"Falha ao iniciar driver {self._name}: {e}",
                exc_info=True,
            )
            raise DriverInitError(
                f"Falha ao iniciar driver {self._name}: {e}"
            ) from e

    async def _setup_subscriptions(self) -> None:
        """Registra assinaturas no Event Bus. Override opcional."""
        pass

    async def _safe_handle_event(self, event: LoganEvent) -> None:
        """Wrapper seguro para handle_event com tratamento de erros."""
        try:
            if hasattr(self, "handle_event"):
                await self.handle_event(event)
        except Exception as e:
            self._logger.error(
                f"Erro inesperado ao processar evento {event.event_type}: {e}",
                exc_info=True,
            )

    async def stop(self) -> None:
        """Para o Driver (desconecta do hardware)."""
        self._logger.info(f"Parando driver: {self._name}")
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        await self.disconnect()
        self._state = DriverState.DISCONNECTED
        await self._publish_state_change()

    async def reconnect(self) -> None:
        """Tenta reconectar ao dispositivo com backoff."""
        self._state = DriverState.RECONNECTING
        await self._publish_state_change()

        for attempt in range(1, self._max_reconnect_attempts + 1):
            self._logger.info(
                f"Tentativa de reconexão {attempt}/{self._max_reconnect_attempts}",
                extra={"driver": self._name},
            )
            try:
                await self.disconnect()
                await asyncio.sleep(self._reconnect_delay)
                await self.connect()
                self._state = DriverState.CONNECTED
                self._logger.info(f"Reconexão bem-sucedida: {self._name}")
                await self._publish_state_change()
                return
            except Exception as e:
                self._logger.warning(
                    f"Reconexão falhou (tentativa {attempt}): {e}",
                    extra={"driver": self._name},
                )
                # Backoff exponencial: 5s, 10s, 20s, ...
                await asyncio.sleep(self._reconnect_delay * (2 ** (attempt - 1)))

        self._state = DriverState.ERROR
        self._logger.error(
            f"Todas as tentativas de reconexão falharam: {self._name}"
        )
        await self._publish_state_change()

    # ──────────────────────────────────────────────
    # Event publishing
    # ──────────────────────────────────────────────

    async def _publish_data(
        self,
        event_type: str,
        data: dict[str, Any],
        priority: int = 0,
        stream: str | None = None,
    ) -> None:
        """Publica dados do hardware no Event Bus.

        Args:
            event_type: Tipo do evento.
            data: Dados do hardware.
            priority: Prioridade do evento.
            stream: Stream para publicação confiável.
        """
        event = LoganEvent(
            event_type=event_type,
            source=f"driver.{self._name}",
            payload=data,
            priority=priority,
        )
        await self._event_bus.publish(event, stream=stream)

    async def _publish_state_change(self) -> None:
        """Publica mudança de estado do Driver."""
        event = LoganEvent(
            event_type=f"driver.{self._name}.state",
            source=f"driver.{self._name}",
            payload={
                "driver": self._name,
                "state": self._state.value,
            },
        )
        from core.constants import STREAM_STATE_CHANGES
        await self._event_bus.publish(event, stream=STREAM_STATE_CHANGES)

    # ──────────────────────────────────────────────
    # Health Check
    # ──────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Verifica se o Driver está saudável."""
        return self._state == DriverState.CONNECTED and await self.is_connected()
