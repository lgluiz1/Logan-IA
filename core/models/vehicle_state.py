# Logan AI — Estado do Veículo

"""
Modelo de estado centralizado do veículo.
Representa a visão mais recente de todos os sensores e condições.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from core.enums import DriverState
from core.models.obd_data import OBDSnapshot


@dataclass(slots=True)
class VehicleState:
    """Estado consolidado do veículo.

    Este objeto é mantido pelo Supervisor e representa a visão
    mais atualizada de todos os dados do veículo.

    Attributes:
        obd_connected: Status da conexão OBD-II.
        obd_state: Estado do driver OBD.
        engine_running: Se o motor está ligado.
        latest_snapshot: Snapshot mais recente dos sensores.
        active_dtcs: Códigos DTC ativos.
        trip_active: Se há viagem em andamento.
        trip_start_time: Início da viagem atual.
        trip_distance_km: Distância da viagem atual.
        last_update: Último update recebido.
    """

    obd_connected: bool = False
    obd_state: DriverState = DriverState.DISCONNECTED
    engine_running: bool = False
    latest_snapshot: OBDSnapshot | None = None
    active_dtcs: list[str] = field(default_factory=list)
    trip_active: bool = False
    trip_start_time: float | None = None
    trip_distance_km: float = 0.0
    last_update: float = field(default_factory=time.time)

    def update_snapshot(self, snapshot: OBDSnapshot) -> None:
        """Atualiza o snapshot mais recente."""
        self.latest_snapshot = snapshot
        self.last_update = time.time()

        # Motor ligado = RPM > 0
        if snapshot.rpm is not None:
            self.engine_running = snapshot.rpm > 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["obd_state"] = self.obd_state.value
        return data
