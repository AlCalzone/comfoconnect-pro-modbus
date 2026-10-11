#!/usr/bin/env python3

"""Query a ComfoConnect PRO gateway and print every value."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from modbus_connection import ModbusError
from modbus_connection.cli_helper import (
    CountingUnit,
    add_connection_args,
    connect_from_args,
    print_component,
)

from comfoconnect_pro_modbus import ComfoConnectPro, NoVentilationUnitError

# The gateway speaks Modbus TCP over its network link and Modbus RTU over RS-485.
CONNECTIONS = (("tcp", None), ("serial", "rtu"))

EXAMPLES = """examples:
  uv run script/query.py 192.168.1.50
  uv run script/query.py 192.168.1.50 --unit 2 --raw
  uv run script/query.py /dev/ttyUSB0 --baudrate 19200 --parity E
"""


def print_gateway(gateway: ComfoConnectPro) -> None:
    """Print each component under its attribute name."""
    print_component(gateway.status, title="status")
    print()
    print_component(gateway.sensors, title="sensors")
    print()
    print_component(gateway.controls, title="controls")


async def main() -> int:
    """Read one gateway and print it."""
    # The backend logs a failed connect at ERROR with its traceback; the
    # messages below say it in one line.
    logging.getLogger().addHandler(logging.NullHandler())

    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_connection_args(parser, connections=CONNECTIONS)
    parser.add_argument("--unit", type=int, default=1, help="Modbus unit id")
    parser.add_argument(
        "--raw", action="store_true", help="also dump every register read, as JSON"
    )
    args = parser.parse_args()

    try:
        connection = await connect_from_args(args)
    except ModbusError as err:
        # A connect timeout arrives with no message of its own.
        detail = str(err) or type(err).__name__
        print(f"Could not connect to {args.target}: {detail}")
        return 1

    counting = CountingUnit(connection.for_unit(args.unit))
    try:
        gateway = await ComfoConnectPro.async_detect(counting)
        report = await gateway.async_update()
        # A raw dump re-reads everything, so count the poll alone.
        poll_reads = counting.reads
        raw = await gateway.async_read_raw() if args.raw else None
    except NoVentilationUnitError as err:
        print(f"No ventilation unit behind the gateway: {err}")
        return 1
    except ModbusError as err:
        print(f"Could not read the gateway: {str(err) or type(err).__name__}")
        return 1
    finally:
        await connection.close()

    print_gateway(gateway)
    if report.failed:
        print("\nFailed to read:")
        for name, error in report.failed.items():
            print(f"  {name}: {str(error) or type(error).__name__}")
    if raw is not None:
        print("\nRaw registers")
        # The dump arrives address-ordered; sorting keys would undo that.
        print(json.dumps(raw, indent=2))
    print(f"\n{poll_reads} Modbus reads")
    return 0


raise SystemExit(asyncio.run(main()))
