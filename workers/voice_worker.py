# Logan AI — Voice Worker

"""
Sintetiza texto em voz usando Kokoro TTS e gerencia a reprodução.
Seleciona variações de frases aleatoriamente a partir de JSONs.
"""

from __future__ import annotations

import asyncio

import aiohttp

from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.constants import (
    EVENT_AUDIO_PLAY,
    EVENT_AUDIO_STOP,
    STREAM_VOICE,
    TTS_DEFAULT_SPEED,
    TTS_DEFAULT_VOICE,
    TTS_SAMPLE_RATE,
)
from core.enums import LEDPattern
from core.event_bus import EventBus
from core.models.event import LoganEvent
from core.models.voice_message import VoiceMessage
from core.voice_queue import VoiceQueue


class VoiceWorker(BaseWorker):
    """Worker de síntese e reprodução de voz.

    Consome mensagens da Voice Queue, sintetiza via Kokoro TTS,
    e envia o áudio para reprodução no ESP32 ou localmente.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
        voice_queue: VoiceQueue,
    ) -> None:
        super().__init__(
            name="voice_worker",
            event_bus=event_bus,
            config=config,
        )
        self._voice_queue = voice_queue
        self._kokoro_url = config.kokoro_url
        self._voice = config.get("voices.tts.default_voice", TTS_DEFAULT_VOICE)
        self._speed = config.get("voices.tts.speed", TTS_DEFAULT_SPEED)
        self._is_speaking = False
        self._consume_task: asyncio.Task | None = None
        self._http_session: aiohttp.ClientSession | None = None

    async def _setup_subscriptions(self) -> None:
        """Escuta comandos de áudio (stop, etc)."""
        self._event_bus.subscribe_stream(STREAM_VOICE, self._safe_handle_event)

    async def _on_start(self) -> None:
        """Inicia consumo da Voice Queue e sessão HTTP."""
        self._http_session = aiohttp.ClientSession()
        self._consume_task = asyncio.create_task(self._consume_loop())

    async def _on_stop(self) -> None:
        """Para consumo e fecha sessão HTTP."""
        if self._consume_task and not self._consume_task.done():
            self._consume_task.cancel()
        if self._http_session:
            await self._http_session.close()

    async def handle_event(self, event: LoganEvent) -> None:
        """Processa comandos de áudio."""
        if event.event_type == EVENT_AUDIO_STOP:
            await self._interrupt()

    async def _consume_loop(self) -> None:
        """Loop de consumo da Voice Queue."""
        try:
            while self.is_running:
                message = await self._voice_queue.get_next_message()
                await self._speak(message)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._logger.error(f"Erro no consume loop: {e}", exc_info=True)

    async def _speak(self, message: VoiceMessage) -> None:
        """Sintetiza e reproduz uma mensagem de voz.

        Args:
            message: Mensagem a ser falada.
        """
        if not message.text.strip():
            return

        self._is_speaking = True

        # LED pulsando verde (falando)
        await self.publish(
            event_type="led.pattern",
            payload={"pattern": LEDPattern.PULSE_GREEN.value},
        )

        try:
            self._logger.info(
                f"Sintetizando: \"{message.text[:80]}...\"",
                extra={
                    "priority": message.priority,
                    "category": message.category.value,
                },
            )

            # Sintetiza via Kokoro TTS
            audio_data = await self._synthesize(message.text)

            if audio_data and self._is_speaking:
                # Envia áudio para reprodução
                await self.publish(
                    event_type=EVENT_AUDIO_PLAY,
                    payload={
                        "audio_hex": audio_data.hex(),
                        "sample_rate": TTS_SAMPLE_RATE,
                        "priority": message.priority,
                    },
                    stream=STREAM_VOICE,
                )

                # Aguarda duração estimada da fala
                duration = len(audio_data) / (TTS_SAMPLE_RATE * 2)  # 16-bit = 2 bytes
                await asyncio.sleep(duration)

        except Exception as e:
            self._logger.error(f"Erro ao sintetizar/reproduzir: {e}", exc_info=True)

        finally:
            self._is_speaking = False
            # LED volta ao normal
            await self.publish(
                event_type="led.pattern",
                payload={"pattern": LEDPattern.SOLID_GREEN.value},
            )

    async def _synthesize(self, text: str) -> bytes | None:
        """Sintetiza texto via Kokoro TTS API.

        Args:
            text: Texto para síntese.

        Returns:
            Dados de áudio (bytes) ou None em caso de erro.
        """
        if not self._http_session:
            return None

        try:
            # API compatível com OpenAI
            url = f"{self._kokoro_url}/v1/audio/speech"
            payload = {
                "model": "kokoro",
                "input": text,
                "voice": self._voice,
                "speed": self._speed,
                "response_format": "pcm",
            }

            async with self._http_session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=180)
            ) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    error = await response.text()
                    self._logger.error(
                        f"Kokoro TTS erro {response.status}: {error}"
                    )
                    return None

        except aiohttp.ClientError as e:
            self._logger.error(f"Erro de conexão com Kokoro TTS: {e}")
            return None
        except Exception as e:
            self._logger.error(f"Erro na síntese TTS: {e}", exc_info=True)
            return None

    async def _interrupt(self) -> None:
        """Interrompe a fala atual."""
        if self._is_speaking:
            self._is_speaking = False
            self._logger.info("Fala interrompida")
            # Envia comando de stop para o ESP32/Audio Driver
            await self.publish(
                event_type="esp32.audio_stop",
                payload={},
            )

    @property
    def is_speaking(self) -> bool:
        """Se está falando no momento."""
        return self._is_speaking
