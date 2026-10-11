from __future__ import annotations

import logging
from typing import Any, Literal

import pytest
from modbus_connection import (
    GatewayPathUnavailableError,
    GatewayTargetError,
    IllegalDataAddressError,
    IllegalDataValueError,
    ModbusConnectionError,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusUnit, ReadEvent, WriteEvent

from comfoconnect_pro_modbus import (
    DEFAULT_UNIT_ID,
    AlarmCode,
    ComfoConnectPro,
    ComfoConnectProError,
    ConnectionState,
    InvalidValueError,
    NoVentilationUnitError,
    TemperatureProfile,
    TemperatureProfileMode,
    VentilationPreset,
)
from comfoconnect_pro_modbus.model import address

from .conftest import HOLDING, INPUT, seed

GATEWAY_ERRORS = [GatewayPathUnavailableError(), GatewayTargetError()]


@pytest.fixture
def writes(mock_modbus_unit: MockModbusUnit) -> list[WriteEvent]:
    events: list[WriteEvent] = []
    mock_modbus_unit.on_write(events.append)
    return events


def test_address_counts_from_one() -> None:
    assert address(0x0001) == 0
    assert address(0x001A) == 25


def test_default_unit_id() -> None:
    assert DEFAULT_UNIT_ID == 1


def test_library_errors_share_a_base() -> None:
    assert issubclass(NoVentilationUnitError, ComfoConnectProError)
    assert issubclass(InvalidValueError, ComfoConnectProError)
    assert issubclass(InvalidValueError, ValueError)


async def test_detect_reads_the_status(mock_modbus_unit: MockModbusUnit) -> None:
    seed(mock_modbus_unit)
    gateway = await ComfoConnectPro.async_detect(mock_modbus_unit, timeout=5)

    assert gateway.status.connection_state is ConnectionState.OK
    assert gateway.status.is_connected
    assert gateway.status.connection_code == 0
    assert mock_modbus_unit.required_timeout == 5


@pytest.mark.parametrize(
    ("code", "state"),
    [
        (30, ConnectionState.NOT_COMFOAIR_Q),
        (40, ConnectionState.INCOMPATIBLE_VERSION),
        (50, ConnectionState.NO_VENTILATION_UNIT),
        (7, None),
    ],
)
async def test_detect_rejects_a_bad_state_after_one_read(
    mock_modbus_unit: MockModbusUnit, code: int, state: ConnectionState | None
) -> None:
    seed(mock_modbus_unit, input_registers={**INPUT, 0x0001: code})
    with pytest.raises(NoVentilationUnitError) as caught:
        await ComfoConnectPro.async_detect(mock_modbus_unit, timeout=5)

    assert caught.value.state is state
    assert caught.value.code == code
    assert f"connection state is {code} (" in str(caught.value)
    assert mock_modbus_unit.read_events == [ReadEvent("input", 0, 1)]
    assert mock_modbus_unit.required_timeout is None


@pytest.mark.parametrize("error", GATEWAY_ERRORS)
async def test_detect_maps_a_refused_state_read(
    mock_modbus_unit: MockModbusUnit, error: Exception
) -> None:
    seed(mock_modbus_unit)
    mock_modbus_unit.fail_read(address(0x0001), error, register_type="input")
    with pytest.raises(NoVentilationUnitError, match="has no path") as caught:
        await ComfoConnectPro.async_detect(mock_modbus_unit)

    assert caught.value.state is None


@pytest.mark.parametrize("error", GATEWAY_ERRORS)
async def test_detect_maps_a_path_lost_after_the_state(
    mock_modbus_unit: MockModbusUnit, error: Exception
) -> None:
    seed(mock_modbus_unit)
    mock_modbus_unit.fail_read(address(0x0001), error, register_type="discrete")
    with pytest.raises(NoVentilationUnitError, match="OK, then lost") as caught:
        await ComfoConnectPro.async_detect(mock_modbus_unit)

    assert caught.value.state is ConnectionState.OK


async def test_constructor_asks_for_a_given_timeout(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    ComfoConnectPro(mock_modbus_unit, timeout=4)

    assert mock_modbus_unit.required_timeout == 4


async def test_constructor_keeps_a_timeout_another_user_asked_for(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.require_timeout(3)
    ComfoConnectPro(mock_modbus_unit)

    assert mock_modbus_unit.required_timeout == 3


async def test_logs_the_connection_state(
    mock_modbus_unit: MockModbusUnit, caplog: pytest.LogCaptureFixture
) -> None:
    seed(mock_modbus_unit)
    with caplog.at_level(logging.DEBUG, logger="comfoconnect_pro_modbus"):
        await ComfoConnectPro.async_detect(mock_modbus_unit)

    assert "Gateway connection state: OK" in caplog.text


async def test_warns_once_per_failing_component(
    gateway: ComfoConnectPro,
    mock_modbus_unit: MockModbusUnit,
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = GatewayPathUnavailableError()
    mock_modbus_unit.fail_read(address(0x0001), error, register_type="holding")
    with caplog.at_level(logging.DEBUG, logger="comfoconnect_pro_modbus"):
        await gateway.async_update()
        await gateway.async_update()
        mock_modbus_unit.fail_read(address(0x0001), None, register_type="holding")
        await gateway.async_update()

    levels = [(r.levelname, r.getMessage().split(":")[0]) for r in caplog.records]
    assert levels == [
        ("WARNING", "Component controls failed to refresh"),
        ("DEBUG", "Component controls still fails to refresh"),
        ("INFO", "Component controls refreshes again"),
    ]


async def test_status(gateway: ComfoConnectPro) -> None:
    report = await gateway.async_update()

    assert report.complete
    status = gateway.status
    assert status.error_flag is True
    assert status.standby is False
    assert status.comfohood is False
    assert status.filter_dirty is False
    assert status.active_error_1 is AlarmCode.FILTER_WARNING_FLAG
    assert status.active_error(1) is AlarmCode.FILTER_WARNING_FLAG
    assert status.active_error(2) == 0
    assert status.active_alarms == (AlarmCode.FILTER_WARNING_FLAG,)


async def test_status_keeps_an_unknown_state_code(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    seed(mock_modbus_unit, input_registers={**INPUT, 0x0001: 7})
    gateway = ComfoConnectPro(mock_modbus_unit)
    await gateway.async_update()

    assert gateway.status.connection_state is None
    assert gateway.status.connection_code == 7
    assert not gateway.status.is_connected


async def test_unknown_alarm_codes_stay_numbers(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    seed(mock_modbus_unit, input_registers={**INPUT, 0x0002: 36, 0x0006: 91})
    gateway = ComfoConnectPro(mock_modbus_unit)
    await gateway.async_update()

    assert gateway.status.active_alarms == (36, AlarmCode.CC_COMP_ERR)


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
    assert controls.away_function is False
    assert controls.comfocool is True


async def test_boost_time_of_a_day(mock_modbus_unit: MockModbusUnit) -> None:
    seed(mock_modbus_unit, holding={0x0005: 65535})
    gateway = ComfoConnectPro(mock_modbus_unit)
    await gateway.async_update()

    assert gateway.controls.boost_time == 86400


async def test_values_before_the_first_update(gateway: ComfoConnectPro) -> None:
    assert gateway.status.connection_state is None
    assert gateway.status.active_error(1) is None
    assert gateway.status.active_alarms == ()
    assert gateway.controls.boost_time is None
    assert gateway.sensors.co2(1) is None
    assert gateway.sensors.co2_zones == {}


@pytest.mark.parametrize(
    ("call", "match"),
    [
        (lambda gateway: gateway.status.active_error(0), "no alarm slot 0"),
        (lambda gateway: gateway.status.active_error(6), "no alarm slot 6"),
        (lambda gateway: gateway.sensors.co2(0), "no CO2 zone 0"),
        (lambda gateway: gateway.sensors.co2(9), "no CO2 zone 9"),
    ],
)
async def test_index_out_of_range(
    gateway: ComfoConnectPro, call: Any, match: str
) -> None:
    with pytest.raises(InvalidValueError, match=match):
        call(gateway)


@pytest.mark.parametrize(
    ("field", "number", "value"),
    [
        ("ventilation_preset", 0x0001, 7),
        ("temperature_profile", 0x0002, 3),
        ("temperature_profile_mode", 0x0003, 3),
    ],
)
async def test_an_unknown_enum_value_decodes_to_none(
    mock_modbus_unit: MockModbusUnit,
    caplog: pytest.LogCaptureFixture,
    field: str,
    number: int,
    value: int,
) -> None:
    seed(mock_modbus_unit, holding={**HOLDING, number: value})
    gateway = ComfoConnectPro(mock_modbus_unit)
    await gateway.async_update()

    assert getattr(gateway.controls, field) is None
    assert f"has no mapping for value {value}" in caplog.text


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


async def test_readings_and_settings_poll_apart(gateway: ComfoConnectPro) -> None:
    readings = await gateway.async_update_readings()
    assert readings.updated == {"status", "sensors"}
    assert gateway.controls.ventilation_preset is None

    settings = await gateway.async_update_settings()
    assert settings.updated == {"controls"}
    assert gateway.controls.ventilation_preset is VentilationPreset.MEDIUM


@pytest.mark.parametrize(
    ("space", "number", "failed"),
    [
        ("discrete", 0x0001, "status"),
        ("input", 0x0007, "sensors"),
        ("holding", 0x0001, "controls"),
        ("coil", 0x0006, "controls"),
    ],
)
async def test_a_refused_block_keeps_the_other_components(
    gateway: ComfoConnectPro,
    mock_modbus_unit: MockModbusUnit,
    space: Literal["discrete", "input", "holding", "coil"],
    number: int,
    failed: str,
) -> None:
    mock_modbus_unit.fail_read(
        address(number), IllegalDataAddressError(), register_type=space
    )
    report = await gateway.async_update()

    assert set(report.failed) == {failed}
    assert report.updated == {"status", "sensors", "controls"} - {failed}


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


@pytest.mark.parametrize(
    ("helper", "value", "event"),
    [
        (
            "async_write_ventilation_preset",
            VentilationPreset.HIGH,
            WriteEvent("holding", 0, [3], 0x06),
        ),
        (
            "async_write_temperature_profile",
            TemperatureProfile.WARM,
            WriteEvent("holding", 1, [2], 0x06),
        ),
        (
            "async_write_temperature_profile_mode",
            TemperatureProfileMode.EXTERNAL_SETPOINT,
            WriteEvent("holding", 2, [2], 0x06),
        ),
        ("async_write_external_setpoint", 22.1, WriteEvent("holding", 3, [221], 0x06)),
        ("async_write_boost_time", 600, WriteEvent("holding", 4, [600], 0x06)),
        ("async_write_boost_time", 3600.0, WriteEvent("holding", 4, [3600], 0x06)),
        ("async_write_boost_time", 86400, WriteEvent("holding", 4, [65535], 0x06)),
        ("async_write_auto_mode", True, WriteEvent("coil", 5, [True], 0x05)),
        ("async_write_boost", False, WriteEvent("coil", 6, [False], 0x05)),
        ("async_write_away_function", True, WriteEvent("coil", 7, [True], 0x05)),
        ("async_write_comfocool", False, WriteEvent("coil", 8, [False], 0x05)),
    ],
)
async def test_write_helpers(
    gateway: ComfoConnectPro,
    writes: list[WriteEvent],
    helper: str,
    value: object,
    event: WriteEvent,
) -> None:
    await getattr(gateway.controls, helper)(value)

    assert writes == [event]


async def test_write_by_name(
    gateway: ComfoConnectPro, writes: list[WriteEvent]
) -> None:
    await gateway.controls.write("ventilation_preset", 1)

    assert writes == [WriteEvent("holding", 0, [1], 0x06)]


async def test_reset_errors(gateway: ComfoConnectPro, writes: list[WriteEvent]) -> None:
    await gateway.controls.async_reset_errors()

    assert writes == [WriteEvent("coil", 0, [True], 0x05)]


@pytest.mark.parametrize(
    ("helper", "value"),
    [
        *(
            ("async_write_boost_time", seconds)
            for seconds in (-1, 65535, 86399, 86401, 3600.5, "600", True)
        ),
        *(
            ("async_write_external_setpoint", celsius)
            for celsius in (-0.01, 40.01, float("nan"), 7000.0, True, "20")
        ),
        *(
            ("async_write_ventilation_preset", value)
            for value in (4, -1, "high", True, 1.0, TemperatureProfile.COLD)
        ),
        *(
            ("async_write_temperature_profile", value)
            for value in (3, "warm", True, TemperatureProfileMode.EXTERNAL_SETPOINT)
        ),
        *(
            ("async_write_temperature_profile_mode", value)
            for value in (3, "fixed", False, VentilationPreset.LOW)
        ),
        *(
            (helper, value)
            for helper in (
                "async_write_auto_mode",
                "async_write_boost",
                "async_write_away_function",
                "async_write_comfocool",
            )
            for value in ("off", 2, 1, None)
        ),
    ],
)
async def test_write_rejects_an_invalid_value(
    gateway: ComfoConnectPro, writes: list[WriteEvent], helper: str, value: object
) -> None:
    with pytest.raises(InvalidValueError):
        await getattr(gateway.controls, helper)(value)

    assert writes == []


async def test_a_refused_write_raises(
    gateway: ComfoConnectPro, mock_modbus_unit: MockModbusUnit
) -> None:
    mock_modbus_unit.fail_write(address(0x0001), IllegalDataValueError())
    with pytest.raises(IllegalDataValueError):
        await gateway.controls.async_write_ventilation_preset(VentilationPreset.LOW)


async def test_a_timed_out_write_raises(
    gateway: ComfoConnectPro, mock_modbus_unit: MockModbusUnit
) -> None:
    mock_modbus_unit.fail_write(
        address(0x0007), ModbusTimeoutError(), register_type="coil"
    )
    with pytest.raises(ModbusTimeoutError):
        await gateway.controls.async_write_boost(True)
