# Logan AI — RPM Worker

"""
Monitora RPM e Velocidade para sugerir boas práticas de condução.
Alerta sobre excesso de giro em motor frio ou perigo de corte de giro.
"""

from __future__ import annotations

import time

from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.constants import EVENT_OBD_DATA, STREAM_ALERTS
from core.enums import AlertCategory, AlertLevel
from core.event_bus import EventBus
from core.models.event import LoganEvent


class RPMWorker(BaseWorker):
    """Worker de monitoramento de rotação do motor (RPM) e velocidade."""

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="rpm_worker",
            event_bus=event_bus,
            config=config,
        )
        self._last_alert_time: float = 0
        self._alert_cooldown = 120.0  # 2 min entre alertas de condução

        self._cold_limit = 3500
        self._high_warning = 5500
        self._high_critical = 6200
        self._temp_cold_threshold = 70.0  # Motor é considerado frio abaixo disso

    async def _setup_subscriptions(self) -> None:
        self._event_bus.subscribe(EVENT_OBD_DATA, self._safe_handle_event)

    async def _on_start(self) -> None:
        """Carrega thresholds."""
        self._cold_limit = self._config.get("thresholds.rpm.cold_limit", 3500)
        self._high_warning = self._config.get("thresholds.rpm.high_warning", 5500)
        self._high_critical = self._config.get("thresholds.rpm.high_critical", 6200)

    async def handle_event(self, event: LoganEvent) -> None:
        """Processa dados de RPM e temperatura do refrigerante."""
        if event.event_type != EVENT_OBD_DATA:
            return

        readings = event.payload.get("readings", {})
        rpm_reading = readings.get("RPM")
        temp_reading = readings.get("COOLANT_TEMP")

        if not rpm_reading or not rpm_reading.get("is_valid"):
            return

        rpm = float(rpm_reading["value"])
        temp = 90.0  # Assumir motor quente se não houver leitura

        if temp_reading and temp_reading.get("is_valid"):
            temp = float(temp_reading["value"])

        now = time.time()

        if now - self._last_alert_time < self._alert_cooldown:
            return

        driver_name = self._config.driver_name
        alert_msg = ""
        level = AlertLevel.INFO

        if temp < self._temp_cold_threshold and rpm > self._cold_limit:
            # Acelerando muito com motor frio
            alert_msg = (
                f"{driver_name}, eu ainda estou frio. "
                f"Tente pegar leve no acelerador até minha temperatura "
                f"chegar no ideal para não forçar o desgaste interno."
            )
            level = AlertLevel.WARNING

        elif rpm > self._high_critical:
            # Over-revving
            alert_msg = (
                f"{driver_name}, cuidado com o corte de giro! "
                f"Estou no limite absoluto de rotação. "
                f"Pode subir uma marcha, por favor."
            )
            level = AlertLevel.CRITICAL

        elif rpm > self._high_warning:
            # Quase no limite
            alert_msg = (
                f"{driver_name}, o giro do meu motor está bem alto, "
                f"passando dos {self._high_warning} RPM. "
                f"Vamos economizar combustível."
            )
            level = AlertLevel.WARNING

        if alert_msg:
            self._last_alert_time = now

            await self.publish(
                event_type="alert.rpm",
                payload={
                    "category": AlertCategory.GENERAL.value, # "RPM" if added to AlertCategory
                    "level": level.value,
                    "value": rpm,
                    "voice_message": alert_msg,
                    "cancellable": False,
                },
                stream=STREAM_ALERTS,
                priority=60 if level == AlertLevel.WARNING else 75,
            )
