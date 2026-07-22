# Logan AI — Temperature Worker

"""
Monitora a temperatura do motor e gera alertas progressivos.
Nunca acessa o OBD diretamente — recebe dados via Event Bus.
"""

from __future__ import annotations

import time
from collections import deque

from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.constants import (
    EVENT_ALERT_TEMPERATURE,
    EVENT_OBD_DATA,
    PRIORITY_CRITICAL_TEMPERATURE,
    PRIORITY_TEMPERATURE,
    STREAM_ALERTS,
    TEMP_COOLANT_CRITICAL,
    TEMP_COOLANT_NORMAL_MAX,
    TEMP_COOLANT_WARNING,
)
from core.enums import AlertCategory, AlertLevel
from core.event_bus import EventBus
from core.models.event import LoganEvent


class TemperatureWorker(BaseWorker):
    """Worker de monitoramento de temperatura.

    Analisa tendência de temperatura (subindo/estável/descendo)
    e gera alertas progressivos sem ser alarmista.
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="temperature_worker",
            event_bus=event_bus,
            config=config,
        )

        # Histórico para análise de tendência (últimos 30 valores)
        self._temp_history: deque[tuple[float, float]] = deque(maxlen=30)
        self._last_alert_level: AlertLevel | None = None
        self._last_alert_time: float = 0
        self._alert_cooldown = 30.0  # Mínimo 30s entre alertas de temp

        # Thresholds (carregados da config)
        self._threshold_normal_max = TEMP_COOLANT_NORMAL_MAX
        self._threshold_warning = TEMP_COOLANT_WARNING
        self._threshold_critical = TEMP_COOLANT_CRITICAL

    async def _setup_subscriptions(self) -> None:
        """Escuta dados OBD via Pub/Sub."""
        self._event_bus.subscribe(EVENT_OBD_DATA, self._safe_handle_event)

    async def _on_start(self) -> None:
        """Carrega thresholds da configuração."""
        self._threshold_normal_max = self._config.get(
            "thresholds.temperature.coolant.normal_max",
            TEMP_COOLANT_NORMAL_MAX,
        )
        self._threshold_warning = self._config.get(
            "thresholds.temperature.coolant.warning",
            TEMP_COOLANT_WARNING,
        )
        self._threshold_critical = self._config.get(
            "thresholds.temperature.coolant.critical",
            TEMP_COOLANT_CRITICAL,
        )

    async def handle_event(self, event: LoganEvent) -> None:
        """Processa dados OBD e analisa temperatura."""
        if event.event_type != EVENT_OBD_DATA:
            return

        readings = event.payload.get("readings", {})
        coolant_reading = readings.get("COOLANT_TEMP")

        if not coolant_reading or not coolant_reading.get("is_valid"):
            return

        temp_value = float(coolant_reading["value"])
        now = time.time()

        # Armazena no histórico
        self._temp_history.append((now, temp_value))

        # Analisa
        await self._analyze_temperature(temp_value, now)

    async def _analyze_temperature(self, temp: float, now: float) -> None:
        """Analisa temperatura e gera alertas se necessário."""
        driver_name = self._config.driver_name

        # Verifica cooldown
        if now - self._last_alert_time < self._alert_cooldown:
            return

        trend = self._detect_trend()

        if temp >= self._threshold_critical:
            # CRÍTICO
            if self._last_alert_level != AlertLevel.CRITICAL:
                await self._generate_alert(
                    level=AlertLevel.CRITICAL,
                    temp=temp,
                    message=(
                        f"{driver_name}, a temperatura do meu motor está muito alta, "
                        f"em {temp:.0f} graus. Recomendo que você pare em um lugar seguro "
                        f"assim que possível para eu poder resfriar."
                    ),
                    priority=PRIORITY_CRITICAL_TEMPERATURE,
                )

        elif temp >= self._threshold_warning:
            # WARNING
            if self._last_alert_level != AlertLevel.WARNING:
                if trend == "rising":
                    msg = (
                        f"{driver_name}, notei que minha temperatura está subindo "
                        f"e já chegou a {temp:.0f} graus. Vou ficar de olho, "
                        f"mas é bom prestar atenção."
                    )
                else:
                    msg = (
                        f"{driver_name}, identifiquei uma pequena alteração "
                        f"na temperatura do meu motor. Estou em {temp:.0f} graus. "
                        f"Vou continuar monitorando."
                    )

                await self._generate_alert(
                    level=AlertLevel.WARNING,
                    temp=temp,
                    message=msg,
                    priority=PRIORITY_TEMPERATURE,
                )

        elif temp <= self._threshold_normal_max:
            # Voltou ao normal
            if self._last_alert_level in (AlertLevel.WARNING, AlertLevel.CRITICAL):
                await self._generate_alert(
                    level=AlertLevel.INFO,
                    temp=temp,
                    message=(
                        f"{driver_name}, boa notícia. Minha temperatura voltou ao "
                        f"normal, estou em {temp:.0f} graus. Tudo certo por aqui."
                    ),
                    priority=40,  # Info priority
                    cancellable=False,
                )
                self._last_alert_level = None

    async def _generate_alert(
        self,
        level: AlertLevel,
        temp: float,
        message: str,
        priority: int,
        cancellable: bool = True,
    ) -> None:
        """Publica alerta de temperatura no Event Bus."""
        self._last_alert_level = level
        self._last_alert_time = time.time()

        await self.publish(
            event_type=EVENT_ALERT_TEMPERATURE,
            payload={
                "category": AlertCategory.TEMPERATURE.value,
                "level": level.value,
                "value": temp,
                "threshold": self._threshold_warning,
                "trend": self._detect_trend(),
                "voice_message": message,
                "cancellable": cancellable,
                "cancel_condition": "temp_normalized"
                if cancellable
                else None,
            },
            priority=priority,
            stream=STREAM_ALERTS,
        )

        self._logger.info(
            f"Alerta de temperatura: {level.value} — {temp}°C",
            extra={
                "value": temp,
                "level": level.value,
                "trend": self._detect_trend(),
            },
        )

    def _detect_trend(self) -> str:
        """Detecta tendência da temperatura (rising, stable, falling)."""
        if len(self._temp_history) < 5:
            return "unknown"

        recent = [t for _, t in list(self._temp_history)[-5:]]
        avg_change = (recent[-1] - recent[0]) / len(recent)

        if avg_change > 0.5:
            return "rising"
        elif avg_change < -0.5:
            return "falling"
        return "stable"
