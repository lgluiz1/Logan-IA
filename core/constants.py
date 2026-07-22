# Logan AI — Constantes do Sistema

"""
Constantes globais utilizadas por todos os componentes do Logan AI.
Nenhum valor mágico deve existir fora deste arquivo.
"""

# ──────────────────────────────────────────────
# Sistema
# ──────────────────────────────────────────────
SYSTEM_NAME = "Logan AI"
SYSTEM_VERSION = "1.0.0"
DEFAULT_DRIVER_NAME = "Luiz"

# ──────────────────────────────────────────────
# Redis
# ──────────────────────────────────────────────
REDIS_DEFAULT_URL = "redis://localhost:6379"
REDIS_EVENT_PREFIX = "logan:"
REDIS_STREAM_MAX_LEN = 10_000
REDIS_CONSUMER_GROUP = "logan_workers"
REDIS_BLOCK_MS = 5_000  # Timeout para leitura bloqueante de streams

# ──────────────────────────────────────────────
# Event Bus — Canais Pub/Sub (transientes)
# ──────────────────────────────────────────────
CHANNEL_OBD_TELEMETRY = "obd.telemetry"
CHANNEL_SYSTEM_HEARTBEAT = "system.heartbeat"
CHANNEL_AUDIO_STREAM = "audio.stream"

# ──────────────────────────────────────────────
# Event Bus — Streams (persistentes)
# ──────────────────────────────────────────────
STREAM_ALERTS = "events.alerts"
STREAM_COMMANDS = "events.commands"
STREAM_STATE_CHANGES = "events.state_changes"
STREAM_DTC = "events.dtc"
STREAM_VOICE = "events.voice"

ALL_STREAMS = [
    STREAM_ALERTS,
    STREAM_COMMANDS,
    STREAM_STATE_CHANGES,
    STREAM_DTC,
    STREAM_VOICE,
]

# ──────────────────────────────────────────────
# Event Types
# ──────────────────────────────────────────────
# OBD
EVENT_OBD_DATA = "obd.data"
EVENT_OBD_CONNECTED = "obd.connected"
EVENT_OBD_DISCONNECTED = "obd.disconnected"
EVENT_OBD_ERROR = "obd.error"

# Alerts
EVENT_ALERT_TEMPERATURE = "alert.temperature"
EVENT_ALERT_FUEL = "alert.fuel"
EVENT_ALERT_BATTERY = "alert.battery"
EVENT_ALERT_DTC = "alert.dtc"
EVENT_ALERT_RPM = "alert.rpm"

# Voice
EVENT_VOICE_WAKE_WORD = "voice.wake_word"
EVENT_VOICE_USER_SPEECH = "voice.user_speech"
EVENT_VOICE_RESPONSE = "voice.response"
EVENT_AUDIO_PLAY = "audio.play"
EVENT_AUDIO_STOP = "audio.stop"

# System
EVENT_SYSTEM_STARTUP = "system.startup"
EVENT_SYSTEM_SHUTDOWN = "system.shutdown"
EVENT_SYSTEM_WORKER_ERROR = "system.worker_error"
EVENT_SYSTEM_WORKER_STATE = "worker.state_change"

# LED
EVENT_LED_SET = "led.set"
EVENT_LED_PATTERN = "led.pattern"

# ──────────────────────────────────────────────
# Prioridades
# ──────────────────────────────────────────────
PRIORITY_WAKE_WORD = 100
PRIORITY_USER_SPEAKING = 95
PRIORITY_OBD_CONNECTION_LOST = 90
PRIORITY_CRITICAL_FAILURE = 85
PRIORITY_CRITICAL_TEMPERATURE = 80
PRIORITY_DTC = 70
PRIORITY_TEMPERATURE = 60
PRIORITY_FUEL = 50
PRIORITY_INFO = 40
PRIORITY_STATISTICS = 30

# Prioridade mínima para interrupção de fala
PRIORITY_INTERRUPT_THRESHOLD = 90

# ──────────────────────────────────────────────
# Scheduler
# ──────────────────────────────────────────────
SCHEDULER_DEFAULT_COOLDOWN_S = 8.0  # Segundos entre falas da mesma categoria
SCHEDULER_DEDUP_WINDOW_S = 60.0  # Janela de deduplicação
SCHEDULER_GROUP_THRESHOLD = 3  # Mínimo de alertas para agrupamento
SCHEDULER_MAX_QUEUE_SIZE = 50

# ──────────────────────────────────────────────
# OBD
# ──────────────────────────────────────────────
OBD_DEFAULT_PORT = "/dev/ttyUSB0"
OBD_DEFAULT_BAUDRATE = 38400
OBD_POLLING_INTERVAL_S = 1.0
OBD_CONNECTION_TIMEOUT_S = 10.0
OBD_HEARTBEAT_INTERVAL_S = 5.0
OBD_MAX_RETRY_ATTEMPTS = 10
OBD_RETRY_DELAY_S = 5.0

# ──────────────────────────────────────────────
# ESP32
# ──────────────────────────────────────────────
ESP32_DEFAULT_PORT = "/dev/ttyACM0"
ESP32_DEFAULT_BAUDRATE = 921600
ESP32_HEARTBEAT_INTERVAL_S = 3.0

# ──────────────────────────────────────────────
# Thresholds — Temperatura (°C)
# ──────────────────────────────────────────────
TEMP_COOLANT_NORMAL_MIN = 80
TEMP_COOLANT_NORMAL_MAX = 95
TEMP_COOLANT_WARNING = 100
TEMP_COOLANT_CRITICAL = 110
TEMP_INTAKE_WARNING = 50
TEMP_INTAKE_CRITICAL = 65

# ──────────────────────────────────────────────
# Thresholds — Combustível (%)
# ──────────────────────────────────────────────
FUEL_LOW_WARNING = 15.0
FUEL_LOW_CRITICAL = 7.0

# ──────────────────────────────────────────────
# Thresholds — Bateria (V)
# ──────────────────────────────────────────────
BATTERY_LOW_WARNING = 12.0
BATTERY_LOW_CRITICAL = 11.5
BATTERY_HIGH_WARNING = 15.0

# ──────────────────────────────────────────────
# Thresholds — RPM
# ──────────────────────────────────────────────
RPM_HIGH_WARNING = 5500
RPM_HIGH_CRITICAL = 6500

# ──────────────────────────────────────────────
# Voice / TTS
# ──────────────────────────────────────────────
TTS_DEFAULT_VOICE = "af_sarah"
TTS_SAMPLE_RATE = 24000
TTS_DEFAULT_SPEED = 1.0
WHISPER_MODEL = "small"
WHISPER_LANGUAGE = "pt"

# ──────────────────────────────────────────────
# AI Gateway
# ──────────────────────────────────────────────
AI_DAILY_LIMIT_OPENAI = 100
AI_DAILY_LIMIT_GEMINI = 200
AI_CACHE_TTL_S = 86400  # 24 horas
AI_PRIMARY_MODEL = "gemini-2.0-flash"
AI_SECONDARY_MODEL = "gpt-4o-mini"

# ──────────────────────────────────────────────
# Health Manager
# ──────────────────────────────────────────────
HEALTH_CHECK_INTERVAL_S = 15.0
HEALTH_MAX_FAILURES = 3
HEALTH_RESTART_DELAY_S = 5.0

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
DB_PATH = "/app/db/logan.db"
PHRASES_DIR = "/app/data/phrases"
CONFIG_DIR = "/app/config"
LOG_DIR = "/app/logs"
