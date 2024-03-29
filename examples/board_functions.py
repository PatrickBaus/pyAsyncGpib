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
"""An example demonstrating the GPIB board (controller) settings."""

import asyncio
import logging

# Devices
from async_gpib import AsyncGpib

# The primary address (e.g. 22) can be anything. There is no device connection required for this example
gpib_device = AsyncGpib(name=0, pad=22)
gpib_board = AsyncGpib(name=0)  # The controller board, *not* a device


async def main():
    """Send a local lockout to all devices, wait for 5 seconds, then reactive them."""
    try:
        # Enable local lockout
        await gpib_board.remote_enable(True)  # The remote_enable() call only works with GPIB boards
        await asyncio.sleep(5.0)
        await gpib_board.remote_enable(False)
        # or alternatively
        # await gpib_device.ibloc()
    finally:
        # Disconnect from the GPIB controller. We may safely call disconnect() on a non-connected gpib device, even
        # in case of a connection error
        await gpib_device.disconnect()


logging.basicConfig(level=logging.DEBUG)  # Set to logging.INFO for less verbose output
asyncio.run(main())
