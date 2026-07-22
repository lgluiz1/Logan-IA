# Logan AI — ESP32 Driver

"""
Driver de comunicação com o ESP32-S3 via USB Serial.
Responsável por enviar áudio, comandos de LED e receber stream de microfone.
"""

from __future__ import annotations

import asyncio
import json
import struct
from enum import IntEnum
from typing import Any

from core.base_driver import BaseDriver
from core.config_manager import ConfigManager
from core.constants import ESP32_DEFAULT_BAUDRATE, ESP32_DEFAULT_PORT
from core.enums import DriverState, LEDPattern
from core.event_bus import EventBus
from core.logger import get_logger

logger = get_logger("driver.esp32")


class ESP32Command(IntEnum):
    """Comandos do protocolo ESP32."""

    PING = 0x01
    PONG = 0x02
    LED_SET = 0x10
    LED_PATTERN = 0x11
    AUDIO_PLAY = 0x20
    AUDIO_STOP = 0x21
    AUDIO_VOLUME = 0x22
    MIC_START = 0x30
    MIC_STOP = 0x31
    MIC_DATA = 0x32
    STATUS = 0x40
    RESET = 0xFF


# Protocolo de pacotes:
# [START_BYTE(1)] [COMMAND(1)] [LENGTH(2)] [PAYLOAD(N)] [CHECKSUM(1)]
START_BYTE = 0xAA
HEADER_SIZE = 4
MAX_PAYLOAD_SIZE = 4096


class ESP32Driver(BaseDriver):
    """Driver de comunicação com o ESP32-S3 via USB Serial.

    O ESP32 atua como satélite responsável apenas por:
    - Captura de áudio (microfones MEMS I2S)
    - Reprodução de áudio (alto-falante I2S)
    - Controle de LEDs (WS2812)
    - Sensores auxiliares

    Toda inteligência roda na Orange Pi.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(name="esp32", event_bus=event_bus, config=config)
        self._port = config.esp32_port
        self._baudrate = config.get("logan.esp32_baudrate", ESP32_DEFAULT_BAUDRATE)
        self._serial: Any = None  # serial.Serial
        self._reader_task: asyncio.Task | None = None
        self._audio_callback: Any = None

    async def connect(self) -> None:
        """Conecta ao ESP32 via USB Serial."""
        try:
            import serial_asyncio

            self._logger.info(
                f"Conectando ao ESP32 em {self._port}",
                extra={"port": self._port, "baudrate": self._baudrate},
            )

            reader, writer = await serial_asyncio.open_serial_connection(
                url=self._port,
                baudrate=self._baudrate,
            )
            self._serial = (reader, writer)

            # Envia ping para verificar conexão
            await self._send_command(ESP32Command.PING)

            # Inicia loop de leitura
            self._reader_task = asyncio.create_task(self._read_loop())

            self._logger.info("ESP32 conectado com sucesso")

        except ImportError:
            self._logger.warning(
                "Biblioteca pyserial-asyncio não instalada. "
                "Instale com: pip install pyserial-asyncio"
            )
            raise
        except Exception as e:
            self._logger.error(f"Erro ao conectar ESP32: {e}")
            raise

    async def disconnect(self) -> None:
        """Desconecta do ESP32."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()

        if self._serial:
            try:
                _, writer = self._serial
                writer.close()
            except Exception:
                pass
        self._serial = None

    async def is_connected(self) -> bool:
        """Verifica se o ESP32 está conectado."""
        return self._serial is not None

    # ──────────────────────────────────────────────
    # Comandos de saída
    # ──────────────────────────────────────────────

    async def set_led(self, pattern: LEDPattern) -> None:
        """Define o padrão de LED no ESP32."""
        await self._send_command(
            ESP32Command.LED_PATTERN,
            pattern.value.encode("utf-8"),
        )

    async def play_audio(self, audio_data: bytes) -> None:
        """Envia áudio para reprodução no ESP32.

        Args:
            audio_data: Dados de áudio PCM (16kHz, 16-bit, mono).
        """
        # Envia em chunks de MAX_PAYLOAD_SIZE
        for i in range(0, len(audio_data), MAX_PAYLOAD_SIZE):
            chunk = audio_data[i : i + MAX_PAYLOAD_SIZE]
            await self._send_command(ESP32Command.AUDIO_PLAY, chunk)
            await asyncio.sleep(0.01)  # Pequeno delay entre chunks

    async def stop_audio(self) -> None:
        """Para a reprodução de áudio."""
        await self._send_command(ESP32Command.AUDIO_STOP)

    async def set_volume(self, level: int) -> None:
        """Define o volume (0-100)."""
        await self._send_command(
            ESP32Command.AUDIO_VOLUME,
            bytes([max(0, min(100, level))]),
        )

    async def start_mic(self) -> None:
        """Inicia captura de áudio do microfone."""
        await self._send_command(ESP32Command.MIC_START)

    async def stop_mic(self) -> None:
        """Para captura de áudio do microfone."""
        await self._send_command(ESP32Command.MIC_STOP)

    # ──────────────────────────────────────────────
    # Protocolo
    # ──────────────────────────────────────────────

    async def _send_command(
        self, command: ESP32Command, payload: bytes = b""
    ) -> None:
        """Envia um comando para o ESP32.

        Formato do pacote:
        [0xAA] [CMD] [LEN_H] [LEN_L] [PAYLOAD...] [CHECKSUM]
        """
        if not self._serial:
            self._logger.warning("ESP32 não conectado, comando ignorado")
            return

        length = len(payload)
        header = struct.pack(
            "!BBH",
            START_BYTE,
            command,
            length,
        )

        # Checksum simples (XOR de todos os bytes)
        checksum = START_BYTE ^ command ^ (length >> 8) ^ (length & 0xFF)
        for b in payload:
            checksum ^= b
        checksum &= 0xFF

        packet = header + payload + bytes([checksum])

        try:
            _, writer = self._serial
            writer.write(packet)
            await writer.drain()
        except Exception as e:
            self._logger.error(f"Erro ao enviar comando ESP32: {e}")
            self._state = DriverState.ERROR

    async def _read_loop(self) -> None:
        """Loop de leitura de dados do ESP32."""
        try:
            reader, _ = self._serial

            while self._state in (DriverState.CONNECTED, DriverState.CONNECTING):
                # Lê header
                header = await asyncio.wait_for(
                    reader.readexactly(HEADER_SIZE),
                    timeout=10.0,
                )

                if header[0] != START_BYTE:
                    continue

                command = header[1]
                length = struct.unpack("!H", header[2:4])[0]

                # Lê payload + checksum
                if length > 0:
                    payload = await reader.readexactly(length)
                else:
                    payload = b""

                checksum = (await reader.readexactly(1))[0]

                # Processa comando recebido
                await self._handle_incoming(ESP32Command(command), payload)

        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            self._logger.warning("Timeout na leitura do ESP32")
        except Exception as e:
            self._logger.error(f"Erro no read loop ESP32: {e}", exc_info=True)

    async def _handle_incoming(
        self, command: ESP32Command, payload: bytes
    ) -> None:
        """Processa comando recebido do ESP32."""
        if command == ESP32Command.PONG:
            self._logger.debug("ESP32 PONG recebido")

        elif command == ESP32Command.MIC_DATA:
            # Áudio do microfone — publica no Event Bus
            await self._publish_data(
                event_type="esp32.mic_data",
                data={"audio_chunk": payload.hex()},
            )

        elif command == ESP32Command.STATUS:
            status = json.loads(payload.decode("utf-8"))
            self._logger.debug(f"ESP32 status: {status}")
