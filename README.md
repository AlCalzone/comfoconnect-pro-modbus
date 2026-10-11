# comfoconnect-pro-modbus

Read and control a Zehnder ComfoAir Q or Flex ventilation unit through the ComfoConnect PRO gateway over Modbus TCP or Modbus RTU.

## Usage

```python
import asyncio

from modbus_connection import ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection

from comfoconnect_pro_modbus import ComfoConnectPro, VentilationPreset


async def main() -> None:
    connection = ModbusConnection(ModbusTcpParams(host="192.168.1.50"))
    try:
        gateway = await ComfoConnectPro.async_detect(connection.for_unit(1))
        await gateway.async_update()

        print("Airflow:", gateway.sensors.airflow, "m³/h")
        print("Outdoor:", gateway.sensors.outdoor_temperature, "°C")
        print("Alarms:", gateway.status.active_alarms)

        await gateway.controls.async_write_ventilation_preset(VentilationPreset.HIGH)
    finally:
        await connection.close()


asyncio.run(main())
```

Over RS-485, pass `ModbusSerialParams` instead:

```python
from modbus_connection import ModbusSerialParams

ModbusSerialParams(device="/dev/ttyUSB0", baudrate=19200, parity="E", stopbits=1)
```

## Installation

The library is not on PyPI yet. Install it from git:

```bash
pip install "comfoconnect-pro-modbus @ git+https://github.com/AlCalzone/comfoconnect-pro-modbus@main"
```

It needs Python 3.12 or later and [modbus-connection](https://github.com/home-assistant-libs/modbus-connection) 4.12.1 or later.

## Requirements and gotchas

- **Protocol:** select Modbus TCP or Modbus RTU on the gateway's Protocols and services page. The default is none.
- **Unit ID:** 1 by default, settable from 1 to 247 on the gateway.
- **TCP port:** 502.
- **Serial settings:** the baud rate and parity must match the gateway. The default parity is even with 1 stop bit. With no parity, the gateway uses 2 stop bits.
- **Ventilation units:** only the ComfoAir Q and Flex. With any other unit, or none, `async_detect()` raises `NoVentilationUnitError`.
- **No identity:** the gateway reports no serial number, model or firmware version.
- **No off switch:** the unit cannot be turned off or put into standby over Modbus.
- **Temperature profile:** `temperature_profile` applies only in the adaptive and fixed modes. `external_setpoint` applies only in the external setpoint mode.
- **Boost time:** takes 0 to 65534 seconds, or exactly 86400 for 24 hours. Other values raise `ValueError`.
- **Partial failures:** a component that fails to read keeps its previous values and is listed in the returned `UpdateReport`. A lost connection raises `ModbusConnectionError`.
- **Tested against:** the gateway's installation manual, document revision 140. Real hardware has not been tested yet.

## API

### `ComfoConnectPro(unit, *, timeout=None)`

The gateway and its ventilation unit, reached through a modbus-connection `ModbusUnit`.

- `await ComfoConnectPro.async_detect(unit, *, timeout=None)`: build the device after checking that the gateway reaches a ventilation unit.
- `await async_update()`: read `status`, `sensors` and `controls`. Returns an `UpdateReport`.
- `await async_read_raw()`: every register and bit the device reads, undecoded, for bug reports.
- `status`, `sensors`, `controls`: the three components below.

### `status`

- `connection_state`: a `ConnectionState`. `OK` when the gateway reaches a supported unit.
- `is_connected`: whether `connection_state` is `OK`.
- `active_alarms`: the active alarms, as `AlarmCode` members, or plain numbers for codes the manual does not list.
- `active_error(slot)`: the alarm in slot 1 to 5, or 0 for an empty slot.
- `error_flag`: at least one alarm is active.
- `filter_dirty`: the filters must be replaced.
- `standby`: the unit is in standby.
- `comfohood`: the ComfoHood cooker hood is on.

### `sensors`

- `airflow`: m³/h.
- `room_temperature`, `extract_temperature`, `exhaust_temperature`, `outdoor_temperature`, `supply_temperature`: °C.
- `room_humidity`, `extract_humidity`, `exhaust_humidity`, `outdoor_humidity`, `supply_humidity`: %.
- `co2(zone)`: ppm in zone 1 to 8.
- `co2_zones`: the zones reporting a level, as `{zone: ppm}`. A zone that reads 0 counts as having no sensor.
- `filter_days_remaining`: days until the filters are due.

### `controls`

- `ventilation_preset`: the fan speed, a `VentilationPreset`.
- `auto_mode`: the unit picks the speed itself.
- `boost`: the boost is running.
- `boost_time`: how long a boost lasts, in seconds.
- `away`: the away function is on.
- `comfocool`: ComfoCool may cool.
- `temperature_profile`: a `TemperatureProfile`.
- `temperature_profile_mode`: a `TemperatureProfileMode`.
- `external_setpoint`: °C.
- `await async_write_ventilation_preset(preset)`: set the fan speed.
- `await async_write_boost_time(seconds)`: set how long a boost lasts.
- `await async_reset_errors()`: clear the alarms.
- `await write(name, value)`: set `auto_mode`, `boost`, `away`, `comfocool`, `temperature_profile`, `temperature_profile_mode` or `external_setpoint`.

### Types

- `VentilationPreset`: `AWAY`, `LOW`, `MEDIUM`, `HIGH`.
- `TemperatureProfile`: `NORMAL`, `COLD`, `WARM`.
- `TemperatureProfileMode`: `ADAPTIVE`, `FIXED`, `EXTERNAL_SETPOINT`.
- `ConnectionState`: `OK`, `NOT_COMFOAIR_Q`, `INCOMPATIBLE_VERSION`, `NO_VENTILATION_UNIT`.
- `AlarmCode`: the ComfoAir Q alarm codes. [`enums.py`](src/comfoconnect_pro_modbus/enums.py) describes each one.
- `UpdateReport`: `updated` holds the names of the components that refreshed. `failed` maps the others to their error.
- `NoVentilationUnitError`: raised by `async_detect()`. Its `state` holds the `ConnectionState`.

The register addresses are in the component classes under [`src/comfoconnect_pro_modbus`](src/comfoconnect_pro_modbus), and in chapter 9.3 of the gateway's installation manual.

## Checking a real device

`script/query.py` reads the gateway once and prints every value:

```bash
uv run script/query.py 192.168.1.50
uv run script/query.py /dev/ttyUSB0 --baudrate 19200 --parity E --raw
```
