# Logan AI — User Speech Worker

"""
Worker de gravação de voz e transcrição (STT).
Inicia gravação ao receber o evento voice.wake_word, converte para WAV,
chama o Whisper no Docker e publica a transcrição.
"""

from __future__ import annotations

import asyncio
import collections
import random
import time
import unicodedata

import aiohttp
import numpy as np
import sounddevice as sd

from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.constants import STREAM_COMMANDS
from core.event_bus import EventBus
from core.models.event import LoganEvent


class UserSpeechWorker(BaseWorker):
    """Worker para gravação e transcrição de áudio do usuário com ativação inteligente."""

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="user_speech_worker",
            event_bus=event_bus,
            config=config,
        )
        self._whisper_url = config.get("system.whisper_url", "http://localhost:9000")
        if "whisper" in self._whisper_url and "localhost" not in self._whisper_url:
            self._whisper_url = "http://localhost:9000"

        self._sample_rate = 16000
        self._duration = 4.0  # Tempo para gravação do comando (4 segundos)
        self._threshold = float(config.get("voices.wake_word.threshold", 0.025))
        self._cooldown_seconds = 7.0
        self._last_trigger_time = 0.0

        self._running_listen = False
        self._listen_task = None
        self._loop = None

    async def _setup_subscriptions(self) -> None:
        """O fluxo é ativo pelo microfone, não necessita assinaturas de streams."""
        pass

    async def handle_event(self, event: LoganEvent) -> None:
        """Não consome eventos externos."""
        pass

    async def start(self) -> None:
        """Inicia monitoramento do microfone."""
        await super().start()
        self._loop = asyncio.get_running_loop()
        self._running_listen = True
        self._listen_task = asyncio.create_task(self._listen_loop())
        self._logger.info("UserSpeechWorker iniciado com monitoramento VAD + Palavra de Ativação")

    async def stop(self) -> None:
        """Para monitoramento."""
        self._running_listen = False
        await super().stop()

    async def _listen_loop(self) -> None:
        """Inicia a thread de leitura do microfone."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._stream_read_loop)

    def _stream_read_loop(self) -> None:
        """Loop síncrono rodando na thread pool monitorando o RMS e pre-roll."""
        buffer = collections.deque(maxlen=40000)  # Buffer de 2.5s a 16kHz

        try:
            # Abre o InputStream de forma persistente
            stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype=np.int16,
            )
            with stream:
                self._logger.info(f"Microfone escutando... Threshold RMS: {self._threshold}")
                while self._running_listen:
                    # Lê chunks de 1024 amostras
                    chunk, _ = stream.read(1024)
                    buffer.extend(chunk[:, 0])

                    # Calcula o RMS normalizado
                    chunk_float = chunk[:, 0].astype(np.float32) / 32768.0
                    rms = np.sqrt(np.mean(chunk_float**2))

                    current_time = time.time()
                    if rms > self._threshold and (current_time - self._last_trigger_time) > self._cooldown_seconds:
                        self._last_trigger_time = current_time
                        self._logger.info(f"VAD ativado! Volume: {rms:.4f}. Gravando trecho de ativação...")

                        # Grava o restante para completar 2.5 segundos (28.800 amostras extras)
                        remaining = 28800
                        chunk_size = 1024
                        for _ in range(0, remaining, chunk_size):
                            extra_chunk, _ = stream.read(chunk_size)
                            buffer.extend(extra_chunk[:, 0])

                        # Extrai as 40.000 amostras acumuladas (2.5 segundos)
                        trigger_audio = np.array(buffer, dtype=np.int16)

                        # Despacha o processamento do gatilho para o event loop assíncrono
                        asyncio.run_coroutine_threadsafe(
                            self._process_trigger_audio(trigger_audio, stream),
                            self._loop
                        )

                        # Cooldown local para não re-saturar o buffer enquanto o usuário fala
                        time.sleep(self._cooldown_seconds)
                        buffer.clear()

        except Exception as e:
            self._logger.error(f"Erro no dispositivo de microfone: {e}")
            self._logger.warning("Microfone indisponível. Teste via API de comando de texto.")

    async def _process_trigger_audio(self, audio_data: np.ndarray, stream: sd.InputStream) -> None:
        """Processa o trecho inicial e checa pela palavra 'Logan' via Whisper."""
        try:
            self._logger.info("Enviando trecho inicial ao Whisper...")
            wav_bytes = self._pcm_to_wav(audio_data.tobytes(), self._sample_rate)
            text = await self._send_to_whisper(wav_bytes)

            if not text:
                return

            self._logger.info(f"Whisper transcreveu: '{text}'")
            normalized = self._normalize_text(text)

            # Verifica a palavra-chave "Logan" (ou variações fonéticas próximas)
            cmd_keywords = ["erro", "falha", "problema", "temperatura", "arrefecimento", "combustivel", "gasolina", "etanol", "tanque", "rpm", "rotacao", "giro", "status", "como voce esta"]

            is_direct_wake = "logan" in normalized
            is_fuzzy_wake = any(w in normalized for w in ["logo", "loga", "logam", "lugar", "lacra", "louca", "louco"])
            is_short_wake = any(normalized == w for w in ["logo", "loga", "logam", "lacra"])

            if is_direct_wake or (is_fuzzy_wake and any(w in normalized for w in cmd_keywords)) or is_short_wake:
                self._logger.info("Palavra de ativação 'Logan' (ou variação fonética) confirmada!")

                # 1. Envia sinal de interrupção imediata da fala do Logan
                event = LoganEvent(
                    event_type="voice.wake_word",
                    source=self._name,
                    payload={"rms": 0.5},
                    priority=100,
                )
                await self._event_bus.publish(event, stream=STREAM_COMMANDS)

                # 2. Verifica se a pergunta já veio inteira na mesma frase
                if any(w in normalized for w in cmd_keywords):
                    self._logger.info("Frase completa detectada. Processando diretamente...")
                    user_input_event = LoganEvent(
                        event_type="voice.user_input",
                        source=self._name,
                        payload={"text": text},
                        priority=60,
                    )
                    await self._event_bus.publish(user_input_event, stream=STREAM_COMMANDS)
                else:
                    # 3. Se só falou "Logan", fala a saudação e ouve a pergunta
                    self._logger.info("Apenas palavra de ativação identificada. Falando saudação...")

                    driver_name = self._config.driver_name
                    greetings = [
                        f"Sim, {driver_name}?",
                        f"Pois não, {driver_name}?",
                        f"Na escuta, {driver_name}.",
                        f"Diga, {driver_name}.",
                        f"Estou ouvindo, {driver_name}."
                    ]
                    greeting_text = random.choice(greetings)

                    # Sintetiza saudação
                    greeting_audio = await self._synthesize_greeting(greeting_text)
                    if greeting_audio:
                        await asyncio.to_thread(self._play_audio_sync, greeting_audio)
                    else:
                        # Fallback se falhar
                        await asyncio.to_thread(self._play_beep_sync)

                    # Grava 4.0 segundos adicionais do mesmo stream
                    self._logger.info(f"Gravando {self._duration} segundos de comando...")
                    command_audio = await asyncio.to_thread(
                        self._record_mic_sync,
                        stream,
                        int(self._duration * self._sample_rate)
                    )

                    self._logger.info("Gravação de comando concluída. Enviando para Whisper...")
                    cmd_wav = self._pcm_to_wav(command_audio.tobytes(), self._sample_rate)
                    cmd_text = await self._send_to_whisper(cmd_wav)

                    if cmd_text:
                        self._logger.info(f"Comando recebido: '{cmd_text}'")
                        user_input_event = LoganEvent(
                            event_type="voice.user_input",
                            source=self._name,
                            payload={"text": cmd_text},
                            priority=60,
                        )
                        await self._event_bus.publish(user_input_event, stream=STREAM_COMMANDS)
            else:
                self._logger.debug("Palavra de ativação não detectada no trecho.")

        except Exception as e:
            self._logger.error(f"Erro ao processar áudio do gatilho: {e}", exc_info=True)

    def _record_mic_sync(self, stream: sd.InputStream, samples: int) -> np.ndarray:
        """Lê amostras do microfone diretamente do stream persistente aberto."""
        data, _ = stream.read(samples)
        return data[:, 0]

    def _play_beep_sync(self) -> None:
        """Toca um sinal sonoro duplo (rising pitch) indicando que o Logan está ouvindo."""
        try:
            sample_rate = 16000
            # Beep 1
            t1 = np.linspace(0, 0.07, int(sample_rate * 0.07), False)
            beep1 = np.sin(880.0 * t1 * 2 * np.pi) * 0.25

            # Silêncio curto
            silence = np.zeros(int(sample_rate * 0.04))

            # Beep 2
            t2 = np.linspace(0, 0.11, int(sample_rate * 0.11), False)
            beep2 = np.sin(1050.0 * t2 * 2 * np.pi) * 0.25

            beep_array = np.concatenate([beep1, silence, beep2])
            sd.play(beep_array, samplerate=sample_rate, blocking=True)
        except Exception as e:
            self._logger.error(f"Erro ao tocar beep: {e}")

    def _pcm_to_wav(self, pcm_data: bytes, sample_rate: int = 16000, channels: int = 1, bits_per_sample: int = 16) -> bytes:
        """Adiciona cabeçalho WAV aos dados PCM."""
        byte_rate = sample_rate * channels * (bits_per_sample // 8)
        block_align = channels * (bits_per_sample // 8)

        header = bytearray(44)
        header[0:4] = b'RIFF'
        header[4:8] = (36 + len(pcm_data)).to_bytes(4, 'little')
        header[8:12] = b'WAVE'
        header[12:16] = b'fmt '
        header[16:20] = (16).to_bytes(4, 'little')
        header[20:22] = (1).to_bytes(2, 'little')
        header[22:24] = (channels).to_bytes(2, 'little')
        header[24:28] = (sample_rate).to_bytes(4, 'little')
        header[28:32] = (byte_rate).to_bytes(4, 'little')
        header[32:34] = (block_align).to_bytes(2, 'little')
        header[34:36] = (bits_per_sample).to_bytes(2, 'little')
        header[36:40] = b'data'
        header[40:44] = (len(pcm_data)).to_bytes(4, 'little')

        return bytes(header) + pcm_data

    async def _send_to_whisper(self, wav_bytes: bytes) -> str | None:
        """Envia o arquivo WAV via HTTP para o contêiner Whisper."""
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                data = aiohttp.FormData()
                data.add_field(
                    "audio",
                    wav_bytes,
                    filename="audio.wav",
                    content_type="audio/wav"
                )
                async with session.post(f"{self._whisper_url}/transcribe", data=data) as response:
                    if response.status == 200:
                        res = await response.json()
                        return str(res.get("text", "")).strip()
                    return None
        except Exception as e:
            self._logger.error(f"Erro de conexão com Whisper: {e}")
            return None

    def _normalize_text(self, text: str) -> str:
        """Remove pontuação e acentuação para facilitação de match."""
        text = text.lower().strip()
        return "".join(
            c for c in unicodedata.normalize("NFD", text)
            if unicodedata.category(c) != "Mn"
        )

    async def _synthesize_greeting(self, text: str) -> bytes | None:
        """Sintetiza uma saudação rápida usando Kokoro TTS."""
        try:
            url = f"{self._config.get('system.kokoro_url', 'http://localhost:8880')}/v1/audio/speech"
            if "kokoro" in url and "localhost" not in url:
                url = "http://localhost:8880/v1/audio/speech"

            voice = self._config.get("voices.tts.default_voice", "pm_alex")
            speed = float(self._config.get("voices.tts.speed", 0.85))

            payload = {
                "model": "kokoro",
                "input": text,
                "voice": voice,
                "speed": speed,
                "response_format": "pcm",
            }

            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session, session.post(url, json=payload) as response:
                if response.status == 200:
                    return await response.read()
            return None
        except Exception as e:
            self._logger.error(f"Erro ao sintetizar saudação: {e}")
            return None

    def _play_audio_sync(self, audio_data: bytes) -> None:
        """Reproduz áudio PCM bruto de forma síncrona."""
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            audio_float = audio_array.astype(np.float32) / 32768.0
            sd.play(audio_float, samplerate=24000, blocking=True)
        except Exception as e:
            self._logger.error(f"Erro ao reproduzir áudio da saudação: {e}")
