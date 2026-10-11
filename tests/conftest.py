"""Fixtures: a ComfoConnect PRO on modbus-connection's in-memory mock."""

from __future__ import annotations

import pytest
from modbus_connection.mock import MockModbusUnit

from comfoconnect_pro_modbus import ComfoConnectPro
from comfoconnect_pro_modbus.model import address


def signed(value: int) -> int:
    """A signed 16-bit value as the register word that carries it."""
    return value & 0xFFFF


# Keys are the manual's addresses; ``seed`` shifts them to protocol addresses.
DISCRETE: dict[int, bool] = {
    0x0001: True,  # error flag
    0x0002: False,  # standby
    0x0003: False,  # ComfoHood
    0x0004: False,  # filter dirty
}
INPUT: dict[int, int] = {
    0x0001: 0,  # connection OK
    0x0002: 79,  # filter warning
    0x0003: 0,
    0x0004: 0,
    0x0005: 0,
    0x0006: 0,
    0x0007: 175,  # m³/h
    0x0008: 215,  # room 21.5 °C
    0x0009: 218,
    0x000A: 52,
    0x000B: signed(-35),  # outdoor -3.5 °C
    0x000C: 192,
    0x000D: 48,
    0x000E: 47,
    0x000F: 81,
    0x0010: 90,
    0x0011: 33,
    0x0012: 640,  # CO₂ zone 1
    0x0013: 0,
    0x0014: 812,  # CO₂ zone 3
    0x001A: 23,  # filter days remaining
}
HOLDING: dict[int, int] = {
    0x0001: 2,  # medium
    0x0002: 0,  # normal
    0x0003: 0,  # adaptive
    0x0004: 220,  # 22.0 °C
    0x0005: 1800,  # 30 minutes
}
COIL: dict[int, bool] = {
    0x0006: True,  # auto mode
    0x0007: False,  # boost
    0x0008: False,  # away
    0x0009: True,  # ComfoCool
}


def seed(
    unit: MockModbusUnit,
    *,
    discrete: dict[int, bool] = DISCRETE,
    input_registers: dict[int, int] = INPUT,
    holding: dict[int, int] = HOLDING,
    coil: dict[int, bool] = COIL,
) -> None:
    """Load values, given by the manual's addresses, into the mock."""
    for number, bit in discrete.items():
        unit.discrete[address(number)] = bit
    for number, word in input_registers.items():
        unit.input[address(number)] = word
    for number, word in holding.items():
        unit.holding[address(number)] = word
    for number, bit in coil.items():
        unit.coil[address(number)] = bit


@pytest.fixture
def gateway(mock_modbus_unit: MockModbusUnit) -> ComfoConnectPro:
    """A gateway reaching a ComfoAir Q with two CO₂ sensors."""
    seed(mock_modbus_unit)
    return ComfoConnectPro(mock_modbus_unit)
