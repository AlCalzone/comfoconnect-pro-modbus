# comfoconnect-pro-modbus

Read and control Zehnder ventilation units through the ComfoConnect PRO gateway over Modbus, as typed Python objects instead of register numbers.

The library maps the gateway's "ComfoAir Q/Flex open interface" onto [modbus-connection](https://github.com/home-assistant-libs/modbus-connection)'s device model. You hand it a `ModbusUnit`, call `async_update()`, and read the sub-systems as attributes. It owns no connection and no I/O policy. The caller does.

## Supported devices

The Zehnder ComfoConnect PRO (product number 30006323), connected over ComfoNet to a ComfoAir Q or ComfoAir Flex ventilation unit. The register map follows the gateway's installation manual, document revision 140.

The gateway speaks Modbus TCP on port 502 over Ethernet or Wi-Fi, and Modbus RTU over RS-485. Select the protocol on the gateway's **Protocols and services** page. Both default to unit ID 1.

The ComfoAir Classic family (ComfoAir 160 to 550, SL and Standard models) also connects to the gateway. The manual documents Modbus for the ComfoAir Q and Flex only, and the gateway reports connection state 30 for any other unit.

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
        print("Preset:", gateway.controls.ventilation_preset)
        print("Alarms:", gateway.status.active_alarms)

        await gateway.controls.async_write_ventilation_preset(VentilationPreset.HIGH)
    finally:
        await connection.close()


asyncio.run(main())
```

Over RS-485, pass `ModbusSerialParams` instead. The gateway defaults to even parity with one stop bit. With no parity it needs two:

```python
from modbus_connection import ModbusSerialParams

ModbusSerialParams(device="/dev/ttyUSB0", baudrate=19200, parity="E", stopbits=1)
```

The gateway has no identity registers: no serial number, model or firmware version. `async_detect()` reads input register 0x0001, the connection state, and raises `NoVentilationUnitError` unless it is 0. A caller that has already checked the gateway constructs `ComfoConnectPro(unit)` directly.

### Addresses

The manual numbers every table from 1, so its input register 0x0001 is protocol address 0. Every field in this library is declared with `address()`, which takes the manual's number and returns the protocol address:

```python
from comfoconnect_pro_modbus import address

address(0x0007)  # -> 6, airflow
```

A field and the manual's table can then be read side by side.

### Components

`ComfoConnectPro` has three components. `async_update()` reads all three, five Modbus reads in all:

- `status`: the connection state, the five alarm slots, and the error, standby, ComfoHood and filter flags.
- `sensors`: airflow, five temperatures, five humidities, eight CO₂ zones and the days until the filter change.
- `controls`: the ventilation preset, the temperature profile and its mode, the external setpoint, the boost time, and the auto mode, boost, away and ComfoCool switches.

Each component is read on its own, so one refused block does not take the rest of the poll with it. `async_update()` returns an `UpdateReport`. A failed component keeps its previous values and is listed by attribute name with its error. A dead link (`ModbusConnectionError`) raises, and so does a timeout before any component has answered:

```python
report = await gateway.async_update()
for name, error in report.failed.items():
    print(f"{name} kept its previous values: {error}")
```

### Alarms

Five input registers hold the active alarm codes. `active_alarms` decodes the non-empty ones to `AlarmCode`, or leaves a code the manual does not list as a plain number:

```python
gateway.status.active_alarms  # (AlarmCode.FILTER_WARNING_FLAG,)
gateway.status.active_error(2)  # 0, slot 2 is empty
```

`async_reset_errors()` clears them.

### CO₂ zones

Up to eight zones report a CO₂ level. `co2_zones` holds only the zones that read more than 0:

```python
gateway.sensors.co2_zones  # {1: 640, 3: 812}
gateway.sensors.co2(2)  # 0
```

### Settings

The holding registers and coils `Controls` reads are also writable:

```python
controls = gateway.controls
await controls.async_write_ventilation_preset(VentilationPreset.LOW)
await controls.write("temperature_profile", TemperatureProfile.WARM)
await controls.write(
    "temperature_profile_mode", TemperatureProfileMode.EXTERNAL_SETPOINT
)
await controls.write("external_setpoint", 22.5)  # °C
await controls.write("boost", True)
await controls.async_write_boost_time(1800)  # seconds
```

The temperature profile applies only in the adaptive and fixed modes. The external setpoint applies only in the external setpoint mode.

The boost time register holds seconds, except 65535, which the gateway takes as 24 hours. `boost_time` reads 65535 as 86400, and `async_write_boost_time(86400)` writes 65535. Any other value from 65535 to 86399 seconds is rejected.

Coils 0x0001 to 0x0005 reset the alarms and select a preset. They act on `True` and ignore `False`, so `Controls` never reads them. `async_reset_errors()` writes coil 0x0001. The preset goes through holding register 0x0001, which also reads back the preset in effect.

### Diagnostics

`async_read_raw()` dumps every register and bit the device reads, undecoded, keyed by address space and address. Quote it in an issue about a wrong value. modbus-connection's mock replays it with `load_raw()`, so the dump can become a test.

## Checking a real device

`script/query.py` reads one gateway once and prints every value it serves. It is the quickest way to check that the gateway is reachable and sees the ventilation unit:

```bash
uv run script/query.py 192.168.1.50
uv run script/query.py 192.168.1.50 --unit 2 --raw
uv run script/query.py /dev/ttyUSB0 --baudrate 19200 --parity E
```

`--raw` adds every register it read, undecoded. The script prints the read count too.

## Timing

The manual names no request rate limit, so the library sets no message spacing. A caller who has measured their link passes `timeout=` to the constructor or to `async_detect()`, which asks for it through `ModbusUnit.require_timeout()`.

Modbus TCP is unencrypted. Keep the gateway on a trusted network.

## Known gaps

The manual leaves a few things open. The library takes these readings of it:

- The manual does not say what a CO₂ zone without a sensor reads. The library takes 0 to mean no sensor.
- The alarm slots have no documented "empty" value. The library takes 0 to mean an empty slot, because no alarm code is 0.
- The manual gives no range for the external setpoint. The library writes any value from 0.0 to 6553.5 °C and leaves the check to the gateway.
- Humidity registers are typed `byte`. The library reads them as unsigned 16-bit values.
- The manual does not say whether coils 0x0002 to 0x0005 read back the active preset. The library reads the preset from holding register 0x0001 only.
