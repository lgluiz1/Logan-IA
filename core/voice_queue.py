# Logan AI — Voice Queue

"""
Fila de voz com prioridade que alimenta o Voice Worker.
Age como intermediário entre o Scheduler e o TTS.
"""

from __future__ import annotations

import asyncio

from core.logger import get_logger
from core.models.voice_message import VoiceMessage
from core.scheduler import Scheduler

logger = get_logger("voice_queue")


class VoiceQueue:
    """Fila de voz que consome do Scheduler e alimenta o Voice Worker.

    A VoiceQueue roda em loop, consumindo mensagens do Scheduler
    e disponibilizando-as para o Voice Worker via asyncio.Queue.
    """

    def __init__(self, scheduler: Scheduler) -> None:
        self._scheduler = scheduler
        self._output_queue: asyncio.Queue[VoiceMessage] = asyncio.Queue(maxsize=20)
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Inicia o loop de consumo do Scheduler."""
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        logger.info("Voice Queue iniciada")

    async def stop(self) -> None:
        """Para a Voice Queue."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Voice Queue parada")

    async def get_next_message(self) -> VoiceMessage:
        """Obtém a próxima mensagem para o Voice Worker.

        Bloqueia até haver uma mensagem disponível.

        Returns:
            Próxima mensagem de voz.
        """
        return await self._output_queue.get()

    async def _consume_loop(self) -> None:
        """Loop que consome do Scheduler e coloca na output queue."""
        try:
            while self._running:
                message = await self._scheduler.dequeue()
                if message and message.text:
                    await self._output_queue.put(message)
                    logger.debug(
                        f"Mensagem transferida para output: p={message.priority}",
                        extra={
                            "priority": message.priority,
                            "category": message.category.value,
                        },
                    )
        except asyncio.CancelledError:
            logger.debug("Voice Queue consume loop cancelado")
        except Exception as e:
            logger.error(f"Erro no Voice Queue consume loop: {e}", exc_info=True)

    @property
    def pending_count(self) -> int:
        """Número de mensagens aguardando no output."""
        return self._output_queue.qsize()
