#!/usr/bin/env python3
# ##### BEGIN GPL LICENSE BLOCK #####
#
# Copyright (C) 2021  Patrick Baus
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####
"""A simple example to demonstrate operating a single SCPI device via the linux-gpib wrapper."""

import asyncio
import logging

# Devices
from async_gpib import AsyncGpib

# The primary address (e.g. 22) can be anything. There is no device connection required for this example
gpib_device = AsyncGpib(name=0, pad=21)


async def main():
    """This example will print ID of the attached SCPI device"""
    async with gpib_device:
        print("Controller version:", await gpib_device.version())
        await gpib_device.write(b"*IDN?")
        print("Device id:", await gpib_device.read())


logging.basicConfig(level=logging.DEBUG)  # Set to logging.INFO for less verbose output
asyncio.run(main())
