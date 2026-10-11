"""The settings a client can change: holding registers 0x0001-0x0005 and coils.

Coil 0x0001 resets the alarms. It acts on a write of ``True`` and resets
itself, so the component writes it and never reads it.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import IntEnum

from modbus_connection.model import NumberField, coil, enum, gauge

from .enums import TemperatureProfile, TemperatureProfileMode, VentilationPreset
from .errors import InvalidValueError
from .model import ComfoConnectComponent, address

BOOST_TIME_MAX = 86400
"""The longest boost, in seconds: 24 hours."""
# The gateway takes this register value as 24 hours.
_BOOST_TIME_24_HOURS_RAW = 65535
EXTERNAL_SETPOINT_MIN = 0.0
EXTERNAL_SETPOINT_MAX = 40.0


def _member[E: IntEnum](enum_type: type[E]) -> Callable[[object], E]:
    """A write validator that accepts a member of ``enum_type`` or its number."""

    def _validate(value: object) -> E:
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidValueError(f"{value!r} is not a {enum_type.__name__}")
        try:
            return enum_type(value)
        except ValueError:
            raise InvalidValueError(f"{value} is not a {enum_type.__name__}") from None

    return _validate


def _boost_seconds(raw: int) -> int:
    """The boost duration a register value stands for, in seconds."""
    return BOOST_TIME_MAX if raw == _BOOST_TIME_24_HOURS_RAW else raw


def _boost_time_register(seconds: int) -> int:
    """A boost duration as the register value that carries it."""
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        raise InvalidValueError(
            f"boost time {seconds!r} is not a whole number of seconds"
        )
    if seconds == BOOST_TIME_MAX:
        return _BOOST_TIME_24_HOURS_RAW
    if not 0 <= seconds < _BOOST_TIME_24_HOURS_RAW:
        raise InvalidValueError(
            f"boost time {seconds} s is neither "
            f"0-{_BOOST_TIME_24_HOURS_RAW - 1} nor {BOOST_TIME_MAX}"
        )
    return seconds


def _external_setpoint(celsius: float) -> float:
    """Check a setpoint against the range the library allows."""
    if not EXTERNAL_SETPOINT_MIN <= celsius <= EXTERNAL_SETPOINT_MAX:
        raise InvalidValueError(
            f"external setpoint {celsius} °C is outside "
            f"{EXTERNAL_SETPOINT_MIN}-{EXTERNAL_SETPOINT_MAX}"
        )
    return celsius


class Controls(ComfoConnectComponent):
    """Fan speed, temperature profile, boost, away function and ComfoCool."""

    coil_ranges = ((address(0x0006), address(0x0009)),)

    ventilation_preset = enum(
        address(0x0001), VentilationPreset, writable=_member(VentilationPreset)
    )
    temperature_profile = enum(
        address(0x0002), TemperatureProfile, writable=_member(TemperatureProfile)
    )
    """Applies only in the adaptive and fixed profile modes."""
    temperature_profile_mode = enum(
        address(0x0003),
        TemperatureProfileMode,
        writable=_member(TemperatureProfileMode),
    )
    external_setpoint = gauge(
        address(0x0004), 0.1, signed=False, unit="°C", writable=_external_setpoint
    )
    """Applies only in the external setpoint profile mode."""
    boost_time: NumberField[int] = NumberField(
        address(0x0005),
        signed=False,
        convert=_boost_seconds,
        writable=_boost_time_register,
        unit="s",
    )
    """How long a boost lasts, in seconds."""

    auto_mode = coil(address(0x0006), writable=True)
    boost = coil(address(0x0007), writable=True)
    away_function = coil(address(0x0008), writable=True)
    comfocool = coil(address(0x0009), writable=True)
    """Whether the ComfoCool unit may cool."""

    async def async_write_ventilation_preset(self, preset: VentilationPreset) -> None:
        """Switch the fans to ``preset``."""
        await self.write("ventilation_preset", preset)

    async def async_write_temperature_profile(
        self, profile: TemperatureProfile
    ) -> None:
        """Set the comfort temperature profile."""
        await self.write("temperature_profile", profile)

    async def async_write_temperature_profile_mode(
        self, mode: TemperatureProfileMode
    ) -> None:
        """Set how the comfort temperature is chosen."""
        await self.write("temperature_profile_mode", mode)

    async def async_write_external_setpoint(self, celsius: float) -> None:
        """Set the comfort temperature for the external setpoint mode."""
        await self.write("external_setpoint", celsius)

    async def async_write_boost_time(self, seconds: int) -> None:
        """Set how long a boost lasts: up to 65534 seconds, or exactly one day."""
        await self.write("boost_time", seconds)

    async def async_write_auto_mode(self, on: bool) -> None:
        """Let the unit pick the fan speed itself, or stop it."""
        await self.write("auto_mode", on)

    async def async_write_boost(self, on: bool) -> None:
        """Start or stop a boost."""
        await self.write("boost", on)

    async def async_write_away_function(self, on: bool) -> None:
        """Turn the away function on or off."""
        await self.write("away_function", on)

    async def async_write_comfocool(self, on: bool) -> None:
        """Allow or stop ComfoCool cooling."""
        await self.write("comfocool", on)

    async def async_reset_errors(self) -> None:
        """Clear the unit's alarms."""
        await self._unit.write_coil(address(0x0001), True)
