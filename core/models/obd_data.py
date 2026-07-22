# Logan AI — Modelo de Dados OBD

"""
Modelos de dados para telemetria OBD-II.
Encapsulam leituras brutas do veículo em estruturas tipadas.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class OBDReading:
    """Uma leitura individual de um sensor OBD-II.

    Attributes:
        command: Nome do comando OBD (e.g., "COOLANT_TEMP").
        value: Valor lido (numérico ou string).
        unit: Unidade de medida (e.g., "°C", "RPM", "%").
        timestamp: Momento da leitura.
        is_valid: Se a leitura é válida.
    """

    command: str
    value: float | int | str | None
    unit: str = ""
    timestamp: float = field(default_factory=time.time)
    is_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OBDSnapshot:
    """Snapshot completo de todos os sensores OBD em um momento.

    Attributes:
        coolant_temp: Temperatura do líquido de arrefecimento (°C).
        intake_temp: Temperatura do ar de admissão (°C).
        rpm: Rotações por minuto.
        speed: Velocidade do veículo (km/h).
        throttle_position: Posição do acelerador (%).
        fuel_level: Nível de combustível (%).
        engine_load: Carga do motor (%).
        map_pressure: Pressão absoluta do coletor (kPa).
        maf_rate: Taxa de fluxo de ar (g/s).
        lambda_value: Valor da sonda lambda (ratio).
        battery_voltage: Voltagem da bateria (V).
        timing_advance: Avanço de ignição (°).
        short_fuel_trim: Correção de combustível curto prazo (%).
        long_fuel_trim: Correção de combustível longo prazo (%).
        fuel_pressure: Pressão de combustível (kPa).
        timestamp: Momento do snapshot.
    """

    coolant_temp: float | None = None
    intake_temp: float | None = None
    rpm: float | None = None
    speed: float | None = None
    throttle_position: float | None = None
    fuel_level: float | None = None
    engine_load: float | None = None
    map_pressure: float | None = None
    maf_rate: float | None = None
    lambda_value: float | None = None
    battery_voltage: float | None = None
    timing_advance: float | None = None
    short_fuel_trim: float | None = None
    long_fuel_trim: float | None = None
    fuel_pressure: float | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_readings(cls, readings: list[OBDReading]) -> OBDSnapshot:
        """Constrói um snapshot a partir de lista de leituras individuais.

        Mapeia o nome do comando OBD para o campo do snapshot.
        """
        field_map = {
            "COOLANT_TEMP": "coolant_temp",
            "INTAKE_TEMP": "intake_temp",
            "RPM": "rpm",
            "SPEED": "speed",
            "THROTTLE_POS": "throttle_position",
            "FUEL_LEVEL": "fuel_level",
            "ENGINE_LOAD": "engine_load",
            "INTAKE_PRESSURE": "map_pressure",
            "MAF": "maf_rate",
            "O2_B1S1": "lambda_value",
            "CONTROL_MODULE_VOLTAGE": "battery_voltage",
            "TIMING_ADVANCE": "timing_advance",
            "SHORT_FUEL_TRIM_1": "short_fuel_trim",
            "LONG_FUEL_TRIM_1": "long_fuel_trim",
            "FUEL_PRESSURE": "fuel_pressure",
        }

        kwargs: dict[str, Any] = {}
        for reading in readings:
            if reading.is_valid and reading.command in field_map:
                kwargs[field_map[reading.command]] = reading.value

        return cls(**kwargs)


@dataclass(slots=True)
class DTCCode:
    """Código de Diagnóstico de Problema (DTC).

    Attributes:
        code: Código DTC (e.g., "P0300").
        description: Descrição do código.
        severity: Gravidade (info, warning, critical).
        system: Sistema afetado (motor, transmissão, etc).
        causes: Possíveis causas.
        solutions: Possíveis soluções.
    """

    code: str
    description: str = ""
    severity: str = "warning"
    system: str = ""
    causes: list[str] = field(default_factory=list)
    solutions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
