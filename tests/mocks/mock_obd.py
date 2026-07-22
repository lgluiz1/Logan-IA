# Logan AI — Mock OBD Driver

import asyncio
from typing import Any

from core.base_driver import BaseDriver
from core.config_manager import ConfigManager
from core.constants import EVENT_OBD_CONNECTED, EVENT_OBD_DATA, EVENT_OBD_DISCONNECTED, STREAM_STATE_CHANGES
from core.enums import DriverState
from core.event_bus import EventBus
from core.models.obd_data import OBDReading


class MockOBDDriver(BaseDriver):
    """Mock do Driver OBD-II para testes.

    Permite injetar leituras programaticamente sem hardware.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(name="obd", event_bus=event_bus, config=config)
        self._connected = False

    async def connect(self) -> None:
        """Simula conexão."""
        self._connected = True
        self._state = DriverState.CONNECTED
        await self._publish_data(
            event_type=EVENT_OBD_CONNECTED,
            data={"port": "MOCK", "protocol": "MOCK_PROTOCOL", "supported_commands": 10},
            stream=STREAM_STATE_CHANGES,
        )

    async def disconnect(self) -> None:
        """Simula desconexão."""
        self._connected = False
        self._state = DriverState.DISCONNECTED
        await self._publish_data(
            event_type=EVENT_OBD_DISCONNECTED,
            data={"reason": "mock_disconnect"},
            stream=STREAM_STATE_CHANGES,
        )

    async def is_connected(self) -> bool:
        return self._connected

    async def inject_reading(self, command: str, value: Any, unit: str = "") -> None:
        """Injeta uma leitura simulada no Event Bus."""
        if not self._connected:
            return

        reading = OBDReading(
            command=command,
            value=value,
            unit=unit,
            is_valid=True,
        )

        readings_data = {command: reading.to_dict()}
        await self._publish_data(
            event_type=EVENT_OBD_DATA,
            data={"readings": readings_data},
        )
