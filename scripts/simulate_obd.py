# Logan AI — OBD Simulator

"""
Simulador OBD-II para desenvolvimento sem veículo real.
Gera dados realistas de telemetria e publica no Event Bus.
"""

from __future__ import annotations

import asyncio
import math
import random
import time

from core.constants import (
    EVENT_OBD_CONNECTED,
    EVENT_OBD_DATA,
    STREAM_STATE_CHANGES,
)
from core.event_bus import EventBus
from core.logger import get_logger
from core.models.event import LoganEvent

logger = get_logger("obd_simulator")


class OBDSimulator:
    """Simulador de dados OBD-II para desenvolvimento.

    Gera dados realistas que variam ao longo do tempo,
    simulando um veículo em diferentes condições:
    - Motor frio esquentando
    - Condução normal
    - Aceleração forte
    - Cenário de superaquecimento
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._running = False
        self._task: asyncio.Task | None = None

        # Estado simulado
        self._time_running = 0.0
        self._coolant_temp = 25.0
        self._intake_temp = 25.0
        self._rpm = 0.0
        self._speed = 0.0
        self._throttle = 0.0
        self._fuel_level = 75.0
        self._engine_load = 0.0
        self._battery_voltage = 12.6
        self._map_pressure = 101.0
        self._maf_rate = 0.0
        self._o2_b1s1 = 0.45

    async def start(self) -> None:
        """Inicia o simulador."""
        self._running = True
        logger.info("OBD Simulator iniciado")

        # Publica evento de conexão
        event = LoganEvent(
            event_type=EVENT_OBD_CONNECTED,
            source="obd_simulator",
            payload={
                "port": "SIMULATOR",
                "protocol": "ISO 15765-4 (CAN 11/500)",
                "supported_commands": 14,
            },
        )
        await self._event_bus.publish(event, stream=STREAM_STATE_CHANGES)

        # Inicia loop de simulação
        self._task = asyncio.create_task(self._simulation_loop())

    async def stop(self) -> None:
        """Para o simulador."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("OBD Simulator parado")

    async def _simulation_loop(self) -> None:
        """Loop principal de simulação."""
        try:
            while self._running:
                try:
                    self._time_running += 1.0
                    self._update_simulation()
                    await self._publish_readings()

                    if self._time_running == 15.0:
                        await self._inject_mock_dtc()

                    await asyncio.sleep(1.0)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Erro no simulador: {e}", exc_info=True)
                    await asyncio.sleep(5.0)

        except asyncio.CancelledError:
            pass

    async def _inject_mock_dtc(self) -> None:
        """Injeta um código DTC de teste no barramento."""
        logger.info("Injetando código de erro DTC simulado: P0300 (Falha de ignição múltipla)")
        event = LoganEvent(
            event_type="obd.dtc_detected",
            source="obd_simulator",
            payload={"codes": ["P0300"]},
        )
        await self._event_bus.publish(event)

    def _update_simulation(self) -> None:
        """Atualiza valores simulados."""
        t = self._time_running

        # Motor esquentando nos primeiros 5 minutos
        if t < 300:
            target_temp = 88.0
            self._coolant_temp += (target_temp - self._coolant_temp) * 0.01
        else:
            # Flutuação normal entre 85-93°C
            self._coolant_temp = 89.0 + 4.0 * math.sin(t / 60) + random.uniform(-1, 1)

        # Simula cenário de superaquecimento a cada 10 minutos (para teste)
        if 590 < t < 660:
            self._coolant_temp = min(self._coolant_temp + 0.3, 108.0)

        # RPM com variação
        base_rpm = 900 + 600 * math.sin(t / 30)
        self._rpm = max(700, base_rpm + random.uniform(-50, 50))

        # Velocidade proporcional ao RPM
        self._speed = max(0, (self._rpm - 800) * 0.08 + random.uniform(-2, 2))

        # Throttle
        self._throttle = max(0, min(100, 20 + 30 * math.sin(t / 20) + random.uniform(-5, 5)))

        # Combustível diminuindo lentamente
        self._fuel_level = max(0, 75.0 - (t / 600))

        # Engine load
        self._engine_load = max(0, min(100, 30 + 20 * math.sin(t / 25)))

        # Battery
        self._battery_voltage = 13.8 + random.uniform(-0.3, 0.3)

        # Intake temp
        self._intake_temp = 30 + 5 * math.sin(t / 120) + random.uniform(-1, 1)

        # MAP
        self._map_pressure = 80 + 20 * math.sin(t / 15) + random.uniform(-2, 2)

        # MAF
        self._maf_rate = max(0, 5 + 10 * math.sin(t / 20) + random.uniform(-1, 1))

        # Simula sonda travada pobre após 45 segundos (para teste do LambdaWorker)
        if t > 45:
            self._o2_b1s1 = 0.12  # Travada pobre!
        else:
            self._o2_b1s1 = 0.45 + 0.35 * math.sin(t * 1.5) + random.uniform(-0.05, 0.05)
            self._o2_b1s1 = max(0.1, min(0.9, self._o2_b1s1))

    async def _publish_readings(self) -> None:
        """Publica leituras simuladas no Event Bus."""
        readings = {
            "COOLANT_TEMP": {
                "command": "COOLANT_TEMP",
                "value": round(self._coolant_temp, 1),
                "unit": "°C",
                "is_valid": True,
                "timestamp": time.time(),
            },
            "INTAKE_TEMP": {
                "command": "INTAKE_TEMP",
                "value": round(self._intake_temp, 1),
                "unit": "°C",
                "is_valid": True,
                "timestamp": time.time(),
            },
            "RPM": {
                "command": "RPM",
                "value": round(self._rpm),
                "unit": "RPM",
                "is_valid": True,
                "timestamp": time.time(),
            },
            "SPEED": {
                "command": "SPEED",
                "value": round(self._speed, 1),
                "unit": "km/h",
                "is_valid": True,
                "timestamp": time.time(),
            },
            "THROTTLE_POS": {
                "command": "THROTTLE_POS",
                "value": round(self._throttle, 1),
                "unit": "%",
                "is_valid": True,
                "timestamp": time.time(),
            },
            "FUEL_LEVEL": {
                "command": "FUEL_LEVEL",
                "value": round(self._fuel_level, 1),
                "unit": "%",
                "is_valid": True,
                "timestamp": time.time(),
            },
            "ENGINE_LOAD": {
                "command": "ENGINE_LOAD",
                "value": round(self._engine_load, 1),
                "unit": "%",
                "is_valid": True,
                "timestamp": time.time(),
            },
            "CONTROL_MODULE_VOLTAGE": {
                "command": "CONTROL_MODULE_VOLTAGE",
                "value": round(self._battery_voltage, 2),
                "unit": "V",
                "is_valid": True,
                "timestamp": time.time(),
            },
            "INTAKE_PRESSURE": {
                "command": "INTAKE_PRESSURE",
                "value": round(self._map_pressure, 1),
                "unit": "kPa",
                "is_valid": True,
                "timestamp": time.time(),
            },
            "MAF": {
                "command": "MAF",
                "value": round(self._maf_rate, 2),
                "unit": "g/s",
                "is_valid": True,
                "timestamp": time.time(),
            },
            "O2_B1S1": {
                "command": "O2_B1S1",
                "value": round(self._o2_b1s1, 3),
                "unit": "V",
                "is_valid": True,
                "timestamp": time.time(),
            },
        }

        event = LoganEvent(
            event_type=EVENT_OBD_DATA,
            source="obd_simulator",
            payload={"readings": readings},
        )
        await self._event_bus.publish(event)


async def run_simulator() -> None:
    """Executa o simulador OBD standalone (para testes)."""
    from core.config_manager import ConfigManager
    from core.logger import setup_logger

    config = ConfigManager()
    config.load()

    setup_logger(level=config.log_level, log_dir=config.get("logan.log_dir", "logs"))

    event_bus = EventBus(redis_url=config.redis_url)
    await event_bus.connect(consumer_name="simulator")

    simulator = OBDSimulator(event_bus)
    await simulator.start()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await simulator.stop()
        await event_bus.disconnect()


if __name__ == "__main__":
    asyncio.run(run_simulator())
