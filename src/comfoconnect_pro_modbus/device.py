"""The top-level object for a ComfoConnect PRO gateway and its ventilation unit."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Self

from modbus_connection import GatewayPathUnavailableError, GatewayTargetError
from modbus_connection.model import Device, Raw

from .controls import Controls
from .enums import ConnectionState
from .model import UpdateReport
from .sensors import Sensors
from .status import ConnectionStatus, Status

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

_LOGGER = logging.getLogger(__name__)

READINGS = ("status", "sensors")
SETTINGS = ("controls",)
COMPONENTS = (*READINGS, *SETTINGS)

# The gateway answers with these when it has no path to the ventilation unit.
GATEWAY_ERRORS = (GatewayPathUnavailableError, GatewayTargetError)


class NoVentilationUnitError(Exception):
    """The gateway answered, but it does not reach a ventilation unit it serves."""

    def __init__(
        self, state: ConnectionState | None, *, unreachable: bool = False
    ) -> None:
        """Initialize the error.

        Pass ``unreachable`` when the gateway refused a read for lack of a path
        to the unit.
        """
        if unreachable:
            message = "the gateway has no path to the ventilation unit"
            if state is not None:
                message += f" (connection state {state.name})"
        else:
            shown = "nothing" if state is None else f"{state.value} ({state.name})"
            message = f"the gateway's connection state is {shown}, not 0 (OK)"
        super().__init__(message)
        self.state = state


class ComfoConnectPro(Device):
    """A ComfoAir Q or Flex unit behind a ComfoConnect PRO, through a ``ModbusUnit``."""

    def __init__(self, unit: ModbusUnit, *, timeout: float | None = None) -> None:
        """Set up the sub-systems."""
        super().__init__(unit)
        unit.require_timeout(timeout)

        self.status = Status(unit)
        self.sensors = Sensors(unit)
        self.controls = Controls(unit)

    @classmethod
    async def async_detect(
        cls, unit: ModbusUnit, *, timeout: float | None = None
    ) -> Self:
        """Read the gateway's status and build the device it describes.

        Raises ``NoVentilationUnitError`` when the gateway reports a connection
        state other than OK, or refuses a read for lack of a path to the unit.
        """
        device = cls(unit, timeout=timeout)
        link = ConnectionStatus(unit)
        try:
            await link.async_update(notify=False)
        except GATEWAY_ERRORS as err:
            _LOGGER.debug("Gateway has no path to a ventilation unit: %s", err)
            raise NoVentilationUnitError(None, unreachable=True) from err
        state = link.connection_state
        _LOGGER.debug(
            "Gateway connection state: %s", "unknown" if state is None else state.name
        )
        if state is not ConnectionState.OK:
            raise NoVentilationUnitError(state)
        try:
            await device.status.async_update(notify=False)
        except GATEWAY_ERRORS as err:
            raise NoVentilationUnitError(state, unreachable=True) from err
        return device

    async def async_update_readings(self) -> UpdateReport:
        """Refresh what the unit measures and reports: status and sensors."""
        return self._logged(await self.async_poll(READINGS))

    async def async_update_settings(self) -> UpdateReport:
        """Refresh the settings a client can change."""
        return self._logged(await self.async_poll(SETTINGS))

    async def async_update(self) -> UpdateReport:
        """Refresh readings and settings together in one report."""
        return self._logged(await self.async_poll(COMPONENTS))

    def _logged(self, report: UpdateReport) -> UpdateReport:
        """Log each component that failed to refresh, and pass the report on."""
        for name, error in report.failed.items():
            _LOGGER.debug("Component %s failed to refresh: %s", name, error)
        return report

    async def async_read_raw(self, names: Iterable[str] | None = None) -> Raw:
        """Every register and bit this device reads, undecoded, for diagnostics."""
        return await super().async_read_raw(COMPONENTS if names is None else names)
