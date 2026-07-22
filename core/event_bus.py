# Logan AI — Event Bus

"""
Event Bus centralizado baseado em Redis Streams + Pub/Sub.

- Pub/Sub: eventos transientes de alta frequência (telemetria, heartbeats)
- Streams: eventos confiáveis que não podem ser perdidos (alertas, comandos)

Nenhum Worker se comunica diretamente com outro.
Toda comunicação passa pelo Event Bus.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Coroutine
from typing import Any

import redis.asyncio as aioredis

from core.constants import (
    ALL_STREAMS,
    REDIS_BLOCK_MS,
    REDIS_CONSUMER_GROUP,
    REDIS_DEFAULT_URL,
    REDIS_EVENT_PREFIX,
    REDIS_STREAM_MAX_LEN,
)
from core.exceptions import EventBusError, EventPublishError, EventSubscribeError
from core.logger import get_logger
from core.models.event import LoganEvent

logger = get_logger("event_bus")

# Type alias para callback de evento
EventCallback = Callable[[LoganEvent], Coroutine[Any, Any, None]]


class EventBus:
    """Event Bus centralizado do Logan AI.

    Gerencia toda a comunicação entre componentes via Redis.
    Suporta tanto Pub/Sub (fire-and-forget) quanto Streams (reliable).
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url or REDIS_DEFAULT_URL
        self._redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        self._subscriptions: dict[str, list[EventCallback]] = {}
        self._stream_subscriptions: dict[str, list[EventCallback]] = {}
        self._consumer_name: str = ""
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def connect(self, consumer_name: str = "supervisor") -> None:
        """Conecta ao Redis e inicializa streams.

        Args:
            consumer_name: Nome único deste consumidor (para consumer groups).
        """
        self._consumer_name = consumer_name
        try:
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                max_connections=20,
                socket_timeout=15.0,  # Maior que o REDIS_BLOCK_MS para evitar TimeoutError
            )
            await self._redis.ping()
            logger.info(
                "Conectado ao Redis",
                extra={"url": self._redis_url, "consumer": consumer_name},
            )

            # Inicializa streams e consumer groups
            await self._initialize_streams()

        except Exception as e:
            raise EventBusError(f"Falha ao conectar ao Redis: {e}") from e

    async def _initialize_streams(self) -> None:
        """Cria streams e consumer groups se não existirem."""
        for stream in ALL_STREAMS:
            stream_key = f"{REDIS_EVENT_PREFIX}{stream}"
            try:
                await self._redis.xgroup_create(
                    stream_key,
                    REDIS_CONSUMER_GROUP,
                    id="0",
                    mkstream=True,
                )
                logger.debug(f"Stream criado: {stream_key}")
            except aioredis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    pass  # Consumer group já existe
                else:
                    raise

    async def disconnect(self) -> None:
        """Desconecta do Redis e para todas as tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()

        if self._redis:
            await self._redis.close()

        logger.info("Event Bus desconectado")

    # ──────────────────────────────────────────────
    # Publicação
    # ──────────────────────────────────────────────

    async def publish(self, event: LoganEvent, stream: str | None = None) -> str | None:
        """Publica um evento no Event Bus.

        Se stream for especificado, usa Redis Streams (confiável).
        Caso contrário, usa Pub/Sub (fire-and-forget).

        Args:
            event: Evento a ser publicado.
            stream: Stream Redis para publicação confiável (opcional).

        Returns:
            ID da mensagem no stream, ou None para Pub/Sub.
        """
        if not self._redis:
            raise EventPublishError("Event Bus não conectado")

        try:
            event_data = event.to_json()

            if stream:
                # Redis Streams (confiável)
                stream_key = f"{REDIS_EVENT_PREFIX}{stream}"
                msg_id = await self._redis.xadd(
                    stream_key,
                    {"event": event_data},
                    maxlen=REDIS_STREAM_MAX_LEN,
                    approximate=True,
                )
                logger.debug(
                    f"Evento publicado em stream: {stream}",
                    extra={
                        "event_type": event.event_type,
                        "source": event.source,
                        "priority": event.priority,
                        "stream_id": msg_id,
                    },
                )
                return msg_id
            else:
                # Pub/Sub (fire-and-forget)
                channel = f"{REDIS_EVENT_PREFIX}{event.event_type}"
                await self._redis.publish(channel, event_data)
                logger.debug(
                    f"Evento publicado via Pub/Sub: {event.event_type}",
                    extra={
                        "source": event.source,
                        "priority": event.priority,
                    },
                )
                return None

        except Exception as e:
            raise EventPublishError(
                f"Falha ao publicar evento {event.event_type}: {e}",
                context={"event": event.to_dict()},
            ) from e

    async def publish_to_channel(
        self,
        event_type: str,
        payload: dict[str, Any],
        source: str,
        priority: int = 0,
    ) -> None:
        """Atalho para publicar evento simples via Pub/Sub.

        Args:
            event_type: Tipo do evento.
            payload: Dados do evento.
            source: Componente de origem.
            priority: Prioridade.
        """
        event = LoganEvent(
            event_type=event_type,
            source=source,
            payload=payload,
            priority=priority,
        )
        await self.publish(event)

    async def publish_to_stream(
        self,
        stream: str,
        event_type: str,
        payload: dict[str, Any],
        source: str,
        priority: int = 0,
        correlation_id: str | None = None,
    ) -> str | None:
        """Atalho para publicar evento em stream Redis.

        Args:
            stream: Nome do stream.
            event_type: Tipo do evento.
            payload: Dados do evento.
            source: Componente de origem.
            priority: Prioridade.
            correlation_id: ID de correlação para rastreamento.

        Returns:
            ID da mensagem no stream.
        """
        event = LoganEvent(
            event_type=event_type,
            source=source,
            payload=payload,
            priority=priority,
            correlation_id=correlation_id,
        )
        return await self.publish(event, stream=stream)

    # ──────────────────────────────────────────────
    # Assinatura
    # ──────────────────────────────────────────────

    def subscribe(self, event_type: str, callback: EventCallback) -> None:
        """Registra callback para um tipo de evento via Pub/Sub.

        Args:
            event_type: Tipo do evento para escutar.
            callback: Função async chamada quando evento chegar.
        """
        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []
        self._subscriptions[event_type].append(callback)
        logger.debug(f"Assinatura Pub/Sub registrada: {event_type}")

    def subscribe_stream(self, stream: str, callback: EventCallback) -> None:
        """Registra callback para um stream Redis.

        Args:
            stream: Nome do stream.
            callback: Função async chamada quando evento chegar.
        """
        if stream not in self._stream_subscriptions:
            self._stream_subscriptions[stream] = []
        self._stream_subscriptions[stream].append(callback)
        logger.debug(f"Assinatura Stream registrada: {stream}")

    # ──────────────────────────────────────────────
    # Loops de consumo
    # ──────────────────────────────────────────────

    async def start_consuming(self) -> None:
        """Inicia os loops de consumo para Pub/Sub e Streams."""
        self._running = True

        # Inicia consumer para Pub/Sub
        if self._subscriptions:
            task = asyncio.create_task(self._pubsub_consumer_loop())
            self._tasks.append(task)

        # Inicia consumers para Streams
        if self._stream_subscriptions:
            task = asyncio.create_task(self._stream_consumer_loop())
            self._tasks.append(task)

        logger.info(
            "Event Bus iniciou consumo",
            extra={
                "pubsub_channels": len(self._subscriptions),
                "streams": len(self._stream_subscriptions),
            },
        )

    async def _pubsub_consumer_loop(self) -> None:
        """Loop de consumo para canais Pub/Sub."""
        self._pubsub = self._redis.pubsub()

        # Assina todos os canais registrados
        channels = {
            f"{REDIS_EVENT_PREFIX}{et}": None
            for et in self._subscriptions
        }
        await self._pubsub.subscribe(**channels)

        try:
            while self._running:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message and message["type"] == "message":
                    await self._dispatch_pubsub_message(message)
                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            logger.debug("Pub/Sub consumer loop cancelado")
        except Exception as e:
            logger.error(f"Erro no Pub/Sub consumer: {e}", exc_info=True)

    async def _stream_consumer_loop(self) -> None:
        """Loop de consumo para Redis Streams com consumer groups."""
        streams = {
            f"{REDIS_EVENT_PREFIX}{s}": ">"
            for s in self._stream_subscriptions
        }

        try:
            while self._running:
                try:
                    results = await self._redis.xreadgroup(
                        groupname=REDIS_CONSUMER_GROUP,
                        consumername=self._consumer_name,
                        streams=streams,
                        count=10,
                        block=REDIS_BLOCK_MS,
                    )

                    if results:
                        for stream_key, messages in results:
                            for msg_id, msg_data in messages:
                                await self._dispatch_stream_message(
                                    stream_key, msg_id, msg_data
                                )

                except aioredis.ResponseError as e:
                    if "NOGROUP" in str(e):
                        await self._initialize_streams()
                    else:
                        logger.error(f"Erro de resposta Redis no Stream consumer: {e}")
                        await asyncio.sleep(1)
                except (aioredis.exceptions.TimeoutError, TimeoutError):
                    # Timeout esperado devido ao block=5000
                    pass
                except Exception as e:
                    if self._running:
                        logger.error(f"Erro no Stream consumer: {e}", exc_info=True)
                        await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.debug("Stream consumer loop cancelado")

    async def _dispatch_pubsub_message(self, message: dict) -> None:
        """Despacha mensagem Pub/Sub para callbacks registrados."""
        try:
            channel = message["channel"]
            if isinstance(channel, bytes):
                channel = channel.decode("utf-8")

            # Remove prefixo
            event_type = channel.replace(REDIS_EVENT_PREFIX, "")
            event = LoganEvent.from_json(message["data"])

            callbacks = self._subscriptions.get(event_type, [])
            for callback in callbacks:
                try:
                    await callback(event)
                except Exception as e:
                    logger.error(
                        f"Erro no callback Pub/Sub: {e}",
                        extra={"event_type": event_type},
                        exc_info=True,
                    )

        except Exception as e:
            logger.error(f"Erro ao despachar mensagem Pub/Sub: {e}", exc_info=True)

    async def _dispatch_stream_message(
        self, stream_key: str, msg_id: str, msg_data: dict
    ) -> None:
        """Despacha mensagem de Stream para callbacks registrados."""
        try:
            # Remove prefixo para encontrar o stream
            stream_name = stream_key.replace(REDIS_EVENT_PREFIX, "")
            event_data = msg_data.get("event", "{}")
            event = LoganEvent.from_json(event_data)

            callbacks = self._stream_subscriptions.get(stream_name, [])
            for callback in callbacks:
                try:
                    await callback(event)
                except Exception as e:
                    logger.error(
                        f"Erro no callback Stream: {e}",
                        extra={
                            "stream": stream_name,
                            "event_type": event.event_type,
                        },
                        exc_info=True,
                    )

            # Acknowledge a mensagem
            await self._redis.xack(
                stream_key, REDIS_CONSUMER_GROUP, msg_id
            )

        except Exception as e:
            logger.error(f"Erro ao despachar mensagem Stream: {e}", exc_info=True)

    # ──────────────────────────────────────────────
    # Utilitários
    # ──────────────────────────────────────────────

    async def get_stream_length(self, stream: str) -> int:
        """Retorna o tamanho de um stream."""
        if not self._redis:
            return 0
        stream_key = f"{REDIS_EVENT_PREFIX}{stream}"
        return await self._redis.xlen(stream_key)

    async def health_check(self) -> bool:
        """Verifica se o Event Bus está operacional."""
        try:
            if self._redis:
                await self._redis.ping()
                return True
        except Exception:
            pass
        return False

    @property
    def is_running(self) -> bool:
        """Se o Event Bus está consumindo eventos."""
        return self._running
