# 🚗 LOGAN AI v1.0

**Assistente automotivo inteligente que transforma qualquer veículo compatível com OBD-II em um carro inteligente.**

O Logan AI age como se fosse o próprio carro conversando com o motorista — sempre em primeira pessoa, com linguagem natural e não alarmista.

> *"Luiz, identifiquei uma pequena alteração na temperatura do meu motor. Vou continuar monitorando."*

---

## Arquitetura

```
Supervisor
│
├── EventBus (Redis Streams + Pub/Sub)
├── Scheduler (Priority Queue)
├── Voice Queue
├── Health Manager
├── Logger
├── Configuration Manager
├── Drivers (OBD, ESP32, Audio, GPS, Bluetooth)
├── Workers (Temperature, Fuel, Battery, RPM, DTC, Voice, LED, ...)
└── Services (AI Gateway, Knowledge Base, Phrase Selector)
```

**Princípio central:** Nenhum Worker se comunica diretamente com outro Worker. Toda comunicação ocorre exclusivamente através do Event Bus.

## Quick Start

```bash
# 1. Clone e configure
cp .env.example .env

# 2. Inicie em modo desenvolvimento (simulador OBD)
make dev

# 3. Acesse
# Dashboard Grafana: http://localhost:3000
# API REST: http://localhost:8080
# Prometheus: http://localhost:9090
```

## Tecnologias

| Componente | Tecnologia |
|:---|:---|
| **Linguagem** | Python 3.11+ |
| **Event Bus** | Redis Streams + Pub/Sub |
| **TTS** | Kokoro |
| **STT** | faster-whisper |
| **Wake Word** | OpenWakeWord |
| **OBD-II** | python-obd |
| **API** | FastAPI |
| **Banco** | SQLite |
| **Containers** | Docker Compose |
| **Monitoramento** | Prometheus + Grafana |
| **Hardware** | Orange Pi + ESP32-S3 |

## Estrutura do Projeto

```
logan_ai/
├── core/           # Núcleo: Event Bus, Scheduler, Supervisor
├── drivers/        # Acesso a hardware: OBD, ESP32, Audio
├── workers/        # Lógica de negócio: Temperature, Fuel, Voice
├── services/       # Serviços compartilhados: AI Gateway, Knowledge Base
├── config/         # Configurações YAML
├── data/           # Frases, códigos DTC, migrações SQL
├── docker/         # Dockerfiles e configs de containers
├── api/            # API REST (FastAPI)
├── esp32/          # Firmware ESP32-S3
├── scripts/        # Scripts utilitários
├── tests/          # Testes unitários e de integração
└── docs/           # Documentação
```

## Licença

Proprietário — Logan AI Team
