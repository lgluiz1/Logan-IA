# Logan AI — Phrase Selector

"""
Seleciona variações de frases aleatoriamente para evitar repetição.
Carrega frases de arquivos JSON organizados por categoria.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from core.base_service import BaseService
from core.config_manager import ConfigManager
from core.event_bus import EventBus
from core.logger import get_logger

logger = get_logger("service.phrase_selector")


class PhraseSelector(BaseService):
    """Seleciona variações de frases para o Logan AI falar.

    Nunca utiliza frases repetitivas — seleciona aleatoriamente
    de um pool de variações armazenadas em JSON.

    Cada arquivo JSON segue o formato:
    {
        "categoria": {
            "situação": [
                "Variação 1 com {driver_name}",
                "Variação 2 com {value}°C",
                ...
            ]
        }
    }
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="phrase_selector",
            event_bus=event_bus,
            config=config,
        )
        self._phrases: dict[str, dict[str, list[str]]] = {}
        self._history: dict[str, list[int]] = {}
        self._max_history = 5  # Lembra das últimas N frases usadas

    async def initialize(self) -> None:
        """Carrega todas as frases dos arquivos JSON."""
        phrases_dir = Path(self._config.phrases_dir)

        if not phrases_dir.exists():
            self._logger.warning(f"Diretório de frases não encontrado: {phrases_dir}")
            self._initialized = True
            return

        for json_file in phrases_dir.glob("*.json"):
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                category = json_file.stem  # filename sem extensão
                self._phrases[category] = data
                phrase_count = sum(
                    len(variations)
                    for variations in data.values()
                    if isinstance(variations, list)
                )
                self._logger.info(
                    f"Frases carregadas: {category} ({phrase_count} variações)"
                )
            except Exception as e:
                self._logger.error(f"Erro ao carregar {json_file}: {e}")

        self._initialized = True
        total = sum(
            sum(len(v) for v in cat.values() if isinstance(v, list))
            for cat in self._phrases.values()
        )
        self._logger.info(f"Total de variações carregadas: {total}")

    async def shutdown(self) -> None:
        """Limpa frases da memória."""
        self._phrases.clear()
        self._history.clear()

    def select(
        self,
        category: str,
        situation: str,
        **kwargs: Any,
    ) -> str:
        """Seleciona uma variação de frase aleatoriamente.

        Args:
            category: Categoria (e.g., "temperature", "connection").
            situation: Situação específica (e.g., "warning", "critical").
            **kwargs: Variáveis para interpolação (e.g., driver_name, value).

        Returns:
            Frase selecionada com variáveis substituídas.
        """
        # Busca variações
        cat_phrases = self._phrases.get(category, {})
        variations = cat_phrases.get(situation, [])

        if not variations:
            # Fallback: retorna mensagem genérica
            return kwargs.get("fallback", f"[{category}.{situation}]")

        # Evita repetição
        history_key = f"{category}.{situation}"
        used_indices = self._history.get(history_key, [])

        # Filtra índices não utilizados recentemente
        available = [
            i for i in range(len(variations)) if i not in used_indices
        ]

        # Se todos foram usados, reseta histórico
        if not available:
            available = list(range(len(variations)))
            self._history[history_key] = []

        # Seleciona aleatoriamente
        idx = random.choice(available)

        # Atualiza histórico
        if history_key not in self._history:
            self._history[history_key] = []
        self._history[history_key].append(idx)
        if len(self._history[history_key]) > self._max_history:
            self._history[history_key] = self._history[history_key][-self._max_history:]

        # Interpola variáveis
        phrase = variations[idx]
        try:
            phrase = phrase.format(**kwargs)
        except (KeyError, IndexError):
            pass  # Se faltar variável, mantém o template

        return phrase

    def get_categories(self) -> list[str]:
        """Lista categorias disponíveis."""
        return list(self._phrases.keys())
