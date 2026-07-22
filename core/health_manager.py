# Logan AI — Health Manager

"""
Health Manager monitora todos os componentes e reinicia Workers com falha.
Publica métricas para Prometheus e gerencia watchdogs.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from core.base_driver import BaseDriver
from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.constants import (
    HEALTH_CHECK_INTERVAL_S,
    HEALTH_MAX_FAILURES,
    HEALTH_RESTART_DELAY_S,
    STREAM_STATE_CHANGES,
)
from core.enums import WorkerState
from core.event_bus import EventBus
from core.logger import get_logger
from core.models.event import LoganEvent

logger = get_logger("health_manager")


class HealthManager:
    """Gerencia a saúde de todos os componentes do Logan AI.

    Responsabilidades:
    - Executa health checks periódicos
    - Reinicia Workers com falha
    - Publica métricas de saúde
    - Mantém contagem de falhas por componente
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        self._event_bus = event_bus
        self._config = config
        self._workers: dict[str, BaseWorker] = {}
        self._drivers: dict[str, BaseDriver] = {}
        self._failure_counts: dict[str, int] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._check_interval = HEALTH_CHECK_INTERVAL_S

    def register_worker(self, worker: BaseWorker) -> None:
        """Registra um Worker para monitoramento."""
        self._workers[worker.name] = worker
        self._failure_counts[worker.name] = 0
        logger.debug(f"Worker registrado para monitoramento: {worker.name}")

    def register_driver(self, driver: BaseDriver) -> None:
        """Registra um Driver para monitoramento."""
        self._drivers[driver.name] = driver
        self._failure_counts[driver.name] = 0
        logger.debug(f"Driver registrado para monitoramento: {driver.name}")

    async def start(self) -> None:
        """Inicia o loop de health checks."""
        self._running = True

        # Escuta eventos de erro de Workers
        self._event_bus.subscribe_stream(
            STREAM_STATE_CHANGES, self._on_state_change
        )

        self._task = asyncio.create_task(self._health_check_loop())
        logger.info("Health Manager iniciado")

    async def stop(self) -> None:
        """Para o Health Manager."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Health Manager parado")

    async def _health_check_loop(self) -> None:
        """Loop periódico de health checks."""
        try:
            while self._running:
                await self._check_all()
                await asyncio.sleep(self._check_interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Erro no health check loop: {e}", exc_info=True)

    async def _check_all(self) -> None:
        """Executa health check em todos os componentes."""
        # Check Event Bus
        eb_ok = await self._event_bus.health_check()
        if not eb_ok:
            logger.critical("Event Bus não está respondendo!")

        # Check Workers
        for name, worker in self._workers.items():
            try:
                is_healthy = await worker.health_check()
                if not is_healthy:
                    self._failure_counts[name] = self._failure_counts.get(name, 0) + 1
                    logger.warning(
                        f"Worker unhealthy: {name} "
                        f"(falhas: {self._failure_counts[name]})",
                    )
                    if self._failure_counts[name] >= HEALTH_MAX_FAILURES:
                        await self._restart_worker(name)
                else:
                    self._failure_counts[name] = 0
            except Exception as e:
                logger.error(f"Erro ao checar worker {name}: {e}")

        # Check Drivers
        for name, driver in self._drivers.items():
            try:
                is_healthy = await driver.health_check()
                if not is_healthy:
                    self._failure_counts[name] = self._failure_counts.get(name, 0) + 1
                    logger.warning(f"Driver unhealthy: {name}")
            except Exception as e:
                logger.error(f"Erro ao checar driver {name}: {e}")

    async def _restart_worker(self, name: str) -> None:
        """Tenta reiniciar um Worker com falha."""
        worker = self._workers.get(name)
        if not worker:
            return

        logger.warning(f"Reiniciando worker: {name}")
        try:
            await worker.stop()
            await asyncio.sleep(HEALTH_RESTART_DELAY_S)
            await worker.start()
            self._failure_counts[name] = 0
            logger.info(f"Worker reiniciado com sucesso: {name}")
        except Exception as e:
            logger.error(f"Falha ao reiniciar worker {name}: {e}", exc_info=True)

    async def _on_state_change(self, event: LoganEvent) -> None:
        """Trata eventos de mudança de estado."""
        if event.event_type == "system.worker_error":
            worker_name = event.payload.get("worker", "unknown")
            severity = event.payload.get("severity", "error")
            logger.warning(
                f"Erro reportado por worker: {worker_name} ({severity})",
                extra=event.payload,
            )

    def get_status(self) -> dict[str, Any]:
        """Retorna status de saúde de todos os componentes."""
        return {
            "workers": {
                name: {
                    "state": w.state.value,
                    "failures": self._failure_counts.get(name, 0),
                }
                for name, w in self._workers.items()
            },
            "drivers": {
                name: {
                    "state": d.state.value,
                    "failures": self._failure_counts.get(name, 0),
                }
                for name, d in self._drivers.items()
            },
        }
