# Logan AI — Local Command Processor

"""
Processador local de comandos de voz offline (sem LLM de nuvem).
Analisa palavras-chave no texto transcrito e monta respostas baseadas no estado atual do veículo.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sqlite3
import unicodedata
from typing import Any

from core.base_service import BaseService
from core.config_manager import ConfigManager
from core.constants import EVENT_OBD_DATA, STREAM_COMMANDS
from core.event_bus import EventBus
from core.models.event import LoganEvent


class LocalCommandProcessor(BaseService):
    """Serviço para processamento local de intenções do usuário."""

    def __init__(
        self,
        event_bus: EventBus,
        config: ConfigManager,
    ) -> None:
        super().__init__(
            name="local_command_processor",
            event_bus=event_bus,
            config=config,
        )
        self._db_path = config.get("system.db_path", "db/logan.db")
        # Ajuste de caminho fora do Docker no Windows
        if "logan.db" not in self._db_path or not self._db_path.startswith("/app/"):
            self._db_path = "db/logan.db"

        # Estado da telemetria do veículo mantido localmente
        self._latest_telemetry: dict[str, Any] = {}
        self._active_dtcs: list[str] = []

    async def initialize(self) -> None:
        """Assina canais do Event Bus."""
        # Escuta os comandos transcritos
        self._event_bus.subscribe_stream(STREAM_COMMANDS, self._on_command_event)

        # Escuta a telemetria do veículo (Pub/Sub)
        self._event_bus.subscribe(EVENT_OBD_DATA, self._on_obd_data)
        self._event_bus.subscribe("obd.dtc_detected", self._on_dtcs_detected)

        self._initialized = True
        self._logger.info("Local Command Processor inicializado")

    async def shutdown(self) -> None:
        """Limpa estado."""
        self._latest_telemetry.clear()
        self._active_dtcs.clear()

    async def _on_obd_data(self, event: LoganEvent) -> None:
        """Atualiza a leitura mais recente de sensores a partir de obd.data."""
        readings = event.payload.get("readings", {})
        for key, r in readings.items():
            if r.get("is_valid"):
                self._latest_telemetry[key] = r.get("value")

    async def _on_dtcs_detected(self, event: LoganEvent) -> None:
        """Atualiza códigos DTC ativos."""
        codes = event.payload.get("codes", [])
        self._active_dtcs = codes

    async def _on_command_event(self, event: LoganEvent) -> None:
        """Escuta eventos de voz do usuário no STREAM_COMMANDS."""
        if event.event_type == "voice.user_input":
            user_text = event.payload.get("text", "")
            if user_text:
                await self._process_command(user_text)

    async def _process_command(self, user_text: str) -> None:
        """Interpreta o comando de voz por palavras-chave e gera resposta de voz."""
        self._logger.info(f"Processando comando de voz: '{user_text}'")
        normalized = self._normalize_text(user_text)

        # Nome do motorista configurado
        driver_name = self._config.driver_name
        response_text = ""

        # 1. Intenção: Códigos de Erros (DTC)
        if any(w in normalized for w in ["erro", "falha", "problema", "diagnostico", "check engine"]):
            if self._active_dtcs:
                latest_code = self._active_dtcs[-1]
                details = await asyncio.to_thread(self._query_dtc_details, latest_code)
                desc = details["description"].lower()
                response_text = (
                    f"{driver_name}, sobre sua pergunta, o último erro que achei no meu sistema foi o {latest_code}, "
                    f"que indica {desc}. Esse erro deve ser o culpado por alguns problemas no meu sistema, "
                    f"precisamos marcar uma vistoria em um mecânico."
                )
            else:
                response_text = "Luiz, no momento não encontrei nenhum código de erro ativo no meu sistema. Tudo parece ok."

        # 1b. Intenção: Por que a luz de injeção acendeu?
        elif any(w in normalized for w in ["luz de injecao", "luz da injecao", "injecao acesa", "luz acesa", "por que acendeu"]):
            if self._active_dtcs:
                latest_code = self._active_dtcs[-1]
                details = await asyncio.to_thread(self._query_dtc_details, latest_code)
                desc = details["description"].lower()
                causes = details["causes"]
                solutions = details["solutions"]

                causes_str = self._format_list_pt(causes)
                solutions_str = self._format_list_pt(solutions)

                response_text = (
                    f"Luiz, a minha luz de injeção acendeu porque detectei a falha {latest_code}, que indica {desc}. "
                )
                if causes_str:
                    response_text += f"Isso pode ser causado por {causes_str}. "
                if solutions_str:
                    response_text += f"A solução recomendada é {solutions_str}."
                else:
                    response_text += "Recomendo procurarmos um mecânico para verificar."
            else:
                response_text = "Luiz, a minha luz de injeção não está acesa e não encontrei nenhuma falha registrada."

        # 2. Intenção: Temperatura
        elif any(w in normalized for w in ["temperatura", "quente", "graus", "arrefecimento", "admissao"]):
            coolant = self._latest_telemetry.get("COOLANT_TEMP")
            if coolant is not None:
                response_text = f"Luiz, a temperatura do líquido de arrefecimento do meu motor está em {int(coolant)} graus."
            else:
                response_text = "Luiz, ainda não recebi os dados de temperatura do motor."

        # 2b. Intenção: Rotação (RPM)
        elif any(w in normalized for w in ["rotacao", "rpm", "giro", "giros"]):
            rpm = self._latest_telemetry.get("RPM")
            if rpm is not None:
                response_text = f"Luiz, a rotação atual do motor está em {int(rpm)} rotações por minuto."
            else:
                response_text = "Luiz, ainda não consegui ler os dados de rotação do motor."

        # 2c. Intenção: Bateria / Alternador
        elif any(w in normalized for w in ["bateria", "alternador", "carregar", "tensao", "voltagem"]):
            voltage = self._latest_telemetry.get("CONTROL_MODULE_VOLTAGE")
            rpm = self._latest_telemetry.get("RPM")

            if voltage is not None:
                voltage_val = float(voltage)
                # Se motor estiver ligado (RPM > 500)
                if rpm is not None and float(rpm) > 500:
                    if 13.5 <= voltage_val <= 14.8:
                        response_text = (
                            f"Luiz, a tensão com o motor ligado está em {voltage_val:.1f} volts. "
                            "O seu alternador está carregando a bateria corretamente, o que indica que ele está em perfeito estado. "
                            "Se a luz da bateria pisca no painel, o culpado pode ser um mau contato nos cabos ou a bateria que já não segura carga."
                        )
                    elif voltage_val < 13.5:
                        response_text = (
                            f"Luiz, a tensão com o motor ligado está em {voltage_val:.1f} volts. "
                            "Isso está abaixo do esperado! O alternador deveria enviar acima de 13.5 volts. "
                            "Como o seu alternador é novo, recomendo checar a fiação, o aterramento ou se a correia está patinando."
                        )
                    else:
                        response_text = (
                            f"Luiz, a tensão com o motor ligado está em {voltage_val:.1f} volts. "
                            "Isso é muito alto e indica uma sobrecarga no sistema. O regulador de tensão do alternador pode estar com problemas."
                        )
                else:
                    # Motor desligado
                    if voltage_val >= 12.4:
                        response_text = f"Luiz, com o motor desligado, a bateria está com {voltage_val:.1f} volts, o que indica que a carga está saudável."
                    elif 12.0 <= voltage_val < 12.4:
                        response_text = f"Luiz, com o motor desligado, a bateria está em {voltage_val:.1f} volts. A carga está um pouco baixa, mas ainda funcional."
                    else:
                        response_text = f"Luiz, com o motor desligado, a bateria está com apenas {voltage_val:.1f} volts. Ela está fraca ou desgastada e precisa ser testada ou trocada."
            else:
                response_text = "Luiz, ainda não recebi os dados de tensão elétrica do meu sistema OBD."

        # 2d. Intenção: Sonda Lambda
        elif any(w in normalized for w in ["sonda lambda", "mistura", "oxigenio"]):
            o2_val = self._latest_telemetry.get("O2_B1S1")
            if o2_val is not None:
                o2_val_fl = float(o2_val)
                if o2_val_fl < 0.35:
                    status_str = f"em {o2_val_fl:.2f} volts, indicando mistura pobre (excesso de ar)."
                elif o2_val_fl > 0.65:
                    status_str = f"em {o2_val_fl:.2f} volts, indicando mistura rica (excesso de combustível)."
                else:
                    status_str = f"em {o2_val_fl:.2f} volts, indicando mistura estequiométrica ideal."

                response_text = (
                    f"Luiz, a leitura em tempo real da sonda lambda pré-catalisador está {status_str} "
                    "Lembrando que com o motor ligado ela deve oscilar rapidamente entre 0.1 e 0.9 volts."
                )
            else:
                response_text = "Luiz, ainda não recebi leituras válidas da sonda lambda do meu sistema OBD."

        # 3. Intenção: Combustível
        elif any(w in normalized for w in ["combustivel", "gasolina", "etanol", "tanque", "abastecer"]):
            fuel = self._latest_telemetry.get("FUEL_LEVEL")
            if fuel is not None:
                response_text = f"Luiz, meu nível de combustível está em {int(fuel)} porcento."
            else:
                response_text = "Luiz, ainda não consegui ler o sensor de nível de combustível."

        # 4. Intenção: Status Geral
        elif (
            any(w in normalized for w in ["status", "como voce esta", "como esta", "tudo bem", "tudo ok", "saude", "checklist", "funcionamento"])
            or (
                any(w in normalized for w in ["motor", "carro", "veiculo", "sistema", "sistemas"])
                and any(w in normalized for w in ["como", "com", "qual", "estado", "condicao", "condicoes", "saude"])
            )
        ):
            if self._active_dtcs:
                latest_code = self._active_dtcs[-1]
                details = await asyncio.to_thread(self._query_dtc_details, latest_code)
                desc = details["description"].lower()
                response_text = f"Luiz, estou com alertas ativos. Detectei a falha {latest_code}, que indica {desc}. É recomendável fazermos uma vistoria no motor."
            else:
                coolant = self._latest_telemetry.get("COOLANT_TEMP")
                fuel = self._latest_telemetry.get("FUEL_LEVEL")
                temp_status = f" com o motor em {int(coolant)} graus" if coolant else ""
                fuel_status = f" e o combustível em {int(fuel)} porcento" if fuel else ""
                response_text = f"Luiz, todos os meus sistemas parecem estar operando normalmente{temp_status}{fuel_status}."

        # 5. Fallback se não bater em nada
        else:
            response_text = "Luiz, desculpe, não consegui entender sua pergunta."

        # Envia a resposta gerada para o Scheduler falar
        self._logger.info(f"Resposta gerada: '{response_text}'")
        await self._event_bus.publish_to_stream(
            stream=STREAM_COMMANDS,
            event_type="voice.response",
            payload={
                "text": response_text,
                "category": "general",
            },
            source=self._name,
            priority=60,  # Prioridade para responder comandos de voz
        )

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto removendo acentos e deixando em caixa baixa."""
        text = text.lower().strip()
        return "".join(
            c for c in unicodedata.normalize("NFD", text)
            if unicodedata.category(c) != "Mn"
        )

    def _query_dtc_details(self, code: str) -> dict[str, Any]:
        """Consulta banco SQLite para buscar todos os detalhes do código DTC."""
        path = self._db_path
        if not os.path.exists(path) and os.path.exists("db/logan.db"):
            path = "db/logan.db"

        result = {
            "description": "uma falha no sistema do carro",
            "causes": [],
            "solutions": []
        }
        try:
            import json
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dtc_codes WHERE code = ?", (code,))
            row = cursor.fetchone()
            conn.close()
            if row:
                row_dict = dict(row)
                result["description"] = row_dict.get("description_pt", result["description"])
                with contextlib.suppress(Exception):
                    result["causes"] = json.loads(row_dict.get("causes", "[]"))
                with contextlib.suppress(Exception):
                    result["solutions"] = json.loads(row_dict.get("solutions", "[]"))
        except Exception as e:
            self._logger.error(f"Erro ao consultar detalhes do DTC {code} no banco: {e}")

        return result

    def _format_list_pt(self, items: list[str]) -> str:
        """Formata uma lista de strings em uma frase natural em português."""
        if not items:
            return ""
        if len(items) == 1:
            return items[0].lower()
        return ", ".join(items[:-1]).lower() + " ou " + items[-1].lower()
