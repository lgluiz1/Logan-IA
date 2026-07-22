# Logan AI — Battery Worker

"""
Monitora a voltagem do sistema elétrico.
Identifica falhas de alternador (baixa tensão com motor ligado)
ou bateria fraca (baixa tensão com motor desligado).
"""

from __future__ import annotations

import time

from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.constants import EVENT_OBD_DATA, STREAM_ALERTS
from core.enums import AlertCategory, AlertLevel
from core.event_bus import EventBus
from core.models.event import LoganEvent


class BatteryWorker(BaseWorker):
    """Worker de monitoramento da bateria e alternador."""

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="battery_worker",
            event_bus=event_bus,
            config=config,
        )
        self._last_alert_time: float = 0
        self._alert_cooldown = 900.0  # 15 min de cooldown pra bateria
        self._alerted = False

        self._engine_off_low = 11.5
        self._engine_on_low = 13.0
        self._high_warning = 15.0

    async def _setup_subscriptions(self) -> None:
        self._event_bus.subscribe(EVENT_OBD_DATA, self._safe_handle_event)

    async def _on_start(self) -> None:
        """Carrega thresholds da configuração."""
        self._engine_off_low = self._config.get("thresholds.battery.engine_off_low", 11.5)
        self._engine_on_low = self._config.get("thresholds.battery.engine_on_low", 13.0)
        self._high_warning = self._config.get("thresholds.battery.high_warning", 15.0)

    async def handle_event(self, event: LoganEvent) -> None:
        """Processa dados OBD para voltagem e RPM (pra saber se motor está ligado)."""
        if event.event_type != EVENT_OBD_DATA:
            return

        readings = event.payload.get("readings", {})
        voltage_reading = readings.get("CONTROL_MODULE_VOLTAGE")
        rpm_reading = readings.get("RPM")

        if not voltage_reading or not voltage_reading.get("is_valid"):
            return

        voltage = float(voltage_reading["value"])

        # Precisamos do RPM para saber se o motor (e logo o alternador) está girando
        rpm = 0.0
        if rpm_reading and rpm_reading.get("is_valid"):
            rpm = float(rpm_reading["value"])

        now = time.time()
        engine_running = rpm > 400  # Acima de 400 rpm motor está ligado

        if now - self._last_alert_time < self._alert_cooldown:
            return

        driver_name = self._config.driver_name
        alert_msg = ""
        level = AlertLevel.WARNING
        priority = 50

        if engine_running:
            # Motor ligado, voltagem normal de um alternador é ~13.5V a 14.5V
            if voltage < self._engine_on_low:
                alert_msg = (
                    f"{driver_name}, detectei uma queda na energia do sistema, "
                    f"estamos com apenas {voltage:.1f} volts. Parece que o meu "
                    f"alternador parou de carregar a bateria. Evite desligar o carro."
                )
                level = AlertLevel.CRITICAL
                priority = 85
            elif voltage > self._high_warning:
                alert_msg = (
                    f"{driver_name}, o sistema elétrico está com uma voltagem muito "
                    f"alta, {voltage:.1f} volts. Pode ser um defeito no regulador de tensão."
                )
                level = AlertLevel.CRITICAL
                priority = 85
        else:
            # Motor desligado
            if voltage < self._engine_off_low:
                alert_msg = (
                    f"{driver_name}, a carga da minha bateria está muito baixa, "
                    f"apenas {voltage:.1f} volts. Talvez eu tenha dificuldade na próxima partida."
                )
                level = AlertLevel.WARNING
                priority = 60

        if alert_msg:
            self._last_alert_time = now
            self._alerted = True

            await self.publish(
                event_type="alert.battery",
                payload={
                    "category": AlertCategory.BATTERY.value,
                    "level": level.value,
                    "value": voltage,
                    "voice_message": alert_msg,
                    "cancellable": False,
                },
                stream=STREAM_ALERTS,
                priority=priority,
            )
        elif self._alerted and (
            (engine_running and self._engine_on_low <= voltage <= self._high_warning) or
            (not engine_running and voltage >= self._engine_off_low)
        ):
            # Normalizou
            self._alerted = False
            self._logger.info(f"Voltagem do sistema normalizada: {voltage:.1f}V")
