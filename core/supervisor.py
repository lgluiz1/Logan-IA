# Logan AI — Supervisor

"""
Supervisor é o orquestrador principal do Logan AI.
Inicializa todos os componentes, gerencia lifecycle e coordena shutdown.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any

from core.base_driver import BaseDriver
from core.base_worker import BaseWorker
from core.base_service import BaseService
from core.config_manager import ConfigManager
from core.constants import STREAM_STATE_CHANGES
from core.enums import SystemMode
from core.event_bus import EventBus
from core.health_manager import HealthManager
from core.logger import get_logger, setup_logger
from core.models.event import LoganEvent
from core.models.vehicle_state import VehicleState
from core.scheduler import Scheduler
from core.voice_queue import VoiceQueue

logger = get_logger("supervisor")


class Supervisor:
    """Orquestrador principal do Logan AI.

    Responsabilidades:
    - Inicializa e para todos os componentes na ordem correta
    - Mantém o VehicleState centralizado
    - Gerencia sinais de shutdown (SIGTERM, SIGINT)
    - Coordena o modo de operação do sistema
    """

    def __init__(self, config_dir: str | None = None) -> None:
        # Configuração
        self._config = ConfigManager(config_dir)
        self._config.load()

        # Componentes core
        self._event_bus: EventBus = EventBus(redis_url=self._config.redis_url)
        self._scheduler: Scheduler = Scheduler(event_bus=self._event_bus, config=self._config)
        self._voice_queue: VoiceQueue = VoiceQueue(scheduler=self._scheduler)
        self._health_manager: HealthManager = HealthManager(event_bus=self._event_bus, config=self._config)

        # Estado
        self._vehicle_state = VehicleState()
        self._mode = SystemMode.NORMAL
        self._running = False

        # Registros de componentes
        self._drivers: dict[str, BaseDriver] = {}
        self._workers: dict[str, BaseWorker] = {}
        self._services: dict[str, BaseService] = {}

    # ──────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────

    async def start(self) -> None:
        """Inicializa e inicia todo o sistema Logan AI."""
        logger.info("=" * 60)
        logger.info("  LOGAN AI v1.0 — Iniciando sistema")
        logger.info("=" * 60)

        try:
            # 1. Configurar Logger (configuração já carregada no __init__)
            setup_logger(
                level=self._config.log_level,
                log_dir=self._config.get("logan.log_dir"),
                json_output=self._config.environment != "development",
                console_output=True,
            )
            logger.info(
                f"Configuração carregada — Ambiente: {self._config.environment}"
            )
            logger.info(f"Motorista: {self._config.driver_name}")

            # 2. Conectar Event Bus
            await self._event_bus.connect(consumer_name="supervisor")

            # 3. Inicializar Scheduler
            await self._scheduler.start()

            # 4. Inicializar Voice Queue
            await self._voice_queue.start()

            # 5. Inicializar Health Manager (apenas logging setup)
            # a task start é feita no passo 8

            # 5b. Iniciar Serviços
            await self._start_services()

            # 6. Iniciar Drivers
            await self._start_drivers()

            # 7. Iniciar Workers
            await self._start_workers()

            # 8. Iniciar Health Manager
            await self._health_manager.start()

            # 9. Iniciar consumo de eventos
            await self._event_bus.start_consuming()

            # 10. Publicar evento de startup
            await self._event_bus.publish_to_stream(
                stream=STREAM_STATE_CHANGES,
                event_type="system.startup",
                payload={
                    "mode": self._mode.value,
                    "driver_name": self._config.driver_name,
                    "workers": list(self._workers.keys()),
                    "drivers": list(self._drivers.keys()),
                },
                source="supervisor",
            )

            self._running = True
            logger.info("=" * 60)
            logger.info("  LOGAN AI — Sistema iniciado com sucesso! ✓")
            logger.info("=" * 60)

        except Exception as e:
            logger.critical(f"Falha ao iniciar o sistema: {e}", exc_info=True)
            await self.stop()
            raise

    async def stop(self) -> None:
        """Para todo o sistema graciosamente."""
        logger.info("Logan AI — Iniciando shutdown...")
        self._running = False

        # Publicar evento de shutdown
        if self._event_bus and self._event_bus.is_running:
            try:
                await self._event_bus.publish_to_stream(
                    stream=STREAM_STATE_CHANGES,
                    event_type="system.shutdown",
                    payload={"reason": "graceful_shutdown"},
                    source="supervisor",
                )
            except Exception:
                pass

        # Para na ordem inversa da inicialização
        # Workers
        for name, worker in reversed(list(self._workers.items())):
            try:
                await worker.stop()
                logger.info(f"Worker parado: {name}")
            except Exception as e:
                logger.error(f"Erro ao parar worker {name}: {e}")

        # Drivers
        for name, driver in reversed(list(self._drivers.items())):
            try:
                await driver.stop()
                logger.info(f"Driver parado: {name}")
            except Exception as e:
                logger.error(f"Erro ao parar driver {name}: {e}")

        # Services
        for name, service in reversed(list(self._services.items())):
            try:
                await service.shutdown()
                logger.info(f"Serviço parado: {name}")
            except Exception as e:
                logger.error(f"Erro ao parar serviço {name}: {e}")

        # Health Manager
        if self._health_manager:
            await self._health_manager.stop()

        # Voice Queue
        if self._voice_queue:
            await self._voice_queue.stop()

        # Scheduler
        if self._scheduler:
            await self._scheduler.stop()

        # Event Bus (por último)
        if self._event_bus:
            await self._event_bus.disconnect()

        logger.info("Logan AI — Shutdown completo ✓")

    async def run_forever(self) -> None:
        """Roda o sistema até receber sinal de parada."""
        # Registra handlers de sinal
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except NotImplementedError:
                # Windows não suporta add_signal_handler para todos os sinais
                pass

        await self.start()

        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            if self._running:
                await self.stop()

    # ──────────────────────────────────────────────
    # Registro de componentes
    # ──────────────────────────────────────────────

    def register_driver(self, driver: BaseDriver) -> None:
        """Registra um Driver no sistema."""
        self._drivers[driver.name] = driver
        logger.debug(f"Driver registrado: {driver.name}")

    def register_worker(self, worker: BaseWorker) -> None:
        """Registra um Worker no sistema."""
        self._workers[worker.name] = worker
        logger.debug(f"Worker registrado: {worker.name}")

    def register_service(self, service: BaseService) -> None:
        """Registra um Serviço no sistema."""
        self._services[service.name] = service
        logger.debug(f"Serviço registrado: {service.name}")

    # ──────────────────────────────────────────────
    # Startup de componentes
    # ──────────────────────────────────────────────

    async def _start_drivers(self) -> None:
        """Inicia todos os Drivers registrados."""
        for name, driver in self._drivers.items():
            try:
                await driver.start()
                if self._health_manager:
                    self._health_manager.register_driver(driver)
                logger.info(f"Driver iniciado: {name}")
            except Exception as e:
                logger.error(f"Falha ao iniciar driver {name}: {e}")
                # Drivers podem falhar sem derrubar o sistema
                self._mode = SystemMode.DEGRADED

    async def _start_workers(self) -> None:
        """Inicia todos os Workers registrados."""
        for name, worker in self._workers.items():
            try:
                await worker.start()
                if self._health_manager:
                    self._health_manager.register_worker(worker)
                logger.info(f"Worker iniciado: {name}")
            except Exception as e:
                logger.error(f"Falha ao iniciar worker {name}: {e}")

    async def _start_services(self) -> None:
        """Inicia todos os Serviços registrados."""
        for name, service in self._services.items():
            try:
                await service.initialize()
                logger.info(f"Serviço iniciado: {name}")
            except Exception as e:
                logger.error(f"Falha ao iniciar serviço {name}: {e}")

    # ──────────────────────────────────────────────
    # Accessors
    # ──────────────────────────────────────────────

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def scheduler(self) -> Scheduler:
        return self._scheduler

    @property
    def voice_queue(self) -> VoiceQueue:
        return self._voice_queue

    @property
    def config(self) -> ConfigManager:
        return self._config

    @property
    def vehicle_state(self) -> VehicleState:
        return self._vehicle_state

    @property
    def mode(self) -> SystemMode:
        return self._mode

    @property
    def health_status(self) -> dict[str, Any]:
        if self._health_manager:
            return self._health_manager.get_status()
        return {}
