# Logan AI — OBD Driver

"""
Driver de acesso ao hardware OBD-II via python-obd.
Nenhum Worker acessa o OBD diretamente — recebem dados publicados por este Driver.
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.base_driver import BaseDriver
from core.config_manager import ConfigManager
from core.constants import (
    CHANNEL_OBD_TELEMETRY,
    EVENT_OBD_CONNECTED,
    EVENT_OBD_DATA,
    EVENT_OBD_DISCONNECTED,
    OBD_DEFAULT_BAUDRATE,
    OBD_DEFAULT_PORT,
    OBD_HEARTBEAT_INTERVAL_S,
    OBD_POLLING_INTERVAL_S,
    STREAM_STATE_CHANGES,
)
from core.enums import DriverState
from core.event_bus import EventBus
from core.exceptions import OBDConnectionError
from core.logger import get_logger
from core.models.obd_data import OBDReading

logger = get_logger("driver.obd")

# Comandos OBD que serão monitorados
OBD_WATCHED_COMMANDS = [
    "COOLANT_TEMP",
    "INTAKE_TEMP",
    "RPM",
    "SPEED",
    "THROTTLE_POS",
    "FUEL_LEVEL",
    "ENGINE_LOAD",
    "INTAKE_PRESSURE",
    "MAF",
    "O2_B1S1",
    "CONTROL_MODULE_VOLTAGE",
    "TIMING_ADVANCE",
    "SHORT_FUEL_TRIM_1",
    "LONG_FUEL_TRIM_1",
]


class OBDDriver(BaseDriver):
    """Driver OBD-II usando python-obd com modo assíncrono.

    Conecta ao adaptador OBD-II via USB, configura watches para
    os comandos desejados, e publica os dados no Event Bus.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(name="obd", event_bus=event_bus, config=config)
        self._connection: Any = None  # obd.Async
        self._port = config.obd_port
        self._baudrate = config.get("logan.obd_baudrate", OBD_DEFAULT_BAUDRATE)
        self._polling_task: asyncio.Task | None = None
        self._latest_readings: dict[str, OBDReading] = {}

    async def connect(self) -> None:
        """Conecta ao adaptador OBD-II."""
        try:
            import obd

            self._logger.info(
                f"Conectando ao OBD-II em {self._port}",
                extra={"port": self._port, "baudrate": self._baudrate},
            )

            portstr = None if self._port == "auto" else self._port
            
            # Usa obd.Async para leitura não-bloqueante
            self._connection = obd.Async(
                portstr=portstr,
                baudrate=self._baudrate,
                fast=True,
                timeout=10,
            )

            if self._connection.is_connected():
                self._logger.info("OBD-II conectado com sucesso")

                # Configura watches
                await self._setup_watches()

                # Inicia loop de publicação
                self._connection.start()
                self._polling_task = asyncio.create_task(self._publish_loop())

                # Publica evento de conexão
                await self._publish_data(
                    event_type=EVENT_OBD_CONNECTED,
                    data={
                        "port": self._port,
                        "protocol": str(self._connection.protocol_name()),
                        "supported_commands": len(self._connection.supported_commands),
                    },
                    stream=STREAM_STATE_CHANGES,
                )
            else:
                raise OBDConnectionError(
                    f"Não foi possível conectar ao OBD em {self._port}"
                )

        except ImportError:
            self._logger.warning(
                "Biblioteca python-obd não instalada. "
                "Instale com: pip install obd"
            )
            raise OBDConnectionError("python-obd não instalado")

        except Exception as e:
            raise OBDConnectionError(f"Erro na conexão OBD: {e}") from e

    async def disconnect(self) -> None:
        """Desconecta do OBD-II."""
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()

        if self._connection:
            try:
                self._connection.stop()
                self._connection.close()
            except Exception as e:
                self._logger.warning(f"Erro ao desconectar OBD: {e}")

        self._connection = None
        self._latest_readings.clear()

        # Publica evento de desconexão
        try:
            await self._publish_data(
                event_type=EVENT_OBD_DISCONNECTED,
                data={"reason": "driver_stopped"},
                stream=STREAM_STATE_CHANGES,
            )
        except Exception:
            pass

    async def is_connected(self) -> bool:
        """Verifica se o OBD está conectado."""
        return (
            self._connection is not None
            and self._connection.is_connected()
        )

    async def _setup_watches(self) -> None:
        """Configura os comandos OBD para monitoramento contínuo."""
        import obd

        for cmd_name in OBD_WATCHED_COMMANDS:
            try:
                cmd = getattr(obd.commands, cmd_name, None)
                if cmd and cmd in self._connection.supported_commands:
                    self._connection.watch(
                        cmd,
                        callback=lambda response, name=cmd_name: self._on_reading(
                            name, response
                        ),
                    )
                    self._logger.debug(f"Watch configurado: {cmd_name}")
                else:
                    self._logger.debug(f"Comando não suportado: {cmd_name}")
            except Exception as e:
                self._logger.warning(f"Erro ao configurar watch {cmd_name}: {e}")

    def _on_reading(self, command_name: str, response: Any) -> None:
        """Callback chamado quando uma leitura OBD é recebida."""
        if response.is_null():
            return

        reading = OBDReading(
            command=command_name,
            value=response.value.magnitude if hasattr(response.value, "magnitude") else response.value,
            unit=str(response.value.units) if hasattr(response.value, "units") else "",
            is_valid=not response.is_null(),
        )
        self._latest_readings[command_name] = reading

    async def _publish_loop(self) -> None:
        """Loop que publica readings consolidadas no Event Bus."""
        try:
            while self._state == DriverState.CONNECTED:
                if self._latest_readings:
                    # Publica snapshot via Pub/Sub (alta frequência, transiente)
                    readings_data = {
                        name: reading.to_dict()
                        for name, reading in self._latest_readings.items()
                    }
                    await self._publish_data(
                        event_type=EVENT_OBD_DATA,
                        data={"readings": readings_data},
                    )

                await asyncio.sleep(OBD_POLLING_INTERVAL_S)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._logger.error(f"Erro no loop de publicação OBD: {e}", exc_info=True)
            self._state = DriverState.ERROR

    def get_latest_reading(self, command: str) -> OBDReading | None:
        """Retorna a leitura mais recente de um comando (para diagnóstico)."""
        return self._latest_readings.get(command)
