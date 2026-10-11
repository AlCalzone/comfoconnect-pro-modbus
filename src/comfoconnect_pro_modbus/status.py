"""The gateway's link state, the unit's alarms and its status flags."""

from __future__ import annotations

from modbus_connection.model import NumberField, discrete_input, enum

from .enums import AlarmCode, ConnectionState
from .model import ComfoConnectComponent, address

ALARM_SLOTS = 5


def alarm(code: int) -> AlarmCode | int:
    """The ``AlarmCode`` for ``code``, or the bare number for a code it lacks."""
    try:
        return AlarmCode(code)
    except ValueError:
        return code


class ConnectionStatus(ComfoConnectComponent):
    """Input register 0x0001 alone, which the gateway serves without a unit."""

    register_space = "input"

    connection_state = enum(address(0x0001), ConnectionState)


class Status(ComfoConnectComponent):
    """Input registers 0x0001 to 0x0006 and discrete inputs 0x0001 to 0x0004."""

    register_space = "input"

    connection_state = enum(address(0x0001), ConnectionState)
    active_error_1: NumberField[AlarmCode | int] = NumberField(
        address(0x0002), signed=False, convert=alarm
    )
    """The first active alarm, or 0."""
    active_error_2: NumberField[AlarmCode | int] = NumberField(
        address(0x0003), signed=False, convert=alarm
    )
    active_error_3: NumberField[AlarmCode | int] = NumberField(
        address(0x0004), signed=False, convert=alarm
    )
    active_error_4: NumberField[AlarmCode | int] = NumberField(
        address(0x0005), signed=False, convert=alarm
    )
    active_error_5: NumberField[AlarmCode | int] = NumberField(
        address(0x0006), signed=False, convert=alarm
    )

    error_flag = discrete_input(address(0x0001))
    """At least one alarm is active."""
    standby = discrete_input(address(0x0002))
    comfohood = discrete_input(address(0x0003))
    """The ComfoHood cooker hood is on."""
    filter_dirty = discrete_input(address(0x0004))
    """The filters must be replaced."""

    @property
    def is_connected(self) -> bool:
        """Whether the gateway reaches a ventilation unit it can serve."""
        return self.connection_state is ConnectionState.OK

    def active_error(self, slot: int) -> AlarmCode | int | None:
        """Alarm slot ``slot``, from 1 to 5; 0 means no alarm in that slot."""
        if not 1 <= slot <= ALARM_SLOTS:
            raise ValueError(f"no alarm slot {slot}")
        code: AlarmCode | int | None = getattr(self, f"active_error_{slot}")
        return code

    @property
    def active_alarms(self) -> tuple[AlarmCode | int, ...]:
        """The alarms in the five slots, without the empty ones."""
        codes = (self.active_error(slot) for slot in range(1, ALARM_SLOTS + 1))
        return tuple(code for code in codes if code)
