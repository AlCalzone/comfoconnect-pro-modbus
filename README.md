# comfoconnect-pro-modbus

Read and control Zehnder ComfoAir Q and Flex ventilation units through the ComfoConnect PRO gateway over Modbus TCP or Modbus RTU.

## Installation

```bash
pip install comfoconnect-pro-modbus
```

It needs Python 3.12 or later and [modbus-connection](https://github.com/home-assistant-libs/modbus-connection) 4.12.1 or later.

## Device setup

- **Protocol:** select Modbus TCP or Modbus RTU on the gateway's Protocols and services page. The default is none.
- **Connection:** Modbus TCP uses port 502. For Modbus RTU, the baud rate and parity must match the gateway. The default parity is even with 1 stop bit. With no parity, the gateway uses 2 stop bits.
- **Unit ID:** 1 by default, settable from 1 to 247 on the gateway.
- **Firmware:** the ventilation unit's firmware must be compatible with the gateway. Otherwise `async_detect()` raises `NoVentilationUnitError` with `INCOMPATIBLE_VERSION`.
- **Supported devices:** the ComfoConnect PRO (product number 30006323) with a ComfoAir Q or Flex on ComfoNet. With any other unit, or none, `async_detect()` raises `NoVentilationUnitError`.
- **Network:** for Modbus RTU, wire the gateway's terminals A and B to the RS-485 adapter.

## Usage

The library builds on modbus-connection. You open the connection and pass the library a `ModbusUnit`. The library never opens or closes the connection itself.

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

Every value is `None` until the first update. Each update returns an `UpdateReport`. `report.updated` names the components that refreshed. `report.failed` maps the others to their error, and those keep their previous values. A lost connection raises `ModbusConnectionError`.

## Gotchas

- **No identity:** the gateway reports no serial number, model or firmware version.
- **No off switch:** the unit cannot be turned off or put into standby over Modbus.
- **Temperature profile:** `temperature_profile` applies only in the adaptive and fixed modes. `external_setpoint` applies only in the external setpoint mode.
- **Boost time:** takes 0 to 65534 seconds, or exactly 86400 for 24 hours. Other values raise `ValueError`.
- **CO₂ zones:** a zone that reads 0 counts as having no sensor.
- **Testing:** built against the gateway's installation manual, document revision 140. It has not been tested on real hardware yet.

## API

### `ComfoConnectPro(unit, *, timeout=None)`

The gateway and its ventilation unit, reached through a modbus-connection `ModbusUnit`.

- `await async_detect(unit, *, timeout=None)`: build the device after checking that the gateway reaches a ventilation unit.
- `await async_update()`: read `status`, `sensors` and `controls`. Returns an `UpdateReport`.
- `await async_read_raw()`: every register and bit the device reads, undecoded.
- `status`, `sensors`, `controls`: the components below.

### `status` (`Status`)

- `connection_state`: a `ConnectionState`. `OK` when the gateway reaches a supported unit.
- `is_connected`: whether `connection_state` is `OK`.
- `active_alarms`: the active alarms, as `AlarmCode` members, or plain numbers for codes the manual does not list.
- `active_error(slot)`: the alarm in slot 1 to 5, or 0 for an empty slot.
- `error_flag`: at least one alarm is active.
- `filter_dirty`: the filters must be replaced.
- `standby`: the unit is in standby.
- `comfohood`: the ComfoHood cooker hood is on.

### `sensors` (`Sensors`)

- `airflow`: the airflow, in m³/h.
- `room_temperature`, `extract_temperature`, `exhaust_temperature`, `outdoor_temperature`, `supply_temperature`: the air temperatures, in °C.
- `room_humidity`, `extract_humidity`, `exhaust_humidity`, `outdoor_humidity`, `supply_humidity`: the air humidities, in %.
- `co2(zone)`: the CO₂ level in zone 1 to 8, in ppm.
- `co2_zones`: the zones reporting a level, as `{zone: ppm}`.
- `filter_days_remaining`: the time until the filters are due, in days.

### `controls` (`Controls`)

- `ventilation_preset`: the fan speed, a `VentilationPreset`.
- `auto_mode`: the unit picks the speed itself.
- `boost`: the boost is running.
- `boost_time`: how long a boost lasts, in seconds.
- `away`: the away function is on.
- `comfocool`: ComfoCool may cool.
- `temperature_profile`: a `TemperatureProfile`.
- `temperature_profile_mode`: a `TemperatureProfileMode`.
- `external_setpoint`: the comfort temperature for the external setpoint mode, in °C.
- `await async_write_ventilation_preset(preset)`: set the fan speed.
- `await async_write_boost_time(seconds)`: set how long a boost lasts.
- `await async_reset_errors()`: clear the alarms.
- `await write(name, value)`: set `auto_mode`, `boost`, `away`, `comfocool`, `temperature_profile`, `temperature_profile_mode` or `external_setpoint`.

### Enums

- `VentilationPreset`: `AWAY`, `LOW`, `MEDIUM`, `HIGH`.
- `TemperatureProfile`: `NORMAL`, `COLD`, `WARM`.
- `TemperatureProfileMode`: `ADAPTIVE`, `FIXED`, `EXTERNAL_SETPOINT`.
- `ConnectionState`: `OK`, `NOT_COMFOAIR_Q`, `INCOMPATIBLE_VERSION`, `NO_VENTILATION_UNIT`.
- `AlarmCode`: the 64 ComfoAir Q alarm codes. [`enums.py`](src/comfoconnect_pro_modbus/enums.py) describes each one.

### Errors

- `NoVentilationUnitError`: raised by `async_detect()` when the gateway reports a connection state other than `OK`. Its `state` holds the `ConnectionState`.
- `ValueError`: raised by `async_write_boost_time()` for a duration the gateway cannot store.

The register addresses are in the component modules under [`src/comfoconnect_pro_modbus`](src/comfoconnect_pro_modbus), and in chapter 9.3 of the gateway's installation manual.

## Troubleshooting

`script/query.py` reads the device once and prints every value:

```bash
uv run script/query.py 192.168.1.50
uv run script/query.py /dev/ttyUSB0 --baudrate 19200 --parity E
```

Add `--raw` to include the undecoded registers. A bug report about a wrong value needs them.

The `comfoconnect_pro_modbus` logger reports at `DEBUG` the connection state `async_detect()` found and each component that failed to refresh during an update.
