# Logan AI — Mock ESP32 Driver

import asyncio
from typing import Any

from core.base_driver import BaseDriver
from core.config_manager import ConfigManager
from core.enums import DriverState, LEDPattern
from core.event_bus import EventBus


class MockESP32Driver(BaseDriver):
    """Mock do Driver ESP32 para testes."""

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(name="esp32", event_bus=event_bus, config=config)
        self._connected = False
        self.last_led_pattern: LEDPattern = LEDPattern.OFF
        self.audio_played: list[bytes] = []

    async def connect(self) -> None:
        self._connected = True
        self._state = DriverState.CONNECTED

    async def disconnect(self) -> None:
        self._connected = False
        self._state = DriverState.DISCONNECTED

    async def is_connected(self) -> bool:
        return self._connected

    async def set_led(self, pattern: LEDPattern) -> None:
        self.last_led_pattern = pattern

    async def play_audio(self, audio_data: bytes) -> None:
        self.audio_played.append(audio_data)

    async def stop_audio(self) -> None:
        pass

    async def set_volume(self, level: int) -> None:
        pass

    async def start_mic(self) -> None:
        pass

    async def stop_mic(self) -> None:
        pass
