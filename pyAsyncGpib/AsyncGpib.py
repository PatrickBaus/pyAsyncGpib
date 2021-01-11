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
import concurrent.futures
import logging

# AsyncGpib
import Gpib
import gpib

class Job:
    def __init__(self, task, *args, **kwargs):
        self.__task = task
        self.__args = args
        self.__kwargs = kwargs

    def process(self, result_queue_sync):
        result = self.__task(*self.__args, **self.__kwargs)
        result_queue_sync.put(result)

class AsyncGpib:
    @property
    def id(self):
        return self.__device.id

    def __repr__(self):
        return repr(self.__device)

    """
    name: Either e.g. "gpib0" (string) or 0 (integer)
    pad: primary address
    """
    def __init__(self, name = 'gpib0', pad = None, sad = 0, timeout = 13, send_eoi = 1, eos_mode = 0):
        self.__device = Gpib.Gpib(name, pad, sad, timeout, send_eoi, eos_mode)
        self.__threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        self.__logger = logging.getLogger(__name__)

    async def connect(self):
        pass

    async def disconnect(self):
        """
        This is an alias for close().
        """
        await self.close()

    async def __wrapper(self, func, *args, **kwargs):
        try:
            return await asyncio.get_running_loop().run_in_executor(self.__threadpool, func, *args, **kwargs)
        except gpib.GpibError as error:
            status = self.__device.ibsta()
            if status & Gpib.TIMO:
                raise asyncio.TimeoutError() from None
            else:
                # Do not log timeouts, a timeout is normal on the GPIB bus, if commands are invalid
                self.__logger.error(error)
                raise error from None


    async def close(self):
        await self.__wrapper(self.__device.close)
        try:
            self.__threadpool.shutdown(wait=True, cancel_futures=True)
        except TypeError:
            # Python < 3.9.0
            self.__threadpool.shutdown(wait=True)

        self.__logger.info("GPIB connection shut down.")

    async def command(self, str):
        await self.__wrapper(self.__device.command, str)

    async def config(self, option, value):
        return await self.__wrapper(self.__device.config, option, value)

    async def interface_clear(self):
       await self.__wrapper(self.__device.interface_clear)

    async def write(self, command):
        self.__logger.debug('Writing data: %(payload)s', {'payload': command})
        await self.__wrapper(self.__device.write, command)

    async def read(self, len=512):
        result = await self.__wrapper(self.__device.read, len)
        self.__logger.debug("Data read: %(data)s", {'data': result})
        return result

    async def listener(self, pad, sad=0):
        return await self.__wrapper(self.__device.listener, pad, sad)

    async def lines(self):
        return await self.__wrapper(self.__device.lines)

    async def ask(self, option):
        return await self.__wrapper(self.__device.ask, option)

    async def clear(self):
        await self.__wrapper(self.__device.clear)

    async def wait(self, mask):
        await self.__wrapper(self.__device.wait, mask)
        # Check for timeout
        ibsta = await self.__wrapper(self.__device.ibsta)
        if ibsta & Gpib.TIMO:
            raise asyncio.TimeoutError("Timeout waiting for event.")

    async def serial_poll(self):
        return await self.__wrapper(self.__device.serial_poll)

    async def trigger(self):
        await self.__wrapper(self.__device.trigger)

    async def remote_enable(self, val):
        return await self.__wrapper(self.__device.remote_enable, val)

    async def ibloc(self):
        return await self.__wrapper(self.__device.ibloc)

    async def ibsta(self):
        return await self.__wrapper(self.__device.ibsta)

    async def ibcnt(self):
        return await self.__wrapper(self.__device.ibcnt)

    async def timeout(self, value):
        return await self.__wrapper(self.__device.timeout)

    async def version(self):
        return gpib.version().decode("utf-8")
