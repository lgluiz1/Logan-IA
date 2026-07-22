# Logan AI — DTC Worker

"""
Monitora os códigos de erro (DTC) emitidos pelo veículo.
Consulta o banco de dados para explicar o erro de forma clara ao motorista.
"""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any

from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.constants import EVENT_OBD_DATA, STREAM_ALERTS
from core.enums import AlertCategory, AlertLevel
from core.event_bus import EventBus
from core.models.event import LoganEvent


class DTCWorker(BaseWorker):
    """Worker de diagnóstico de falhas (DTC)."""

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="dtc_worker",
            event_bus=event_bus,
            config=config,
        )
        self._db_path = config.get("system.db_path", "/app/db/logan.db")
        # Se rodando fora do docker no windows
        if "logan.db" not in self._db_path or not self._db_path.startswith("/app/"):
            self._db_path = "db/logan.db"

        self._known_active_dtcs: set[str] = set()

    async def _setup_subscriptions(self) -> None:
        """Escuta leituras de DTC via OBD_DATA ou evento específico de DTC."""
        self._event_bus.subscribe(EVENT_OBD_DATA, self._safe_handle_event)
        self._event_bus.subscribe("obd.dtc_detected", self._safe_handle_event)

    async def handle_event(self, event: LoganEvent) -> None:
        """Processa novos códigos DTC detectados."""
        if event.event_type == "obd.dtc_detected":
            codes = event.payload.get("codes", [])
            if codes:
                await self._process_dtcs(codes)

        elif event.event_type == EVENT_OBD_DATA:
            # Em alguns adapters, DTC pode vir no snapshot
            readings = event.payload.get("readings", {})
            dtc_reading = readings.get("GET_DTC")
            if dtc_reading and dtc_reading.get("is_valid"):
                codes = dtc_reading.get("value", [])
                if isinstance(codes, list):
                    # Se for lista de strings ou tuplas
                    parsed_codes = []
                    for c in codes:
                        if isinstance(c, tuple) and len(c) > 0:
                            parsed_codes.append(c[0])
                        elif isinstance(c, str):
                            parsed_codes.append(c)
                    if parsed_codes:
                        await self._process_dtcs(parsed_codes)

    async def _process_dtcs(self, codes: list[str]) -> None:
        """Avalia lista de códigos e gera alertas se houver novos erros."""
        current_dtcs = set(codes)

        # Códigos novos que não estavam ativos antes
        new_dtcs = current_dtcs - self._known_active_dtcs

        # Códigos resolvidos (apagados)
        resolved_dtcs = self._known_active_dtcs - current_dtcs

        if resolved_dtcs:
            for code in resolved_dtcs:
                self._logger.info(f"DTC resolvido: {code}")
                await asyncio.to_thread(self._write_dtc_history_sync, code, "resolved")

        if new_dtcs:
            for code in new_dtcs:
                await asyncio.to_thread(self._write_dtc_history_sync, code, "detected")
                await self._alert_new_dtc(code)

        self._known_active_dtcs = current_dtcs

    async def _alert_new_dtc(self, code: str) -> None:
        """Gera alerta de voz explicando o DTC."""
        driver_name = self._config.driver_name
        self._logger.warning(f"Novo código DTC detectado: {code}")

        # Busca no banco de dados SQLite
        description = None
        severity = "warning"

        try:
            # Faz a busca em uma thread pool para não bloquear o loop asyncio
            result = await asyncio.to_thread(self._query_dtc, code)
            if result:
                description = result.get("description_pt")
                severity = result.get("severity", severity)
        except Exception as e:
            self._logger.error(f"Erro ao buscar DTC no banco: {e}")

        level = AlertLevel.CRITICAL if severity == "critical" else AlertLevel.WARNING
        priority = 85 if severity == "critical" else 70

        if description:
            message = (
                f"{driver_name}, minha luz de injeção registrou um erro. "
                f"O código é o {code}, que indica {description.lower()}. "
            )
            if severity == "critical":
                message += "Recomendo procurarmos um mecânico urgente para evitar danos ao meu motor."
            else:
                message += "Isso pode afetar o desempenho ou o consumo, mas não é uma emergência."
        else:
            description = "erro não catalogado"
            message = (
                f"{driver_name}, detectei um código de erro novo, {code}, que eu não tenho no meu sistema. "
                "Salvei ele no meu histórico e vou pesquisar na internet sobre ele assim que tiver conexão."
            )

        # Publica o alerta
        await self.publish(
            event_type="alert.dtc",
            payload={
                "category": AlertCategory.DTC.value,
                "level": level.value,
                "code": code,
                "description": description,
                "voice_message": message,
                "cancellable": False,
            },
            stream=STREAM_ALERTS,
            priority=priority,
        )

    def _query_dtc(self, code: str) -> dict[str, Any] | None:
        """Busca síncrona no SQLite (rodada via to_thread)."""
        import os

        # Fallback de caminho caso esteja no windows testando (sem /app/)
        path = self._db_path
        if not os.path.exists(path) and os.path.exists("db/logan.db"):
            path = "db/logan.db"

        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dtc_codes WHERE code = ?", (code,))
            row = cursor.fetchone()
            conn.close()

            if row:
                return dict(row)
        except Exception as e:
            self._logger.error(f"Erro no SQLite DTC: {e}")

        return None

    def _write_dtc_history_sync(self, code: str, action: str) -> None:
        """Persiste histórico de ativação e resolução de falhas no SQLite."""
        import os
        path = self._db_path
        if not os.path.exists(path) and os.path.exists("db/logan.db"):
            path = "db/logan.db"

        try:
            conn = sqlite3.connect(path)
            cursor = conn.cursor()

            if action == "detected":
                # Verifica se já está ativo para não duplicar
                cursor.execute(
                    "SELECT id FROM dtc_history WHERE dtc_code = ? AND status = 'active'",
                    (code,)
                )
                if not cursor.fetchone():
                    # Como não temos múltiplos perfis de veículo complexos, usamos vehicle_id = 1
                    cursor.execute(
                        "INSERT INTO dtc_history (vehicle_id, dtc_code, status) VALUES (1, ?, 'active')",
                        (code,)
                    )
                    conn.commit()
                    self._logger.info(f"DTC {code} persistido no histórico como ativo.")

            elif action == "resolved":
                # Marca como resolvido
                cursor.execute(
                    "UPDATE dtc_history SET status = 'resolved', cleared_at = CURRENT_TIMESTAMP WHERE dtc_code = ? AND status = 'active'",
                    (code,)
                )
                conn.commit()
                self._logger.info(f"DTC {code} atualizado no histórico como resolvido.")

            conn.close()
        except Exception as e:
            self._logger.error(f"Erro ao salvar histórico do DTC {code}: {e}")
