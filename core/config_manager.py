# Logan AI — Gerenciador de Configuração

"""
Gerenciador de configuração centralizado.
Carrega configurações de arquivos YAML, variáveis de ambiente e CLI args.
Prioridade: ENV > YAML > Defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from core.constants import CONFIG_DIR, DB_PATH, PHRASES_DIR
from core.exceptions import ConfigNotFoundError, ConfigValidationError
from core.logger import get_logger

logger = get_logger("config_manager")


class ConfigManager:
    """Gerenciador centralizado de configuração.

    Carrega configs de YAML e sobrescreve com variáveis de ambiente.
    Thread-safe para leitura (imutável após carregamento).
    """

    def __init__(self, config_dir: str | None = None) -> None:
        default_dir = os.getenv("LOGAN_CONFIG_DIR", CONFIG_DIR)
        self._config_dir = Path(default_dir)
        # Fallback para ambiente local Windows/Mac fora do Docker
        if not self._config_dir.exists() and Path("config").exists():
            self._config_dir = Path("config")
            
        self._config: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        """Carrega todas as configurações."""
        self._config = {}

        # Carrega cada arquivo YAML do diretório
        for yaml_file in ["logan.yml", "priorities.yml", "thresholds.yml", "voices.yml"]:
            file_path = self._config_dir / yaml_file
            if file_path.exists():
                key = yaml_file.replace(".yml", "").replace(".yaml", "")
                with open(file_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data:
                        self._config[key] = data
                logger.info(f"Configuração carregada: {yaml_file}")
            else:
                logger.warning(f"Configuração não encontrada: {yaml_file}")

        # Sobrescreve com variáveis de ambiente
        self._apply_env_overrides()

        self._loaded = True
        logger.info(
            "Configuração completa carregada",
            extra={"sections": list(self._config.keys())},
        )

    def _apply_env_overrides(self) -> None:
        """Aplica variáveis de ambiente como override.

        Convenção: LOGAN_<SECTION>__<KEY> (duplo underscore separa seção de chave)
        Exemplo: LOGAN_LOGAN__DRIVER_NAME=Luiz
        """
        prefix = "LOGAN_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                parts = key[len(prefix) :].lower().split("__", 1)
                if len(parts) == 2:
                    section, config_key = parts
                    if section not in self._config:
                        self._config[section] = {}
                    # Tenta converter para tipo apropriado
                    self._config[section][config_key] = self._parse_value(value)

    @staticmethod
    def _parse_value(value: str) -> Any:
        """Tenta converter string para tipo Python apropriado."""
        # Booleanos
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        # Números
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    def get(self, path: str, default: Any = None) -> Any:
        """Obtém valor de configuração por caminho pontilhado.

        Args:
            path: Caminho da config (e.g., "logan.driver_name").
            default: Valor padrão se não encontrado.

        Returns:
            Valor da configuração.

        Example:
            >>> config.get("logan.driver_name", "Motorista")
            "Luiz"
        """
        keys = path.split(".")
        value: Any = self._config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            if value is None:
                return default
        return value

    def get_section(self, section: str) -> dict[str, Any]:
        """Obtém uma seção inteira da configuração."""
        return dict(self._config.get(section, {}))

    @property
    def driver_name(self) -> str:
        """Nome do motorista."""
        return os.getenv(
            "DRIVER_NAME",
            self.get("logan.driver_name", "Luiz"),
        )

    @property
    def redis_url(self) -> str:
        """URL do Redis."""
        return os.getenv(
            "REDIS_URL",
            self.get("logan.redis_url", "redis://localhost:6379"),
        )

    @property
    def db_path(self) -> str:
        """Caminho do banco SQLite."""
        return os.getenv("LOGAN_DB_PATH", self.get("logan.db_path", DB_PATH))

    @property
    def phrases_dir(self) -> str:
        """Diretório de frases."""
        return os.getenv(
            "LOGAN_PHRASES_DIR",
            self.get("logan.phrases_dir", PHRASES_DIR),
        )

    @property
    def log_level(self) -> str:
        """Nível de log."""
        return os.getenv(
            "LOGAN_LOG_LEVEL",
            self.get("logan.log_level", "INFO"),
        )

    @property
    def environment(self) -> str:
        """Ambiente (development, production, demo)."""
        return os.getenv("LOGAN_ENV", self.get("logan.system.environment", "development"))

    @property
    def obd_port(self) -> str:
        """Porta do OBD-II."""
        return os.getenv(
            "OBD_PORT",
            self.get("logan.obd_port", "/dev/ttyUSB0"),
        )

    @property
    def esp32_port(self) -> str:
        """Porta do ESP32."""
        return os.getenv(
            "ESP32_PORT",
            self.get("logan.esp32_port", "/dev/ttyACM0"),
        )

    @property
    def whisper_url(self) -> str:
        """URL do serviço Whisper."""
        return os.getenv(
            "WHISPER_URL",
            self.get("logan.whisper_url", "http://whisper:9000"),
        )

    @property
    def kokoro_url(self) -> str:
        """URL do serviço Kokoro TTS."""
        return os.getenv(
            "KOKORO_URL",
            self.get("logan.kokoro_url", "http://kokoro:8880"),
        )
