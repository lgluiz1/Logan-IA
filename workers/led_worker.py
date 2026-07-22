# Logan AI — LED Worker

"""
Controla LEDs RGB endereçáveis (WS2812) via ESP32.
Escuta comandos do Event Bus e traduz em padrões visuais.
"""

from __future__ import annotations

from core.base_worker import BaseWorker
from core.config_manager import ConfigManager
from core.enums import LEDPattern
from core.event_bus import EventBus
from core.models.event import LoganEvent


class LEDWorker(BaseWorker):
    """Worker de controle de LEDs.

    Traduz eventos do sistema em padrões visuais:
    - Verde sólido: sistema OK
    - Azul sólido: escutando wake word
    - Azul pulsante: processando comando
    - Verde pulsante: falando
    - Vermelho: erro/alerta
    - Rainbow: inicialização
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="led_worker",
            event_bus=event_bus,
            config=config,
        )
        self._current_pattern = LEDPattern.OFF

    async def _setup_subscriptions(self) -> None:
        """Escuta comandos de LED."""
        self._event_bus.subscribe("led.set", self._safe_handle_event)
        self._event_bus.subscribe("led.pattern", self._safe_handle_event)

    async def handle_event(self, event: LoganEvent) -> None:
        """Processa comandos de LED."""
        if event.event_type == "led.pattern":
            pattern_name = event.payload.get("pattern", "off")
            try:
                pattern = LEDPattern(pattern_name)
                await self._set_pattern(pattern)
            except ValueError:
                self._logger.warning(f"Padrão de LED desconhecido: {pattern_name}")

    async def _set_pattern(self, pattern: LEDPattern) -> None:
        """Define o padrão de LED no ESP32."""
        if pattern == self._current_pattern:
            return

        self._current_pattern = pattern

        # Publica para o ESP32 Driver
        await self.publish(
            event_type="esp32.led_command",
            payload={"pattern": pattern.value},
        )

        self._logger.debug(f"LED padrão definido: {pattern.value}")
