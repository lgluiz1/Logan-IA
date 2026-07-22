# Logan AI — Enums

"""
Enumerações tipadas para estados, prioridades e categorias do sistema.
Usar enums ao invés de strings mágicas garante type-safety e autocompletion.
"""

from enum import IntEnum, StrEnum


class WorkerState(StrEnum):
    """Estados possíveis de um Worker."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


class DriverState(StrEnum):
    """Estados possíveis de um Driver."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"


class AlertLevel(StrEnum):
    """Níveis de alerta."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertCategory(StrEnum):
    """Categorias de alerta para agrupamento e cooldown."""

    TEMPERATURE = "temperature"
    FUEL = "fuel"
    BATTERY = "battery"
    RPM = "rpm"
    DTC = "dtc"
    CONNECTION = "connection"
    SYSTEM = "system"
    VOICE = "voice"
    GENERAL = "general"
    LAMBDA = "lambda"


class Priority(IntEnum):
    """Prioridades do Scheduler (maior = mais urgente)."""

    STATISTICS = 30
    INFO = 40
    FUEL = 50
    TEMPERATURE = 60
    DTC = 70
    CRITICAL_TEMPERATURE = 80
    CRITICAL_FAILURE = 85
    OBD_CONNECTION_LOST = 90
    USER_SPEAKING = 95
    WAKE_WORD = 100


class EventChannel(StrEnum):
    """Canais Pub/Sub (eventos transientes de alta frequência)."""

    OBD_TELEMETRY = "obd.telemetry"
    SYSTEM_HEARTBEAT = "system.heartbeat"
    AUDIO_STREAM = "audio.stream"


class EventStream(StrEnum):
    """Streams Redis (eventos persistentes e confiáveis)."""

    ALERTS = "events.alerts"
    COMMANDS = "events.commands"
    STATE_CHANGES = "events.state_changes"
    DTC = "events.dtc"
    VOICE = "events.voice"


class LEDPattern(StrEnum):
    """Padrões de LED do ESP32."""

    OFF = "off"
    SOLID_BLUE = "solid_blue"          # Escutando wake word
    PULSE_BLUE = "pulse_blue"          # Processando comando
    SOLID_GREEN = "solid_green"        # Sistema OK
    PULSE_GREEN = "pulse_green"        # Falando
    SOLID_RED = "solid_red"            # Erro crítico
    PULSE_RED = "pulse_red"            # Alerta
    SOLID_YELLOW = "solid_yellow"      # Atenção
    RAINBOW = "rainbow"               # Inicialização
    BREATHING_WHITE = "breathing_white" # Standby


class OBDProtocol(StrEnum):
    """Protocolos OBD-II suportados."""

    AUTO = "auto"
    SAE_J1850_PWM = "1"
    SAE_J1850_VPW = "2"
    ISO_9141_2 = "3"
    ISO_14230_4_KWP_5BAUD = "4"
    ISO_14230_4_KWP_FAST = "5"
    ISO_15765_4_CAN_11BIT_500K = "6"
    ISO_15765_4_CAN_29BIT_500K = "7"
    ISO_15765_4_CAN_11BIT_250K = "8"
    ISO_15765_4_CAN_29BIT_250K = "9"


class VoiceState(StrEnum):
    """Estados do pipeline de voz."""

    IDLE = "idle"
    LISTENING_WAKE_WORD = "listening_wake_word"
    LISTENING_COMMAND = "listening_command"
    PROCESSING = "processing"
    SPEAKING = "speaking"


class SystemMode(StrEnum):
    """Modos de operação do sistema."""

    NORMAL = "normal"
    DEGRADED = "degraded"      # Sem internet
    MINIMAL = "minimal"        # Sem OBD
    MAINTENANCE = "maintenance" # Manutenção
    DEMO = "demo"              # Demonstração (simulado)
