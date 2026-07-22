# Logan AI — Exceções Customizadas

"""
Hierarquia de exceções do Logan AI.
Todas as exceções herdam de LoganError para fácil captura genérica.
"""


class LoganError(Exception):
    """Exceção base para todo o sistema Logan AI."""

    def __init__(self, message: str, context: dict | None = None) -> None:
        super().__init__(message)
        self.context = context or {}


# ──────────────────────────────────────────────
# Erros Recuperáveis
# ──────────────────────────────────────────────
class RecoverableError(LoganError):
    """Erro que pode ser resolvido com retry automático."""

    pass


class ConnectionLostError(RecoverableError):
    """Conexão com dispositivo perdida."""

    pass


class TimeoutError(RecoverableError):
    """Operação excedeu o tempo limite."""

    pass


class DeviceBusyError(RecoverableError):
    """Dispositivo ocupado, tentar novamente."""

    pass


# ──────────────────────────────────────────────
# Erros Críticos
# ──────────────────────────────────────────────
class CriticalError(LoganError):
    """Erro grave que pode exigir intervenção manual."""

    pass


class HardwareError(CriticalError):
    """Falha de hardware detectada."""

    pass


class DriverInitError(CriticalError):
    """Falha ao inicializar um Driver."""

    pass


class WorkerCrashError(CriticalError):
    """Worker sofreu crash irrecuperável."""

    pass


# ──────────────────────────────────────────────
# Erros de Configuração
# ──────────────────────────────────────────────
class ConfigError(LoganError):
    """Erro de configuração do sistema."""

    pass


class ConfigNotFoundError(ConfigError):
    """Arquivo de configuração não encontrado."""

    pass


class ConfigValidationError(ConfigError):
    """Configuração inválida."""

    pass


# ──────────────────────────────────────────────
# Erros de Event Bus
# ──────────────────────────────────────────────
class EventBusError(LoganError):
    """Erro no Event Bus."""

    pass


class EventPublishError(EventBusError):
    """Falha ao publicar evento."""

    pass


class EventSubscribeError(EventBusError):
    """Falha ao subscrever em canal/stream."""

    pass


# ──────────────────────────────────────────────
# Erros de IA
# ──────────────────────────────────────────────
class AIGatewayError(LoganError):
    """Erro no AI Gateway."""

    pass


class AIRateLimitError(AIGatewayError):
    """Limite diário de chamadas atingido."""

    pass


class AIOfflineError(AIGatewayError):
    """Sem acesso à internet para consulta de IA."""

    pass


# ──────────────────────────────────────────────
# Erros de Voz
# ──────────────────────────────────────────────
class VoiceError(LoganError):
    """Erro no pipeline de voz."""

    pass


class TTSError(VoiceError):
    """Erro na síntese de voz (Kokoro)."""

    pass


class STTError(VoiceError):
    """Erro no reconhecimento de fala (Whisper)."""

    pass


class WakeWordError(VoiceError):
    """Erro na detecção de wake word."""

    pass


# ──────────────────────────────────────────────
# Erros OBD
# ──────────────────────────────────────────────
class OBDError(LoganError):
    """Erro relacionado ao OBD-II."""

    pass


class OBDConnectionError(OBDError, RecoverableError):
    """Falha na conexão OBD-II."""

    pass


class OBDCommandError(OBDError):
    """Comando OBD retornou erro."""

    pass


class OBDProtocolError(OBDError):
    """Protocolo OBD não suportado."""

    pass
