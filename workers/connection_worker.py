# Logan AI — Connection Worker

"""
Monitora continuamente a conexão OBD-II.
Ao perder conexão, pausa todos os Workers e notifica o motorista.
"""

from __future__ import annotations

import asyncio
import time

from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.constants import (
    EVENT_OBD_CONNECTED,
    EVENT_OBD_DATA,
    EVENT_OBD_DISCONNECTED,
    OBD_HEARTBEAT_INTERVAL_S,
    PRIORITY_OBD_CONNECTION_LOST,
    STREAM_ALERTS,
    STREAM_STATE_CHANGES,
)
from core.enums import AlertCategory
from core.event_bus import EventBus
from core.models.event import LoganEvent


class ConnectionWorker(BaseWorker):
    """Worker de monitoramento de conexão OBD-II.

    Detecta perda de conexão e coordena:
    - Publicação de evento OBD_OFFLINE (todos pausam)
    - Notificação verbal ao motorista
    - Delegação para Recovery Worker
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="connection_worker",
            event_bus=event_bus,
            config=config,
        )
        self._is_connected = False
        self._last_data_time: float = 0
        self._heartbeat_interval = OBD_HEARTBEAT_INTERVAL_S
        self._monitor_task: asyncio.Task | None = None
        self._disconnect_threshold = 15.0  # Segundos sem dados = desconectado
        self._disconnect_time: float = 0.0
        self._has_warned_cable = False
        self._is_first_connection_after_boot = True

    async def _setup_subscriptions(self) -> None:
        """Escuta eventos de dados e estado do OBD."""
        self._event_bus.subscribe(EVENT_OBD_DATA, self._safe_handle_event)
        self._event_bus.subscribe_stream(
            STREAM_STATE_CHANGES, self._safe_handle_event
        )

    async def _on_start(self) -> None:
        """Inicia task de monitoramento."""
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def _on_stop(self) -> None:
        """Para task de monitoramento."""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()

    async def handle_event(self, event: LoganEvent) -> None:
        """Processa eventos de dados e estado."""
        if event.event_type == EVENT_OBD_DATA:
            # Dados recebidos = conexão ativa
            self._last_data_time = time.time()
            if not self._is_connected:
                await self._on_reconnect()

        elif event.event_type == EVENT_OBD_CONNECTED:
            await self._on_reconnect()

        elif event.event_type == EVENT_OBD_DISCONNECTED:
            await self._on_disconnect("driver_reported")

    async def _monitor_loop(self) -> None:
        """Loop de monitoramento de heartbeat."""
        try:
            while self.is_running or self.is_paused:
                current_time = time.time()

                # Caso de perda de conexão ativa (por falta de dados)
                if self._is_connected and self._last_data_time > 0:
                    elapsed = current_time - self._last_data_time
                    if elapsed > self._disconnect_threshold:
                        await self._on_disconnect("timeout")

                # Caso de conexão inativa prolongada (para checagem do cabo)
                if not self._is_connected and self._disconnect_time > 0.0:
                    elapsed_offline = current_time - self._disconnect_time
                    if elapsed_offline > 15.0 and not self._has_warned_cable:
                        self._has_warned_cable = True
                        driver_name = self._config.driver_name
                        await self.publish(
                            event_type="voice.response",
                            payload={
                                "text": (
                                    f"{driver_name}, acho que tem algo estranho. Preciso de sua ajuda. "
                                    f"Verifique por favor se o meu cabo está conectado corretamente ao conector OBD, "
                                    f"se não, eu não consigo ter certeza do meu funcionamento."
                                ),
                                "category": AlertCategory.CONNECTION.value,
                            },
                            stream=STREAM_ALERTS,
                            priority=PRIORITY_OBD_CONNECTION_LOST,
                        )

                await asyncio.sleep(self._heartbeat_interval)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._logger.error(f"Erro no monitor loop: {e}", exc_info=True)

    async def _on_disconnect(self, reason: str) -> None:
        """Ações ao detectar desconexão OBD."""
        if not self._is_connected and self._disconnect_time > 0.0:
            return  # Já estava desconectado e o timer está correndo

        self._is_connected = False
        self._disconnect_time = time.time()
        self._has_warned_cable = False
        driver_name = self._config.driver_name

        self._logger.warning(
            f"Conexão OBD perdida: {reason}",
            extra={"reason": reason},
        )

        # 1. Publica evento para todos os Workers pausarem
        await self.publish(
            event_type=EVENT_OBD_DISCONNECTED,
            payload={"reason": reason},
            stream=STREAM_STATE_CHANGES,
            priority=PRIORITY_OBD_CONNECTION_LOST,
        )

        # 2. Notifica o motorista via voz (Aviso Imediato)
        await self.publish(
            event_type="voice.response",
            payload={
                "text": f"Perdi a conexão com a minha central, {driver_name}. Estou verificando.",
                "category": AlertCategory.CONNECTION.value,
            },
            stream=STREAM_ALERTS,
            priority=PRIORITY_OBD_CONNECTION_LOST,
        )

        # 3. Solicita Recovery Worker para tentar reconectar
        await self.publish(
            event_type="recovery.request",
            payload={
                "target": "obd",
                "reason": reason,
            },
            stream=STREAM_STATE_CHANGES,
        )

    async def _on_reconnect(self) -> None:
        """Ações ao restabelecer conexão OBD."""
        if self._is_connected:
            return  # Já estava conectado

        self._is_connected = True
        self._last_data_time = time.time()
        self._disconnect_time = 0.0
        self._has_warned_cable = False
        driver_name = self._config.driver_name

        self._logger.info("Conexão OBD restabelecida")

        # 1. Publica evento para Workers retomarem
        await self.publish(
            event_type=EVENT_OBD_CONNECTED,
            payload={"status": "reconnected"},
            stream=STREAM_STATE_CHANGES,
        )

        # 2. Fala a saudação adequada
        if self._is_first_connection_after_boot:
            self._is_first_connection_after_boot = False
            await self._handle_startup_greeting()
        else:
            # Reconexão rápida (mid-run)
            await self.publish(
                event_type="voice.response",
                payload={
                    "text": f"Conectado de volta à central. Tudo normalizado, {driver_name}.",
                    "category": AlertCategory.CONNECTION.value,
                },
                stream=STREAM_ALERTS,
                priority=60,
            )

    async def _handle_startup_greeting(self) -> None:
        """Processa a saudação humanizada inicial de acordo com o horário e dia."""
        import datetime
        import json
        import os
        import sqlite3

        driver_name = self._config.driver_name
        now = datetime.datetime.now()
        current_date = now.strftime("%Y-%m-%d")

        # Mapeia saudação pelo horário
        if now.hour < 12:
            greeting = f"Bom dia, {driver_name}!"
        elif 12 <= now.hour < 18:
            greeting = f"Boa tarde, {driver_name}!"
        else:
            greeting = f"Boa noite, {driver_name}!"

        # Garante que a pasta data existe
        os.makedirs("data", exist_ok=True)
        state_file = "data/startup_state.json"

        is_first_of_day = True
        try:
            if os.path.exists(state_file):
                with open(state_file) as f:
                    state = json.load(f)
                    if state.get("last_greeting_date") == current_date:
                        is_first_of_day = False
        except Exception as e:
            self._logger.error(f"Erro ao ler data/startup_state.json: {e}")

        # Atualiza o arquivo de estado com a data de hoje
        try:
            with open(state_file, "w") as f:
                json.dump({"last_greeting_date": current_date}, f)
        except Exception as e:
            self._logger.error(f"Erro ao salvar data/startup_state.json: {e}")

        # Se for a primeira viagem do dia, faz a revisão histórica
        if is_first_of_day:
            path = self._config.get("system.db_path", "db/logan.db")
            if not os.path.exists(path) and os.path.exists("db/logan.db"):
                path = "db/logan.db"

            active_errors = []
            try:
                conn = sqlite3.connect(path)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT h.dtc_code, c.description_pt FROM dtc_history h "
                    "LEFT JOIN dtc_codes c ON h.dtc_code = c.code "
                    "WHERE h.status = 'active'"
                )
                active_errors = cursor.fetchall()
                conn.close()
            except Exception as e:
                self._logger.error(f"Erro ao buscar erros ativos para saudação: {e}")

            if active_errors:
                # Pega a descrição amigável do primeiro erro ativo
                code, desc = active_errors[0]
                desc_str = desc.lower() if desc else "uma falha de diagnóstico"
                message = (
                    f"{greeting} Vamos lá. Reparei que anteriormente viajamos com o erro {code}, "
                    f"que indica {desc_str}, e acabei de verificar que ele continua ativo no meu sistema. "
                    "Precisamos verificar isso."
                )
            else:
                message = f"{greeting} Estou analisando o sistema, tudo parece ok. Vamos nessa!"
        else:
            # Viagens subsequentes no mesmo dia (saudação amigável curta)
            if now.hour < 12:
                message = f"Bom dia, {driver_name}. Tudo pronto por aqui, vamos nessa!"
            elif 12 <= now.hour < 18:
                message = f"Boa tarde, {driver_name}. Tudo pronto por aqui, vamos nessa!"
            else:
                message = f"Boa noite, {driver_name}. Analisando sistemas, tudo ok."

        # Publica a fala
        await self.publish(
            event_type="voice.response",
            payload={
                "text": message,
                "category": AlertCategory.CONNECTION.value,
            },
            stream=STREAM_ALERTS,
            priority=60,
        )
