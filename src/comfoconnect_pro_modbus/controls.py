"""The settings a client can change: holding registers 0x0001-0x0005 and coils.

Coil 0x0001 resets the alarms. It acts on a write of ``True`` and resets
itself, so the component writes it and never reads it.
"""

from __future__ import annotations

from modbus_connection.model import coil, enum, gauge, integer

from .enums import TemperatureProfile, TemperatureProfileMode, VentilationPreset
from .model import ComfoConnectComponent, address

BOOST_TIME_24_HOURS = 65535
"""What boost time register 0x0005 holds for a boost of 24 hours."""
DAY = 86400
EXTERNAL_SETPOINT_MIN = 0.0
EXTERNAL_SETPOINT_MAX = 40.0


def _boost_time_register(seconds: int) -> int:
    """A boost duration as the register value that carries it."""
    if seconds == DAY:
        return BOOST_TIME_24_HOURS
    if not 0 <= seconds < BOOST_TIME_24_HOURS:
        raise ValueError(
            f"boost time {seconds} s is neither 0-{BOOST_TIME_24_HOURS - 1} nor {DAY}"
        )
    return seconds


def _external_setpoint(celsius: float) -> float:
    """Check a setpoint against the range the library allows."""
    if not EXTERNAL_SETPOINT_MIN <= celsius <= EXTERNAL_SETPOINT_MAX:
        raise ValueError(
            f"external setpoint {celsius} °C is outside "
            f"{EXTERNAL_SETPOINT_MIN}-{EXTERNAL_SETPOINT_MAX}"
        )
    return celsius


class Controls(ComfoConnectComponent):
    """Fan speed, temperature profile, boost, away and ComfoCool."""

    coil_ranges = ((address(0x0006), address(0x0009)),)

    ventilation_preset = enum(
        address(0x0001), VentilationPreset, writable=VentilationPreset
    )
    temperature_profile = enum(
        address(0x0002), TemperatureProfile, writable=TemperatureProfile
    )
    """Applies only in the adaptive and fixed profile modes."""
    temperature_profile_mode = enum(
        address(0x0003), TemperatureProfileMode, writable=TemperatureProfileMode
    )
    external_setpoint = gauge(
        address(0x0004), 0.1, signed=False, unit="°C", writable=_external_setpoint
    )
    """Applies only in the external setpoint profile mode."""
    _boost_time = integer(address(0x0005), signed=False)

    auto_mode = coil(address(0x0006), writable=True)
    boost = coil(address(0x0007), writable=True)
    away = coil(address(0x0008), writable=True)
    comfocool = coil(address(0x0009), writable=True)
    """Whether the ComfoCool unit may cool."""

    @property
    def boost_time(self) -> int | None:
        """How long a boost lasts, in seconds."""
        raw = self._boost_time
        if raw == BOOST_TIME_24_HOURS:
            return DAY
        return raw

    async def async_write_boost_time(self, seconds: int) -> None:
        """Set how long a boost lasts: up to 65534 seconds, or exactly one day."""
        await self._unit.write_register(address(0x0005), _boost_time_register(seconds))

    async def async_write_ventilation_preset(self, preset: VentilationPreset) -> None:
        """Switch the fans to ``preset``."""
        await self.write("ventilation_preset", preset)

    async def async_reset_errors(self) -> None:
        """Clear the unit's alarms."""
        await self._unit.write_coil(address(0x0001), True)
