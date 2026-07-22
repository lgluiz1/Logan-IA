# Logan AI — Entrypoint

"""
Ponto de entrada principal do Logan AI.
Instancia e conecta todos os componentes.
"""

from __future__ import annotations

import asyncio
import os
import sys

from core.supervisor import Supervisor


async def main() -> None:
    """Inicializa e executa o Logan AI."""
    config_dir = os.getenv("LOGAN_CONFIG_DIR", "/app/config")

    # Cria Supervisor
    supervisor = Supervisor(config_dir=config_dir)

    # Importa e registra componentes
    from drivers.audio_driver import AudioDriver
    from drivers.obd_driver import OBDDriver

    # Novos componentes da Fase 3
    from services.command_processor import LocalCommandProcessor
    from workers.battery_worker import BatteryWorker
    from workers.connection_worker import ConnectionWorker
    from workers.dtc_worker import DTCWorker
    from workers.fuel_worker import FuelWorker
    from workers.internet_sync_worker import InternetSyncWorker
    from workers.lambda_worker import LambdaWorker
    from workers.led_worker import LEDWorker
    from workers.recovery_worker import RecoveryWorker
    from workers.rpm_worker import RPMWorker
    from workers.temperature_worker import TemperatureWorker
    from workers.user_speech_worker import UserSpeechWorker
    from workers.voice_worker import VoiceWorker
    from workers.wake_word_worker import WakeWordWorker

    # O driver OBD só é ativado se não estivermos usando o simulador
    is_demo = supervisor.config.environment == "demo"
    if not is_demo:
        obd_driver = OBDDriver(supervisor.event_bus, supervisor.config)
        supervisor.register_driver(obd_driver)

    audio_driver = AudioDriver(supervisor.event_bus, supervisor.config)
    supervisor.register_driver(audio_driver)

    # Registra Serviços
    supervisor.register_service(LocalCommandProcessor(supervisor.event_bus, supervisor.config))

    # Registra todos os workers
    supervisor.register_worker(ConnectionWorker(supervisor.event_bus, supervisor.config))
    supervisor.register_worker(RecoveryWorker(supervisor.event_bus, supervisor.config))
    supervisor.register_worker(VoiceWorker(supervisor.event_bus, supervisor.config, supervisor.voice_queue))
    supervisor.register_worker(LEDWorker(supervisor.event_bus, supervisor.config))
    supervisor.register_worker(TemperatureWorker(supervisor.event_bus, supervisor.config))
    supervisor.register_worker(DTCWorker(supervisor.event_bus, supervisor.config))
    supervisor.register_worker(FuelWorker(supervisor.event_bus, supervisor.config))
    supervisor.register_worker(BatteryWorker(supervisor.event_bus, supervisor.config))
    supervisor.register_worker(RPMWorker(supervisor.event_bus, supervisor.config))

    # Workers da Fase 3
    supervisor.register_worker(WakeWordWorker(supervisor.event_bus, supervisor.config))
    supervisor.register_worker(UserSpeechWorker(supervisor.event_bus, supervisor.config))
    supervisor.register_worker(InternetSyncWorker(supervisor.event_bus, supervisor.config))
    supervisor.register_worker(LambdaWorker(supervisor.event_bus, supervisor.config))

    if is_demo:
        print("\n🚗 LOGAN AI — Modo Demo (Simulador OBD)\n")

    # Executa
    await supervisor.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nLogan AI encerrado.")
        sys.exit(0)
