# Logan AI — Scheduler

"""
Scheduler com prioridade absoluta.
Controla a fila de mensagens de voz com:
- Deduplicação
- Cooldown por categoria
- Agrupamento de alertas
- Cancelamento de alertas resolvidos
- Interrupção para prioridades altas
"""

from __future__ import annotations

import asyncio
import heapq
import time

from core.config_manager import ConfigManager
from core.constants import (
    PRIORITY_INTERRUPT_THRESHOLD,
    SCHEDULER_DEDUP_WINDOW_S,
    SCHEDULER_DEFAULT_COOLDOWN_S,
    SCHEDULER_GROUP_THRESHOLD,
    SCHEDULER_MAX_QUEUE_SIZE,
    STREAM_ALERTS,
    STREAM_COMMANDS,
    STREAM_VOICE,
)
from core.enums import AlertCategory
from core.event_bus import EventBus
from core.logger import get_logger
from core.models.event import LoganEvent
from core.models.voice_message import VoiceMessage

logger = get_logger("scheduler")


class Scheduler:
    """Scheduler central com Priority Queue para o Logan AI.

    Pipeline de 7 estágios:
    1. Deduplicação — evento idêntico nos últimos 60s?
    2. Cooldown — categoria tem cooldown ativo?
    3. Priorização — atribui prioridade
    4. Agrupamento — 3+ eventos similares pendentes?
    5. Cancelamento — condição ainda válida?
    6. Enfileirar — Voice Queue
    7. Interrupção — prioridade ≥ 90?
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        self._event_bus = event_bus
        self._config = config

        # Priority queue (min-heap, LoganEvent tem __lt__ invertido)
        self._queue: list[VoiceMessage] = []

        # Deduplicação: hash do evento → timestamp
        self._seen_events: dict[str, float] = {}

        # Cooldown por categoria: categoria → último timestamp de fala
        self._cooldowns: dict[str, float] = {}

        # Eventos pendentes por categoria para agrupamento
        self._pending_by_category: dict[str, list[VoiceMessage]] = {}

        # Callback para quando mensagem está pronta
        self._on_message_ready: asyncio.Event = asyncio.Event()

        # Controle
        self._running = False
        self._current_speaking = False

    async def start(self) -> None:
        """Inicia o Scheduler e registra assinaturas no Event Bus."""
        self._running = True

        # Escuta streams de alertas e comandos
        self._event_bus.subscribe_stream(STREAM_ALERTS, self._on_alert_event)
        self._event_bus.subscribe_stream(STREAM_COMMANDS, self._on_command_event)

        logger.info("Scheduler iniciado")

    async def stop(self) -> None:
        """Para o Scheduler."""
        self._running = False
        self._on_message_ready.set()  # Desbloqueia qualquer await
        logger.info("Scheduler parado")

    # ──────────────────────────────────────────────
    # Event Handlers
    # ──────────────────────────────────────────────

    async def _on_alert_event(self, event: LoganEvent) -> None:
        """Processa evento de alerta (vindo dos Workers)."""
        if event.event_type == "voice.response":
            await self._enqueue_voice_response(event)
        else:
            await self._process_event(event)

    async def _on_command_event(self, event: LoganEvent) -> None:
        """Processa evento de comando (wake word, user speech, etc)."""
        # Comandos de voz têm tratamento especial
        if event.event_type == "voice.wake_word":
            await self._handle_wake_word(event)
        elif event.event_type == "voice.response":
            await self._enqueue_voice_response(event)
        else:
            await self._process_event(event)

    # ──────────────────────────────────────────────
    # Pipeline de 7 estágios
    # ──────────────────────────────────────────────

    async def _process_event(self, event: LoganEvent) -> None:
        """Pipeline principal de processamento de eventos."""

        # 1. Deduplicação
        event_hash = self._compute_event_hash(event)
        if self._is_duplicate(event_hash):
            logger.info(
                f"Evento duplicado descartado: {event.event_type}",
                extra={"event_type": event.event_type},
            )
            return

        # 2. Cooldown
        category = event.payload.get("category", "general")
        if self._is_on_cooldown(category):
            logger.info(
                f"Evento em cooldown descartado: {event.event_type} ({category})",
                extra={"category": category},
            )
            return

        # 3. Extrair mensagem de voz do payload
        text = event.payload.get("voice_message", "")
        if not text:
            return

        voice_msg = VoiceMessage(
            text=text,
            priority=event.priority,
            category=AlertCategory(category) if category in AlertCategory.__members__.values() else AlertCategory.GENERAL,
            source=event.source,
            cancellable=event.payload.get("cancellable", False),
            cancel_condition=event.payload.get("cancel_condition"),
        )

        # 4. Agrupamento
        if category not in self._pending_by_category:
            self._pending_by_category[category] = []
        self._pending_by_category[category].append(voice_msg)

        if len(self._pending_by_category[category]) >= SCHEDULER_GROUP_THRESHOLD:
            # Agrupa múltiplos alertas da mesma categoria
            grouped_msg = self._group_messages(category)
            await self._enqueue(grouped_msg)
        else:
            # Agenda individual (com delay para possível agrupamento)
            await asyncio.sleep(0.5)  # Pequena janela para agrupamento
            if voice_msg in self._pending_by_category.get(category, []):
                self._pending_by_category[category].remove(voice_msg)
                await self._enqueue(voice_msg)

    async def _enqueue(self, message: VoiceMessage) -> None:
        """Estágio 6: Enfileira mensagem na Voice Queue."""
        if len(self._queue) >= SCHEDULER_MAX_QUEUE_SIZE:
            # Remove item de menor prioridade
            self._queue.sort()
            self._queue.pop()
            logger.warning("Voice Queue cheia, removido item de menor prioridade")

        heapq.heappush(self._queue, message)
        self._on_message_ready.set()

        logger.info(
            f"Mensagem enfileirada: prioridade={message.priority}, "
            f"categoria={message.category}",
            extra={
                "priority": message.priority,
                "category": message.category.value,
                "queue_size": len(self._queue),
            },
        )

        # 7. Interrupção
        if message.priority >= PRIORITY_INTERRUPT_THRESHOLD:
            await self._interrupt_current_speech()

    async def _enqueue_voice_response(self, event: LoganEvent) -> None:
        """Enfileira resposta de voz diretamente (do AI Gateway ou Workers)."""
        text = event.payload.get("text", "")
        if not text:
            return

        voice_msg = VoiceMessage(
            text=text,
            priority=event.priority,
            category=AlertCategory(
                event.payload.get("category", "general")
            ),
            source=event.source,
        )
        await self._enqueue(voice_msg)

    # ──────────────────────────────────────────────
    # Dequeue
    # ──────────────────────────────────────────────

    async def dequeue(self) -> VoiceMessage | None:
        """Retira a próxima mensagem da fila (maior prioridade).

        Bloqueia até haver uma mensagem disponível.

        Returns:
            Próxima mensagem ou None se scheduler parou.
        """
        while self._running:
            if self._queue:
                message = heapq.heappop(self._queue)

                # 5. Verificação de cancelamento
                if message.cancellable and message.cancel_condition:
                    # Verifica se a condição de cancelamento foi atendida
                    # (implementação simplificada — em produção, checaria estado atual)
                    pass

                # Atualiza cooldown
                self._cooldowns[message.category.value] = time.time()

                return message

            self._on_message_ready.clear()
            await self._on_message_ready.wait()

        return None

    # ──────────────────────────────────────────────
    # Wake Word (prioridade máxima)
    # ──────────────────────────────────────────────

    async def _handle_wake_word(self, event: LoganEvent) -> None:
        """Trata detecção de wake word — interrompe tudo imediatamente."""
        logger.info("Wake word detectado — interrompendo tudo")
        await self._interrupt_current_speech()

        # Publica evento para LED e Speech Worker
        await self._event_bus.publish_to_stream(
            stream=STREAM_VOICE,
            event_type="audio.stop",
            payload={"reason": "wake_word"},
            source="scheduler",
            priority=100,
        )

    async def _interrupt_current_speech(self) -> None:
        """Interrompe qualquer fala em andamento."""
        if self._current_speaking:
            await self._event_bus.publish_to_stream(
                stream=STREAM_VOICE,
                event_type="audio.stop",
                payload={"reason": "interrupt"},
                source="scheduler",
                priority=100,
            )
            self._current_speaking = False

    def set_speaking(self, is_speaking: bool) -> None:
        """Atualiza flag de fala em andamento."""
        self._current_speaking = is_speaking

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    def _compute_event_hash(self, event: LoganEvent) -> str:
        """Computa hash do evento para deduplicação."""
        key_parts = [
            event.event_type,
            event.source,
            str(event.payload.get("category", "")),
            str(event.payload.get("level", "")),
        ]
        return ":".join(key_parts)

    def _is_duplicate(self, event_hash: str) -> bool:
        """Verifica se evento é duplicata dentro da janela."""
        now = time.time()

        # Limpa entradas expiradas
        expired = [
            k for k, v in self._seen_events.items()
            if now - v > SCHEDULER_DEDUP_WINDOW_S
        ]
        for k in expired:
            del self._seen_events[k]

        if event_hash in self._seen_events:
            return True

        self._seen_events[event_hash] = now
        return False

    def _is_on_cooldown(self, category: str) -> bool:
        """Verifica se categoria está em cooldown."""
        last_time = self._cooldowns.get(category)
        if last_time is None:
            return False

        cooldown = self._config.get(
            f"priorities.cooldowns.{category}",
            SCHEDULER_DEFAULT_COOLDOWN_S,
        )
        return (time.time() - last_time) < cooldown

    def _group_messages(self, category: str) -> VoiceMessage:
        """Agrupa múltiplas mensagens da mesma categoria em uma."""
        messages = self._pending_by_category.pop(category, [])
        if not messages:
            return VoiceMessage(text="", category=AlertCategory.GENERAL)

        # Usa a maior prioridade
        max_priority = max(m.priority for m in messages)

        # Cria texto agrupado
        grouped_text = (
            f"Tenho {len(messages)} observações sobre "
            f"{category} para compartilhar com você."
        )

        return VoiceMessage(
            text=grouped_text,
            priority=max_priority,
            category=AlertCategory(category) if category in AlertCategory.__members__.values() else AlertCategory.GENERAL,
            source="scheduler",
        )

    @property
    def queue_size(self) -> int:
        """Tamanho atual da fila."""
        return len(self._queue)

    @property
    def is_running(self) -> bool:
        return self._running
