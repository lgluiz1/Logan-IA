# Logan AI — Integration Test Pipeline

"""
Teste de integração de ponta a ponta do pipeline:
OBD -> Event Bus -> Worker (Temperature) -> Event Bus -> Scheduler -> Voice Queue -> Voice Worker
"""

import asyncio
import os
import pytest
from unittest.mock import patch, MagicMock

from core.config_manager import ConfigManager
from core.constants import EVENT_OBD_DATA
from core.event_bus import EventBus
from core.scheduler import Scheduler
from core.voice_queue import VoiceQueue
from tests.mocks.mock_obd import MockOBDDriver
from workers.temperature_worker import TemperatureWorker


@pytest.mark.asyncio
async def test_temperature_alert_pipeline():
    """Testa o fluxo completo de um alerta de temperatura crítica."""

    # 1. Setup básico
    config = ConfigManager()
    config.load()
    
    # Usa um EventBus local em memória se não houver Redis
    # Como não temos um mock do Redis pronto para esse teste, vamos 
    # usar patch para evitar a conexão real se não estiver disponível.
    event_bus = EventBus("redis://localhost:6379")
    
    # Mock das funções do event bus que usam redis
    event_bus.connect = MagicMock(return_value=asyncio.sleep(0))
    event_bus.disconnect = MagicMock(return_value=asyncio.sleep(0))
    event_bus.start_consuming = MagicMock(return_value=asyncio.sleep(0))
    
    # Em vez de testar com Redis real, vamos mockar a publicação 
    # para invocar diretamente os handlers inscritos
    handlers = {}
    
    def subscribe_mock(event_type, handler, group=None):
        if event_type not in handlers:
            handlers[event_type] = []
        handlers[event_type].append(handler)
        
    async def publish_mock(event, stream=None):
        # Dispara callbacks locais
        if event.event_type in handlers:
            for handler in handlers[event.event_type]:
                await handler(event)
        # Dispara callbacks de streams genéricos
        if stream in handlers:
            for handler in handlers[stream]:
                await handler(event)
                
    event_bus.subscribe = subscribe_mock
    event_bus.subscribe_stream = subscribe_mock
    event_bus.publish = publish_mock

    # 2. Setup dos componentes
    scheduler = Scheduler(event_bus, config)
    await scheduler.start()

    voice_queue = VoiceQueue(scheduler)
    await voice_queue.start()

    temp_worker = TemperatureWorker(event_bus, config)
    await temp_worker.start()

    mock_obd = MockOBDDriver(event_bus, config)
    await mock_obd.start()

    # 3. Injeção de dados (Simulando temperatura subindo)
    # Primeiro, envia temperatura normal (85)
    await mock_obd.inject_reading("COOLANT_TEMP", 85.0)
    await asyncio.sleep(0.1)

    # Verifica que não há mensagens na fila
    assert voice_queue.pending_count == 0

    # Injeta temperatura de Warning (102)
    # Isso deve disparar o TemperatureWorker -> Scheduler -> VoiceQueue
    await mock_obd.inject_reading("COOLANT_TEMP", 102.0)
    
    # Aguarda processamento do Event Bus -> Scheduler -> Queue
    await asyncio.sleep(0.5)

    # Verifica se a mensagem chegou na Voice Queue
    assert voice_queue.pending_count > 0
    
    message = await voice_queue.get_next_message()
    assert message is not None
    assert message.category.value == "temperature"
    assert "graus" in message.text or "temperatura" in message.text

    # 4. Limpeza
    await temp_worker.stop()
    await mock_obd.stop()
    await voice_queue.stop()
    await scheduler.stop()
