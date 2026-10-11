"""Read and control Zehnder ventilation units through a ComfoConnect PRO."""

from .controls import (
    BOOST_TIME_MAX,
    EXTERNAL_SETPOINT_MAX,
    EXTERNAL_SETPOINT_MIN,
    Controls,
)
from .device import (
    COMPONENTS,
    READINGS,
    SETTINGS,
    ComfoConnectPro,
    NoVentilationUnitError,
)
from .enums import (
    AlarmCode,
    ConnectionState,
    TemperatureProfile,
    TemperatureProfileMode,
    VentilationPreset,
)
from .model import UpdateReport, address
from .sensors import CO2_ZONES, Sensors
from .status import ALARM_SLOTS, Status

__all__ = [
    "ALARM_SLOTS",
    "BOOST_TIME_MAX",
    "CO2_ZONES",
    "COMPONENTS",
    "EXTERNAL_SETPOINT_MAX",
    "EXTERNAL_SETPOINT_MIN",
    "READINGS",
    "SETTINGS",
    "AlarmCode",
    "ComfoConnectPro",
    "ConnectionState",
    "Controls",
    "NoVentilationUnitError",
    "Sensors",
    "Status",
    "TemperatureProfile",
    "TemperatureProfileMode",
    "UpdateReport",
    "VentilationPreset",
    "address",
]
