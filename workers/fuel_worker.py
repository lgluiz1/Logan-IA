# Logan AI — Fuel Worker

"""
Monitora o nível de combustível e avisa quando entra na reserva.
"""

from __future__ import annotations

import time

from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.constants import EVENT_OBD_DATA, STREAM_ALERTS
from core.enums import AlertCategory, AlertLevel
from core.event_bus import EventBus
from core.models.event import LoganEvent


class FuelWorker(BaseWorker):
    """Worker de monitoramento de nível de combustível."""

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="fuel_worker",
            event_bus=event_bus,
            config=config,
        )
        self._last_alert_level: AlertLevel | None = None
        self._last_alert_time: float = 0
        self._alert_cooldown = 1800.0  # 30 minutos entre alertas de combustível

        self._low_warning = 15.0
        self._low_critical = 8.0

    async def _setup_subscriptions(self) -> None:
        """Escuta dados OBD."""
        self._event_bus.subscribe(EVENT_OBD_DATA, self._safe_handle_event)

    async def _on_start(self) -> None:
        """Carrega thresholds da configuração."""
        self._low_warning = self._config.get("thresholds.fuel.low_warning", 15.0)
        self._low_critical = self._config.get("thresholds.fuel.low_critical", 8.0)

    async def handle_event(self, event: LoganEvent) -> None:
        """Processa dados OBD para combustível."""
        if event.event_type != EVENT_OBD_DATA:
            return

        readings = event.payload.get("readings", {})
        fuel_reading = readings.get("FUEL_LEVEL")

        if not fuel_reading or not fuel_reading.get("is_valid"):
            return

        fuel_pct = float(fuel_reading["value"])
        now = time.time()

        # Ignora flutuações rápidas se avisamos há pouco tempo
        if now - self._last_alert_time < self._alert_cooldown:
            return

        driver_name = self._config.driver_name

        if fuel_pct <= self._low_critical:
            # Pane Seca iminente
            if self._last_alert_level != AlertLevel.CRITICAL:
                await self._alert(
                    level=AlertLevel.CRITICAL,
                    fuel_pct=fuel_pct,
                    message=(
                        f"{driver_name}, meu combustível está bem baixo, "
                        f"apenas {fuel_pct:.0f} por cento. Precisamos parar "
                        f"no primeiro posto que encontrarmos para não dar pane seca."
                    ),
                    priority=75,
                )

        elif fuel_pct <= self._low_warning:
            # Reserva normal
            if self._last_alert_level != AlertLevel.WARNING:
                await self._alert(
                    level=AlertLevel.WARNING,
                    fuel_pct=fuel_pct,
                    message=(
                        f"{driver_name}, entrei na reserva de combustível. "
                        f"Estou com {fuel_pct:.0f} por cento. Recomendo planejarmos "
                        f"um abastecimento em breve."
                    ),
                    priority=50,
                )

        elif fuel_pct > self._low_warning + 5.0:
            # Abasteceu (Reset de estado se subiu acima do warning + margem)
            if self._last_alert_level is not None:
                self._last_alert_level = None
                self._logger.info(f"Combustível reabastecido. Nível: {fuel_pct:.0f}%")

    async def _alert(self, level: AlertLevel, fuel_pct: float, message: str, priority: int) -> None:
        """Envia o alerta de voz."""
        self._last_alert_level = level
        self._last_alert_time = time.time()

        self._logger.warning(f"Alerta de combustível: {fuel_pct:.1f}% ({level.value})")

        await self.publish(
            event_type="alert.fuel",
            payload={
                "category": AlertCategory.FUEL.value,
                "level": level.value,
                "value": fuel_pct,
                "voice_message": message,
                "cancellable": True,
            },
            stream=STREAM_ALERTS,
            priority=priority,
        )
