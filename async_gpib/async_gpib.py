# -*- coding: utf-8 -*-
"""
This is an Python AsyncIO wrapper for Linux GPIB and the gpib_ctypes package.
"""

import asyncio
import concurrent.futures
import logging

# Import either the Linux GPIB module or gpib_ctypes. Prefer Linux GPIB.
try:
    import Gpib
    import gpib
except ModuleNotFoundError:
    from gpib_ctypes import Gpib
    from gpib_ctypes import gpib

class AsyncGpib:    # pylint: disable=too-many-public-methods
    """
    A thin wrapper class, that uses a threadpool to execute the blocking gpib libarary calls.
    """
    @property
    def id(self):   # pylint: disable=invalid-name
        """
        The device handle.
        Returns
        -------
        int
            device handle retrieved from calling ibfind.
        """
        return self.__device.id

    def __repr__(self):
        return repr(self.__device)

    def __init__(self, name="gpib0", pad=None, sad=gpib.NO_SAD, timeout=gpib.T10s, send_eoi=1, eos_mode=0):  # pylint: disable=too-many-arguments
        """
        Parameters
        ----------
        name: str or int, default="gpib0"
            Either the board name from the config file (e.g. "gpib0"), the board index (e.g. 0) or a
            device object (name=0, pad=....)
        pad: int, default=None
            primary address, must only be specified when creating a device obeject
        sad: int, default=gpib.NO_SAD
            secondary address, must only be specified when creating a device obeject
        timeout: {TNONE, T10us, T30us, T100us, T300us, T1ms, T3ms, T10ms, T30ms, T100ms, T300ms, T1s, T3s, T10s, T30s, T100s, T300s, T1000s}, default=gpib.T10s
            timeout
        send_eoi: int, default=1
            assert EOI on write if non-zero, default 1
        eos_mode: int, default=0
            end-of-string termination, default 0
        """
        self.__device = Gpib.Gpib(name, pad, sad, timeout, send_eoi, eos_mode)
        self.__threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=1)    # pylint: disable=consider-using-with

        self.__logger = logging.getLogger(__name__)

    async def connect(self):
        """
        Calling connect() does nothing, but is here for compatibility with other transports that
        require a connection.
        """

    async def disconnect(self):
        """
        This is an alias for close().
        """
        await self.close()

    async def __wrapper(self, func, *args, **kwargs):
        """
        This is the actual wrapper, that runs the threaded Linux GPIB lib in the executor and
        returns a future to wait for.
        """
        try:
            return await asyncio.get_running_loop().run_in_executor(self.__threadpool, func, *args, **kwargs)
        except gpib.GpibError as error:
            status = self.__device.ibsta()
            if status & Gpib.TIMO:
                raise asyncio.TimeoutError() from None

            # Do not log timeouts, a timeout is normal on the GPIB bus, if commands are invalid
            self.__logger.error(error)
            raise error from None


    async def close(self):
        """
        Close the board or device handle by calling ibonl.
        """
        await self.__wrapper(self.__device.close)
        try:
            self.__threadpool.shutdown(wait=True, cancel_futures=True)
        except TypeError:
            # Python < 3.9.0
            self.__threadpool.shutdown(wait=True)

        self.__logger.info("GPIB connection shut down.")

    async def command(self, cmd):
        """
        Write command bytes by calling ibcmd.

        Parameters
        ----------
        cmd: bytes
            sequence of bytes to write

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        await self.__wrapper(self.__device.command, cmd)

    async def config(self, option, value):
        """
        Change configuration by calling ibconfig.

        Parameters
        ----------
        option: int
            gpib.Ibc* constant designating configuration settings
        value: int
            configuration setting value

        Returns
        -------
        int
            ibsta value

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        return await self.__wrapper(self.__device.config, option, value)

    async def interface_clear(self):
        """
        Clear interface by calling ibsic.

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        await self.__wrapper(self.__device.interface_clear)

    async def write(self, command):
        """
        Write data bytes by calling ibwrt.

        Parameters
        ----------
        command: bytes
            sequence of bytes to write

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        self.__logger.debug("Writing data: %s", command)
        await self.__wrapper(self.__device.write, command)

    async def read(self, length=512):
        """
        Read a number of data bytes by calling ibread.

        Parameters
        ----------
        length: int, default=512
            number of bytes to read

        Returns
        -------
        bytes
            sequence of bytes which was read

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        result = await self.__wrapper(self.__device.read, length)
        self.__logger.debufg("Data read: %s", result)
        return result

    async def listener(self, pad, sad=gpib.NO_SAD):
        """
        Check if a listener is present at address by calling ibln.

        Parameters
        ----------
        pad: int
            primary address
        sad: int, optional
            secondary address, default gpib.NO_SAD

        Returns
        -------
        bool
            True if listener is present, False otherwise

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        return await self.__wrapper(self.__device.listener, pad, sad)

    async def lines(self):
        """
        Obtain the status of the control and handshaking bus lines of the bus.

        Returns
        -------
        int
            line capability and status bits

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        return await self.__wrapper(self.__device.lines)

    async def ask(self, option):
        """
        Query configuration by calling ibask.

        Parameters
        ----------
        option: int
            gpib.Iba* constant designating configuration settings

        Returns
        -------
        int
            configuration setting value

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        return await self.__wrapper(self.__device.ask, option)

    async def clear(self):
        """
        Clear device by calling ibclr.
        """
        await self.__wrapper(self.__device.clear)

    async def wait(self, eventmask):
        """
        Wait for event by calling ibwait.

        Parameters
        ----------
        eventmask: int
            ibsta bits designating events to wait for

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        await self.__wrapper(self.__device.wait, eventmask)
        # Check for timeout
        ibsta = await self.__wrapper(self.__device.ibsta)
        if ibsta & Gpib.TIMO:
            raise asyncio.TimeoutError("Timeout waiting for event.")

    async def serial_poll(self):
        """
        Read status byte by calling ibrsp.

        Returns
        -------
        int
            serial poll status byte

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        return await self.__wrapper(self.__device.serial_poll)

    async def trigger(self):
        """
        Trigger device by calling ibtrg.

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        await self.__wrapper(self.__device.trigger)

    async def remote_enable(self, enable):
        """
        Query configuration by calling ibask.

        Parameters
        ----------
        enable: bool or int
            if non-zero, set remote enable

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        await self.__wrapper(self.__device.remote_enable, enable)

    async def ibloc(self):
        """
        Push device to local mode by calling ibloc.

        Returns
        -------
        int
            ibsta value

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        return await self.__wrapper(self.__device.ibloc)

    async def ibsta(self):
        """
        Get status value by calling ThreadIbsta or reading ibsta.

        Returns
        -------
        int
            ibsta value

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        return await self.__wrapper(self.__device.ibsta)

    async def ibcnt(self):
        """
        Get number of transferred bytes by calling ThreadIbcntl or reading ibcnt.

        Returns
        -------
        int
            number of transferred bytes

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        return await self.__wrapper(self.__device.ibcnt)

    async def timeout(self, value):
        """
        Set IO timeout by calling ibtmo.

        Parameters
        ----------
        value: {TNONE, T10us, T30us, T100us, T300us, T1ms, T3ms, T10ms, T30ms, T100ms, T300ms, T1s, T3s, T10s, T30s, T100s, T300s, T1000s}
            timeout, one of constants from gpib.TNONE to gpib.T100s

        Returns
        -------
        int
            ibsta value

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        return await self.__wrapper(self.__device.timeout, value)

    async def version(self):
        """
        Get the GPIB library version. Not implemented on Windows.

        Returns
        -------
        str
             GPIB library version
        """
        return gpib.version().decode("utf-8")
