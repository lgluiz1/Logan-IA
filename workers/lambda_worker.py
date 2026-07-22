# Logan AI — Lambda Sensor Diagnostics Worker

"""
Worker de diagnóstico da sonda lambda.
Monitora a oscilação da voltagem do sensor de oxigênio (O2_B1S1)
para detectar se a sonda está travada (mistura rica/pobre) ou com defeito de aquecimento.
"""

from __future__ import annotations

import time
from collections import deque

from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.constants import EVENT_OBD_DATA, STREAM_ALERTS
from core.enums import AlertCategory, AlertLevel
from core.event_bus import EventBus
from core.models.event import LoganEvent


class LambdaWorker(BaseWorker):
    """Worker para monitorar a oscilação da sonda lambda pré-catalisador."""

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="lambda_worker",
            event_bus=event_bus,
            config=config,
        )
        self._history: deque[tuple[float, float]] = deque()
        self._history_window_s = 15.0  # Janela de análise de 15 segundos
        self._min_readings = 8  # Mínimo de amostras para diagnóstico
        self._alert_cooldown = 180.0  # 3 minutos de cooldown entre alertas
        self._last_alert_time = 0.0

    async def _setup_subscriptions(self) -> None:
        """Assina o canal de dados do OBD."""
        self._event_bus.subscribe(EVENT_OBD_DATA, self._safe_handle_event)

    async def handle_event(self, event: LoganEvent) -> None:
        """Processa novas leituras OBD e analisa voltagem da sonda lambda."""
        if event.event_type != EVENT_OBD_DATA:
            return

        readings = event.payload.get("readings", {})

        # 1. Verifica se o motor está funcionando (RPM > 500)
        rpm_reading = readings.get("RPM")
        if rpm_reading and rpm_reading.get("is_valid"):
            try:
                rpm = float(rpm_reading["value"])
                if rpm <= 500:
                    self._history.clear()  # Motor parado, descarta histórico
                    return
            except ValueError:
                pass

        # 2. Obtém leitura da sonda lambda (O2_B1S1)
        o2_reading = readings.get("O2_B1S1")
        if not o2_reading or not o2_reading.get("is_valid"):
            return

        try:
            voltage = float(o2_reading["value"])
        except ValueError:
            return

        now = time.time()
        self._history.append((now, voltage))

        # Limpa leituras expiradas fora da janela
        while self._history and now - self._history[0][0] > self._history_window_s:
            self._history.popleft()

        # 3. Realiza o diagnóstico se houver amostras suficientes
        if len(self._history) >= self._min_readings:
            await self._run_diagnostics()

    async def _run_diagnostics(self) -> None:
        """Analisa a amplitude e comportamento da sonda lambda."""
        now = time.time()

        # Ignora se estiver no cooldown de alertas
        if now - self._last_alert_time < self._alert_cooldown:
            return

        voltages = [v for _, v in self._history]
        max_v = max(voltages)
        min_v = min(voltages)
        amplitude = max_v - min_v
        avg_v = sum(voltages) / len(voltages)

        driver_name = self._config.driver_name
        alert_msg = ""
        category = AlertCategory.LAMBDA.value

        # Sonda saudável oscila bastante (amplitude esperada > 0.4V)
        # Se oscilar menos de 0.08V na janela de 15s com motor ligado, está travada/morta
        if amplitude < 0.08:
            if avg_v < 0.20:
                # Travada em mistura pobre
                alert_msg = (
                    f"{driver_name}, notei um comportamento anormal na minha sonda lambda. "
                    "A voltagem está travada em mistura pobre. Isso pode ser causado por uma entrada falsa de ar "
                    "no coletor do motor ou bicos injetores entupidos."
                )
            elif avg_v > 0.65:
                # Travada em mistura rica
                alert_msg = (
                    f"{driver_name}, notei que a minha sonda lambda está travada em mistura rica. "
                    "O motor pode estar injetando combustível em excesso, o que aumenta muito o consumo do carro."
                )
            else:
                # Travada no meio ou inativa (aquecedor queimado)
                alert_msg = (
                    f"{driver_name}, a sonda lambda está inativa ou apresentando leituras travadas. "
                    "O sensor pode estar com mau contato nos fios ou a resistência de aquecimento interna queimada."
                )

        if alert_msg:
            self._last_alert_time = now
            self._logger.warning(f"Anomalia na Sonda Lambda detectada (amplitude: {amplitude:.3f}V, média: {avg_v:.3f}V)")

            # Dispara alerta de voz de nível aviso
            await self.publish(
                event_type="alert.lambda",
                payload={
                    "category": category,
                    "level": AlertLevel.WARNING.value,
                    "description": "Anomalia na Sonda Lambda",
                    "voice_message": alert_msg,
                    "cancellable": True,
                },
                stream=STREAM_ALERTS,
                priority=70,
            )
