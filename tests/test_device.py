from __future__ import annotations

import logging
from typing import Literal

import pytest
from modbus_connection import (
    GatewayPathUnavailableError,
    GatewayTargetError,
    IllegalDataAddressError,
    IllegalDataValueError,
    ModbusConnectionError,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusUnit, WriteEvent

from comfoconnect_pro_modbus import (
    AlarmCode,
    ComfoConnectPro,
    ConnectionState,
    NoVentilationUnitError,
    TemperatureProfile,
    TemperatureProfileMode,
    VentilationPreset,
    address,
    alarm,
)

from .conftest import HOLDING, INPUT, seed


def test_address_counts_from_one() -> None:
    assert address(0x0001) == 0
    assert address(0x001A) == 25


async def test_detect_reads_the_status(mock_modbus_unit: MockModbusUnit) -> None:
    seed(mock_modbus_unit)
    gateway = await ComfoConnectPro.async_detect(mock_modbus_unit, timeout=5)

    assert gateway.status.connection_state is ConnectionState.OK
    assert gateway.status.is_connected
    assert mock_modbus_unit.required_timeout == 5


@pytest.mark.parametrize(
    ("code", "state"),
    [
        (30, ConnectionState.NOT_COMFOAIR_Q),
        (40, ConnectionState.INCOMPATIBLE_VERSION),
        (50, ConnectionState.NO_VENTILATION_UNIT),
    ],
)
async def test_detect_rejects_a_gateway_without_a_unit(
    mock_modbus_unit: MockModbusUnit, code: int, state: ConnectionState
) -> None:
    seed(mock_modbus_unit, input_registers={**INPUT, 0x0001: code})
    with pytest.raises(NoVentilationUnitError, match=state.name) as caught:
        await ComfoConnectPro.async_detect(mock_modbus_unit)

    assert caught.value.state is state


async def test_detect_rejects_an_unknown_connection_state(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    seed(mock_modbus_unit, input_registers={**INPUT, 0x0001: 7})
    with pytest.raises(NoVentilationUnitError, match="nothing"):
        await ComfoConnectPro.async_detect(mock_modbus_unit)


async def test_status(gateway: ComfoConnectPro) -> None:
    report = await gateway.async_update()

    assert report.complete
    status = gateway.status
    assert status.error_flag is True
    assert status.standby is False
    assert status.comfohood is False
    assert status.filter_dirty is False
    assert status.active_error(1) is AlarmCode.FILTER_WARNING_FLAG
    assert status.active_error(2) == 0
    assert status.active_alarms == (AlarmCode.FILTER_WARNING_FLAG,)


async def test_unknown_alarm_codes_stay_numbers(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    seed(mock_modbus_unit, input_registers={**INPUT, 0x0002: 36, 0x0006: 91})
    gateway = ComfoConnectPro(mock_modbus_unit)
    await gateway.async_update()

    assert gateway.status.active_alarms == (36, AlarmCode.CC_COMP_ERR)
    assert alarm(36) == 36


async def test_alarm_slot_out_of_range(gateway: ComfoConnectPro) -> None:
    with pytest.raises(ValueError, match="no alarm slot 6"):
        gateway.status.active_error(6)


async def test_sensors(gateway: ComfoConnectPro) -> None:
    await gateway.async_update()

    sensors = gateway.sensors
    assert sensors.airflow == 175
    assert sensors.room_temperature == 21.5
    assert sensors.extract_temperature == 21.8
    assert sensors.exhaust_temperature == 5.2
    assert sensors.outdoor_temperature == -3.5
    assert sensors.supply_temperature == 19.2
    assert sensors.room_humidity == 48
    assert sensors.extract_humidity == 47
    assert sensors.exhaust_humidity == 81
    assert sensors.outdoor_humidity == 90
    assert sensors.supply_humidity == 33
    assert sensors.filter_days_remaining == 23
    assert sensors.co2(1) == 640
    assert sensors.co2(2) == 0
    assert sensors.co2_zones == {1: 640, 3: 812}


async def test_co2_zone_out_of_range(gateway: ComfoConnectPro) -> None:
    with pytest.raises(ValueError, match="no CO2 zone 9"):
        gateway.sensors.co2(9)


async def test_controls(gateway: ComfoConnectPro) -> None:
    await gateway.async_update()

    controls = gateway.controls
    assert controls.ventilation_preset is VentilationPreset.MEDIUM
    assert controls.temperature_profile is TemperatureProfile.NORMAL
    assert controls.temperature_profile_mode is TemperatureProfileMode.ADAPTIVE
    assert controls.external_setpoint == 22.0
    assert controls.boost_time == 1800
    assert controls.auto_mode is True
    assert controls.boost is False
    assert controls.away is False
    assert controls.comfocool is True


async def test_boost_time_of_a_day(mock_modbus_unit: MockModbusUnit) -> None:
    seed(mock_modbus_unit, holding={0x0005: 65535})
    gateway = ComfoConnectPro(mock_modbus_unit)
    await gateway.async_update()

    assert gateway.controls.boost_time == 86400


async def test_poll_reads_each_space_once(
    gateway: ComfoConnectPro, mock_modbus_unit: MockModbusUnit
) -> None:
    await gateway.async_update()

    reads = {
        (e.register_type, e.address, e.count) for e in mock_modbus_unit.read_events
    }
    assert reads == {
        ("input", 0, 6),
        ("discrete", 0, 4),
        ("input", 6, 20),
        ("holding", 0, 5),
        ("coil", 5, 4),
    }


@pytest.fixture
def writes(mock_modbus_unit: MockModbusUnit) -> list[WriteEvent]:
    events: list[WriteEvent] = []
    mock_modbus_unit.on_write(events.append)
    return events


async def test_write_ventilation_preset(
    gateway: ComfoConnectPro, writes: list[WriteEvent]
) -> None:
    await gateway.controls.async_write_ventilation_preset(VentilationPreset.HIGH)

    assert writes == [WriteEvent("holding", 0, [3], 0x06)]


async def test_write_external_setpoint(
    gateway: ComfoConnectPro, writes: list[WriteEvent]
) -> None:
    await gateway.controls.write("external_setpoint", 23.5)

    assert writes == [WriteEvent("holding", 3, [235], 0x06)]


async def test_write_profile(
    gateway: ComfoConnectPro, writes: list[WriteEvent]
) -> None:
    await gateway.controls.write("temperature_profile", TemperatureProfile.WARM)
    await gateway.controls.write(
        "temperature_profile_mode", TemperatureProfileMode.EXTERNAL_SETPOINT
    )

    assert writes == [
        WriteEvent("holding", 1, [2], 0x06),
        WriteEvent("holding", 2, [2], 0x06),
    ]


@pytest.mark.parametrize(
    ("seconds", "word"), [(0, 0), (600, 600), (65534, 65534), (86400, 65535)]
)
async def test_write_boost_time(
    gateway: ComfoConnectPro, writes: list[WriteEvent], seconds: int, word: int
) -> None:
    await gateway.controls.async_write_boost_time(seconds)

    assert writes == [WriteEvent("holding", 4, [word], 0x06)]


@pytest.mark.parametrize("seconds", [-1, 65535, 86399, 86401])
async def test_write_boost_time_out_of_range(
    gateway: ComfoConnectPro, writes: list[WriteEvent], seconds: int
) -> None:
    with pytest.raises(ValueError, match="boost time"):
        await gateway.controls.async_write_boost_time(seconds)

    assert writes == []


@pytest.mark.parametrize(
    ("field", "coil"), [("auto_mode", 5), ("boost", 6), ("away", 7), ("comfocool", 8)]
)
async def test_write_switch(
    gateway: ComfoConnectPro, writes: list[WriteEvent], field: str, coil: int
) -> None:
    await gateway.controls.write(field, True)
    await gateway.controls.write(field, False)

    assert writes == [
        WriteEvent("coil", coil, [True], 0x05),
        WriteEvent("coil", coil, [False], 0x05),
    ]


async def test_reset_errors(gateway: ComfoConnectPro, writes: list[WriteEvent]) -> None:
    await gateway.controls.async_reset_errors()

    assert writes == [WriteEvent("coil", 0, [True], 0x05)]


async def test_a_refused_block_keeps_the_rest(
    gateway: ComfoConnectPro, mock_modbus_unit: MockModbusUnit
) -> None:
    mock_modbus_unit.fail_read(
        address(0x0006), IllegalDataAddressError(), register_type="coil"
    )
    report = await gateway.async_update()

    assert report.updated == {"status", "sensors"}
    assert set(report.failed) == {"controls"}
    assert gateway.sensors.airflow == 175


async def test_a_dead_link_raises(
    gateway: ComfoConnectPro, mock_modbus_unit: MockModbusUnit
) -> None:
    mock_modbus_unit.fail_requests(ModbusConnectionError("gone"))
    with pytest.raises(ModbusConnectionError):
        await gateway.async_update()


async def test_a_timeout_before_any_answer_raises(
    gateway: ComfoConnectPro, mock_modbus_unit: MockModbusUnit
) -> None:
    mock_modbus_unit.fail_requests(ModbusTimeoutError())
    with pytest.raises(ModbusTimeoutError):
        await gateway.async_update()


async def test_read_raw(gateway: ComfoConnectPro) -> None:
    raw = await gateway.async_read_raw()

    assert raw["input"][0] == 0
    assert raw["input"][25] == 23
    assert raw["discrete"][0] is True
    assert raw["holding"][0] == 2
    assert raw["coil"][8] is True


async def test_logs_the_connection_state(
    mock_modbus_unit: MockModbusUnit, caplog: pytest.LogCaptureFixture
) -> None:
    seed(mock_modbus_unit)
    with caplog.at_level(logging.DEBUG, logger="comfoconnect_pro_modbus"):
        await ComfoConnectPro.async_detect(mock_modbus_unit)

    assert "Gateway connection state: OK" in caplog.text


async def test_logs_failed_components(
    gateway: ComfoConnectPro,
    mock_modbus_unit: MockModbusUnit,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mock_modbus_unit.fail_read(
        address(0x0006), IllegalDataAddressError(), register_type="coil"
    )
    with caplog.at_level(logging.DEBUG, logger="comfoconnect_pro_modbus"):
        await gateway.async_update()

    assert "Component controls failed to refresh" in caplog.text


@pytest.mark.parametrize("error", [GatewayPathUnavailableError(), GatewayTargetError()])
async def test_detect_maps_a_gateway_without_a_path(
    mock_modbus_unit: MockModbusUnit, error: Exception
) -> None:
    seed(mock_modbus_unit, input_registers={**INPUT, 0x0001: 50})
    mock_modbus_unit.fail_read(address(0x0001), error, register_type="discrete")
    with pytest.raises(NoVentilationUnitError, match="NO_VENTILATION_UNIT"):
        await ComfoConnectPro.async_detect(mock_modbus_unit)


async def test_detect_maps_a_refused_connection_state(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    seed(mock_modbus_unit)
    mock_modbus_unit.fail_read(
        address(0x0001), GatewayPathUnavailableError(), register_type="input"
    )
    with pytest.raises(NoVentilationUnitError, match="no path") as caught:
        await ComfoConnectPro.async_detect(mock_modbus_unit)

    assert caught.value.state is None


async def test_detect_maps_a_path_lost_after_the_state(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    seed(mock_modbus_unit)
    mock_modbus_unit.fail_read(
        address(0x0001), GatewayPathUnavailableError(), register_type="discrete"
    )
    with pytest.raises(
        NoVentilationUnitError, match=r"no path.*\(connection state OK\)"
    ):
        await ComfoConnectPro.async_detect(mock_modbus_unit)


@pytest.mark.parametrize(("celsius", "word"), [(0.0, 0), (22.1, 221), (40.0, 400)])
async def test_write_external_setpoint_in_range(
    gateway: ComfoConnectPro, writes: list[WriteEvent], celsius: float, word: int
) -> None:
    await gateway.controls.write("external_setpoint", celsius)

    assert writes == [WriteEvent("holding", 3, [word], 0x06)]


@pytest.mark.parametrize("celsius", [-1.0, 40.1, 7000.0])
async def test_write_external_setpoint_out_of_range(
    gateway: ComfoConnectPro, writes: list[WriteEvent], celsius: float
) -> None:
    with pytest.raises(ValueError, match="external setpoint"):
        await gateway.controls.write("external_setpoint", celsius)

    assert writes == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ventilation_preset", 9),
        ("temperature_profile", 3),
        ("temperature_profile_mode", -1),
    ],
)
async def test_write_enum_out_of_range(
    gateway: ComfoConnectPro, writes: list[WriteEvent], field: str, value: int
) -> None:
    with pytest.raises(ValueError, match=str(value)):
        await gateway.controls.write(field, value)

    assert writes == []


async def test_write_enum_accepts_a_plain_number(
    gateway: ComfoConnectPro, writes: list[WriteEvent]
) -> None:
    await gateway.controls.write("ventilation_preset", 1)

    assert writes == [WriteEvent("holding", 0, [1], 0x06)]


async def test_reads_the_protocol_addresses(mock_modbus_unit: MockModbusUnit) -> None:
    # Use literal protocol addresses so an off-by-one in address() fails here
    mock_modbus_unit.input[0] = 0
    mock_modbus_unit.input[6] = 175
    mock_modbus_unit.input[25] = 23
    mock_modbus_unit.discrete[3] = True
    mock_modbus_unit.holding[4] = 900
    mock_modbus_unit.coil[8] = True
    gateway = await ComfoConnectPro.async_detect(mock_modbus_unit)
    await gateway.async_update()

    assert gateway.sensors.airflow == 175
    assert gateway.sensors.filter_days_remaining == 23
    assert gateway.status.filter_dirty is True
    assert gateway.controls.boost_time == 900
    assert gateway.controls.comfocool is True


async def test_a_refused_write_raises(
    gateway: ComfoConnectPro, mock_modbus_unit: MockModbusUnit
) -> None:
    mock_modbus_unit.fail_write(address(0x0001), IllegalDataValueError())
    with pytest.raises(IllegalDataValueError):
        await gateway.controls.async_write_ventilation_preset(VentilationPreset.LOW)


async def test_an_unknown_preset_decodes_to_none(
    mock_modbus_unit: MockModbusUnit, caplog: pytest.LogCaptureFixture
) -> None:
    seed(mock_modbus_unit, holding={**HOLDING, 0x0001: 7})
    gateway = ComfoConnectPro(mock_modbus_unit)
    await gateway.async_update()

    assert gateway.controls.ventilation_preset is None
    assert "has no mapping for value 7" in caplog.text


async def test_values_before_the_first_update(gateway: ComfoConnectPro) -> None:
    assert gateway.controls.boost_time is None
    assert gateway.sensors.co2(1) is None
    assert gateway.sensors.co2_zones == {}
    assert gateway.status.active_alarms == ()


@pytest.mark.parametrize(
    ("space", "number", "failed"),
    [
        ("discrete", 0x0001, "status"),
        ("input", 0x0007, "sensors"),
        ("holding", 0x0001, "controls"),
    ],
)
async def test_a_refused_block_keeps_the_other_components(
    gateway: ComfoConnectPro,
    mock_modbus_unit: MockModbusUnit,
    space: Literal["discrete", "input", "holding"],
    number: int,
    failed: str,
) -> None:
    mock_modbus_unit.fail_read(
        address(number), IllegalDataAddressError(), register_type=space
    )
    report = await gateway.async_update()

    assert set(report.failed) == {failed}
    assert report.updated == {"status", "sensors", "controls"} - {failed}
