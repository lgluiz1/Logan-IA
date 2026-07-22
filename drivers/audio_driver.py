# Logan AI — Audio Driver

"""
Driver de áudio para reprodução e captura local (fallback sem ESP32).
"""

from __future__ import annotations

from typing import Any

from core.base_driver import BaseDriver
from core.config_manager import ConfigManager
from core.constants import EVENT_AUDIO_PLAY, EVENT_AUDIO_STOP, STREAM_VOICE
from core.event_bus import EventBus
from core.logger import get_logger
from core.models.event import LoganEvent

logger = get_logger("driver.audio")


class AudioDriver(BaseDriver):
    """Driver de áudio local (fallback quando ESP32 não está disponível).

    Usa sounddevice ou pyaudio para reprodução e captura de áudio
    diretamente na Orange Pi ou PC de desenvolvimento.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(name="audio", event_bus=event_bus, config=config)
        self._output_device: Any = None
        self._input_device: Any = None

    async def _setup_subscriptions(self) -> None:
        """Assina eventos de áudio."""
        self._event_bus.subscribe_stream(STREAM_VOICE, self._safe_handle_event)
        self._event_bus.subscribe(EVENT_AUDIO_STOP, self._safe_handle_event)

    async def handle_event(self, event: LoganEvent) -> None:
        """Processa comandos de áudio recebidos pelo Event Bus."""
        if event.event_type == EVENT_AUDIO_PLAY:
            audio_hex = event.payload.get("audio_hex")
            sample_rate = event.payload.get("sample_rate", 24000)
            if audio_hex:
                audio_data = bytes.fromhex(audio_hex)
                await self.play(audio_data, sample_rate)
        elif event.event_type == EVENT_AUDIO_STOP:
            await self.stop_playback()

    async def connect(self) -> None:
        """Inicializa dispositivos de áudio."""
        try:
            import sounddevice as sd

            devices = sd.query_devices()
            self._logger.info(f"Dispositivos de áudio encontrados: {len(devices)}")
            self._output_device = sd.default.device[1]
            self._input_device = sd.default.device[0]
            self._logger.info("Audio Driver conectado (modo local)")

        except ImportError:
            self._logger.warning(
                "sounddevice não instalado. "
                "Instale com: pip install sounddevice"
            )

    async def disconnect(self) -> None:
        """Libera dispositivos de áudio."""
        self._output_device = None
        self._input_device = None

    async def is_connected(self) -> bool:
        """Verifica se há dispositivos de áudio disponíveis."""
        return self._output_device is not None

    async def play(self, audio_data: bytes, sample_rate: int = 24000) -> None:
        """Reproduz áudio localmente."""
        try:
            import numpy as np
            import sounddevice as sd

            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            audio_float = audio_array.astype(np.float32) / 32768.0
            sd.play(audio_float, samplerate=sample_rate, blocking=False)
        except Exception as e:
            self._logger.error(f"Erro ao reproduzir áudio: {e}")

    async def stop_playback(self) -> None:
        """Para reprodução de áudio."""
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
