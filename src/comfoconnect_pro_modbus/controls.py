"""The settings a client can change: holding registers 0x0001-0x0005 and coils.

Coil 0x0001 resets the alarms. It acts on a write of ``True`` and resets
itself, so the component writes it and never reads it.

Holding registers 0x0004 and 0x0005 read back something other than what a
client writes to them, as tested on a gateway with firmware 1.0.5. 0x0004 reads
the comfort temperature in effect, in every profile mode, while a write sets
the external setpoint. 0x0005 reads the time left on a running boost, and 0
without one, while a write sets the duration of the next boost. The component
reads them as ``comfort_temperature`` and ``boost_remaining``, and writes them
directly, so a write never stands in for the value read back.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum, IntEnum

from modbus_connection.model import NumberField, coil, enum, gauge

from .enums import TemperatureProfile, TemperatureProfileMode, VentilationPreset
from .errors import InvalidValueError
from .model import ComfoConnectComponent, address

BOOST_TIME_MAX = 86400
"""The longest boost, in seconds: 24 hours."""
# The holding registers whose writes set something other than what they read.
_EXTERNAL_SETPOINT_REGISTER = address(0x0004)
_BOOST_TIME_REGISTER = address(0x0005)
# The gateway takes this register value as 24 hours.
_BOOST_TIME_24_HOURS_RAW = 65535
EXTERNAL_SETPOINT_MIN = 0.0
EXTERNAL_SETPOINT_MAX = 40.0


def _member[E: IntEnum](enum_type: type[E]) -> Callable[[object], E]:
    """A write validator that accepts a member of ``enum_type`` or its number."""

    def _validate(value: object) -> E:
        if isinstance(value, Enum) and not isinstance(value, enum_type):
            raise InvalidValueError(f"{value!r} is not a {enum_type.__name__}")
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidValueError(f"{value!r} is not a {enum_type.__name__}")
        try:
            return enum_type(value)
        except ValueError:
            raise InvalidValueError(f"{value} is not a {enum_type.__name__}") from None

    return _validate


def _bool(value: object) -> bool:
    """A write validator that accepts only ``True`` and ``False``."""
    if not isinstance(value, bool):
        raise InvalidValueError(f"{value!r} is not a bool")
    return value


def _boost_seconds(raw: int) -> int:
    """The boost duration a register value stands for, in seconds."""
    return BOOST_TIME_MAX if raw == _BOOST_TIME_24_HOURS_RAW else raw


def _boost_time_register(seconds: float) -> int:
    """A boost duration as the register value that carries it."""
    if isinstance(seconds, float) and seconds.is_integer():
        seconds = int(seconds)
    if isinstance(seconds, bool | Enum) or not isinstance(seconds, int):
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


def _external_setpoint(celsius: object) -> float:
    """Check a setpoint against the range the library allows."""
    if isinstance(celsius, bool | Enum) or not isinstance(celsius, int | float):
        raise InvalidValueError(f"external setpoint {celsius!r} is not a number")
    # A NaN fails both comparisons, so it is rejected here too.
    if not EXTERNAL_SETPOINT_MIN <= celsius <= EXTERNAL_SETPOINT_MAX:
        raise InvalidValueError(
            f"external setpoint {celsius} °C is outside "
            f"{EXTERNAL_SETPOINT_MIN}-{EXTERNAL_SETPOINT_MAX}"
        )
    return float(celsius)


class Controls(ComfoConnectComponent):
    """Fan speed, temperature profile, boost, away function and ComfoCool.

    Every write sets an absolute value, so retrying one is safe. A
    ``ModbusTimeoutError`` on a write does not mean the gateway ignored it.
    The unit changes ``boost``, ``auto_mode`` and ``ventilation_preset`` on
    its own, for example when a boost ends.

    A preset write alone overrides auto mode for 2 hours, after which the unit
    picks the speed again. Turn ``auto_mode`` off first to keep the preset.

    The away function and a boost run on top of auto mode or a manual preset,
    and leave ``auto_mode`` as it was. ``ventilation_preset`` reads ``AWAY``
    while away is on and ``HIGH`` during a boost, and the unit returns to the
    earlier mode when either ends.
    """

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
    comfort_temperature = gauge(
        _EXTERNAL_SETPOINT_REGISTER, 0.1, signed=False, unit="°C"
    )
    """The comfort temperature in effect, in every profile mode.

    In the external setpoint mode it is the last external setpoint written.
    """
    boost_remaining: NumberField[int] = NumberField(
        _BOOST_TIME_REGISTER, signed=False, convert=_boost_seconds, unit="s"
    )
    """The time left on a running boost, in seconds, or 0 without one."""

    auto_mode = coil(address(0x0006), writable=_bool)
    boost = coil(address(0x0007), writable=_bool)
    away_function = coil(address(0x0008), writable=_bool)
    comfocool = coil(address(0x0009), writable=_bool)
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
        """Set the comfort temperature for the external setpoint mode.

        It takes effect in that mode only. ``comfort_temperature`` reads it back
        while the unit is in that mode.
        """
        tenths = round(_external_setpoint(celsius) * 10)
        await self._unit.write_register(_EXTERNAL_SETPOINT_REGISTER, tenths)

    async def async_write_boost_time(self, seconds: float) -> None:
        """Set how long the next boost lasts, in whole seconds.

        Takes up to 65534 seconds, or exactly ``BOOST_TIME_MAX``. The register
        reads back the time left on a running boost, not this duration, so
        write it before each boost to be sure of the length.
        """
        raw = _boost_time_register(seconds)
        await self._unit.write_register(_BOOST_TIME_REGISTER, raw)

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
