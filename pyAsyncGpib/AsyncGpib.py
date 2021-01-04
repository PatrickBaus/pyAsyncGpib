# -*- coding: utf-8 -*-
# ##### BEGIN GPL LICENSE BLOCK #####
#
# Copyright (C) 2020  Patrick Baus
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

# AsyncGpib
import Gpib
import gpib
import janus

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
        self.__board = Gpib.Gpib(name)

        self.__device_task = None
        self.__logger = logging.getLogger(__name__)

    async def connect(self):
        # Only connect if we are disconnected
        if self.__device_task is None:
            # create two queues to talk to asyncio from our thread
            self.__job_queue = janus.Queue()
            self.__result_queue = janus.Queue()

            loop = asyncio.get_running_loop()
            self.__device_task = loop.run_in_executor(None, self.__main)
            #await self.interface_clear()

    async def disconnect(self):
        if self.__device_task is not None:
            try:
                await self.__job_queue.async_q.put(None)
                await self.__job_queue.async_q.join()
                await self.__device_task
            finally:
                self.__device_task = None

    def __main(self):
        """
        This is the thread, that serves the queues and manages the GPIB adapter.
        """
        while 'thread is not canceled':
            try:
                job = self.__job_queue.sync_q.get()
                if job is None:
                    # If we have a 'None' job in the queue, we are done
                    break
                job.process(self.__result_queue.sync_q)
            except gpib.GpibError as error:
                status = self.__device.ibsta()
                if not (status & Gpib.TIMO):
                    # Do not log timeouts, a timeout is normal on the GPIB bus, if commands are invalid
                    self.__logger.error(error)
                self.__result_queue.sync_q.put((error, status))
            finally:
                self.__job_queue.sync_q.task_done()

        self.__logger.info("Shutting down GPIB")

    async def __query_job(self, task, *args, **kwargs):
        await self.__job_queue.async_q.put(Job(task, *args, **kwargs))
        result = await self.__result_queue.async_q.get()
        # This is not very pythonic, but it gets the job done
        # Test if we have an error. This will be a tuple (error, ibsta).
        if isinstance(result, tuple) and isinstance(result[0], gpib.GpibError):
            error, ibsta = result
            if ibsta & Gpib.TIMO:
                # The status (ibsta) returned a timeout
                raise asyncio.TimeoutError() from None
            else:
                raise error from None
        self.__result_queue.async_q.task_done()
        return result

    async def close(self):
        """
        This is an alias for disconnect().
        """
        await self.disconnect()

    async def command(self, str):
        await self.__query_job(self.__device.command, str)

    async def config(self, option, value):
        return await self.__query_job(self.__device.config, option, value)

    async def interface_clear(self):
       await self.__query_job(self.__device.interface_clear)

    async def write(self, command):
        self.__logger.debug('Writing data: %(payload)s', {'payload': command})
        await self.__query_job(self.__device.write, command)

    async def read(self, len=512):
        result = await self.__query_job(self.__device.read, len)
        self.__logger.debug("Data read: %(data)s", {'data': result})
        return result

    async def listener(self, pad, sad=0):
        return await self.__query_job(self.__device.listener, pad, sad)

    async def lines(self):
        return await self.__query_job(self.__device.lines)

    async def ask(self, option):
        return await self.__query_job(self.__device.ask, option)

    async def clear(self):
        await self.__query_job(self.__device.clear)

    async def wait(self, mask):
        if
        await self.__query_job(self.__device.wait, mask)

    async def serial_poll(self):
        return await self.__query_job(self.__device.serial_poll)

    async def trigger(self):
        await self.__query_job(self.__device.trigger)

    async def remote_enable(self, val):
        return await self.__query_job(self.__device.remote_enable, val)

    async def ibloc(self):
        await self.__query_job(self.__device.ibloc)

    async def ibsta(self):
        return await self.__query_job(self.__device.ibsta)

    async def ibcnt(self):
        return await self.__query_job(self.__device.ibcnt)

    async def timeout(self, value):
        return await self.__query_job(self.__device.timeout)

    async def set_auto_polling(self, enabled):
        return await self.__query_job(self.__board.config, gpib.IbcAUTOPOLL, enabled)
