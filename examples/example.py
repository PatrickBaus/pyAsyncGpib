#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

import asyncio
import logging
import sys

# Devices
from async_gpib.async_gpib import AsyncGpib

# The primary address (e.g. 22) can be anything. There is no device connection required for this example
gpib_device = AsyncGpib(name=0, pad=22)

async def main():
    try:
        print("Controller version:", await gpib_device.version())
    finally:
        # Disconnect from the GPIB controller. We may safely call diconnect() on a non-connected gpib device, even
        # in case of a connection error
        await gpib_device.disconnect()

logging.basicConfig(level=logging.DEBUG)    # Set to logging.INFO for less verbose output
asyncio.run(main())
