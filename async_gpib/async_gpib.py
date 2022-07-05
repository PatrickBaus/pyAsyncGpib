"""
This is a Python AsyncIO wrapper for Linux GPIB and the gpib_ctypes package.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging

# Import either the Linux GPIB module or gpib_ctypes. Prefer Linux GPIB.
from enum import Flag, unique
from types import TracebackType
from typing import Any, Callable, Type

try:
    from typing import Self  # type: ignore # Python 3.11
except ImportError:
    from typing_extensions import Self

try:
    import Gpib
    import gpib
except ModuleNotFoundError:
    from gpib_ctypes import Gpib, gpib

TIMEOUT_VALUES = {
    gpib.T10us: 10e-6,
    gpib.T30us: 30e-6,
    gpib.T100us: 100e-6,
    gpib.T300us: 300e-6,
    gpib.T1ms: 1e-3,
    gpib.T3ms: 3e-3,
    gpib.T10ms: 10e-3,
    gpib.T30ms: 30e-3,
    gpib.T100ms: 100e-3,
    gpib.T300ms: 300e-3,
    gpib.T1s: 1.0,
    gpib.T3s: 3.0,
    gpib.T10s: 10.0,
    gpib.T30s: 30.0,
    gpib.T100s: 100.0,
    gpib.T300s: 300.0,
    gpib.T1000s: 1000.0,
}


@unique
class EosType(Flag):
    """
    The bitmask used, for setting the end-of-string mode.
    """

    NONE = 0
    REOS = 1 << 10  # Enable termination of reads, when the EOS character is received
    XEOS = 1 << 11  # Assert the EOI line, whenever the EOS character is sent during write
    BIN = 1 << 12  # Match the EOS character against all 8 bits and not just the 7 least significant bits


def _calculate_timeout_value(timeout: float | None):
    if timeout is None:
        return gpib.TNONE
    for key, value in TIMEOUT_VALUES.items():
        if value >= timeout:
            return key
    return gpib.T1000s


class AsyncGpib:  # pylint: disable=too-many-public-methods, too-many-instance-attributes  # This is just a wrapper
    """
    A thin wrapper class, that uses a threadpool to execute the blocking gpib library calls.
    """

    @property
    def id(self) -> int | str:  # pylint: disable=invalid-name
        """
        The device handle.
        Returns
        -------
        int or str
            The device name as given to ibfind().
        """
        return self.__name

    @property
    def pad(self) -> int | None:
        """
        Returns
        -------
        int
            The device primary address
        """
        return self.__pad

    @property
    def sad(self) -> int:
        """
        Returns
        -------
        int
            The device secondary address
        """
        return self.__sad

    def __str__(self) -> str:
        return f"Linux-GPIB at Gpib({self.__name})"

    def __init__(  # pylint: disable=too-many-arguments
        self,
        name: int | str = "gpib0",
        pad: int | None = None,
        sad: int = 0,
        timeout: float | None = 10.0,
        send_eoi: bool = True,
        eos_mode: EosType = EosType.NONE,
        eos_character: bytes | None = None,
    ) -> None:
        """
        Parameters
        ----------
        name: str or int, default="gpib0"
            Either the board name from the config file (e.g. "gpib0"), the board index (e.g. 0) or a
            device object (name=0, pad=....)
        pad: int, default=None
            primary address, must only be specified when creating a device object
        sad: int, default=0
            secondary address, must only be specified when creating a device object
        timeout: float or None, default=10.0
            timeout in seconds
        send_eoi: bool, default=1
            assert EOI on write if non-zero, default True
        eos_mode: int, optional
            end-of-string termination character
        """
        eos_character = eos_character if eos_character is not None else b"\0"
        self.__name = name
        self.__pad = pad
        self.__sad = sad
        self.__timeout = _calculate_timeout_value(timeout)
        self.__send_eoi = bool(send_eoi)
        self.__eos_mode = ord(eos_character) | eos_mode.value
        self.__device: Gpib.Gpib | None = None
        self.__threadpool: concurrent.futures.ThreadPoolExecutor | None = None

        self.__logger = logging.getLogger(__name__)
        self.__logger.setLevel(logging.WARNING)  # Only log really important messages

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self, exc_type: Type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """
        Calling connect() does nothing, but is here for compatibility with other transports that
        require a connection.
        """
        self.__device = Gpib.Gpib(self.__name, self.__pad, self.__sad, self.__timeout, self.__send_eoi, self.__eos_mode)
        self.__threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    async def disconnect(self) -> None:
        """
        This is an alias for close().
        """
        await self.close()

    async def __wrapper(self, func: Callable, *args: Any) -> Any:
        """
        This is the actual wrapper, that runs the threaded Linux GPIB lib in the executor and
        returns a future to wait for.
        """
        assert self.__device is not None

        try:
            return await asyncio.get_running_loop().run_in_executor(self.__threadpool, func, *args)
        except gpib.GpibError as error:
            status = self.__device.ibsta()
            if status & Gpib.TIMO:
                raise asyncio.TimeoutError() from None

            raise error from None

    async def close(self) -> None:
        """
        Close the board or device handle by calling ibonl.
        """
        assert self.__device is not None
        assert self.__threadpool is not None

        await self.__wrapper(self.__device.close)
        try:
            self.__threadpool.shutdown(wait=True, cancel_futures=True)
        except TypeError:
            # Python < 3.9.0
            self.__threadpool.shutdown(wait=True)
        finally:
            self.__device = None
            self.__threadpool = None

        self.__logger.info("GPIB connection shut down.")

    async def command(self, cmd: bytes) -> None:
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
        assert self.__device is not None

        await self.__wrapper(self.__device.command, cmd)

    async def config(self, option: int, value: int) -> int:
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
        assert self.__device is not None

        return await self.__wrapper(self.__device.config, option, value)

    async def interface_clear(self) -> None:
        """
        Clear interface by calling ibsic.

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        assert self.__device is not None

        await self.__wrapper(self.__device.interface_clear)

    async def write(self, command: bytes) -> None:
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
        assert self.__device is not None

        self.__logger.debug("Writing data: %s", command)
        await self.__wrapper(self.__device.write, command)

    async def read(self, length: int = 512) -> bytes:
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
        assert self.__device is not None

        result = await self.__wrapper(self.__device.read, length)
        self.__logger.debug("Data read: %s", result)
        return result

    async def listener(self, pad: int, sad: int = 0) -> bool:
        """
        Check if a listener is present at address by calling ibln.

        Parameters
        ----------
        pad: int
            primary address
        sad: int, optional
            secondary address, default 0

        Returns
        -------
        bool
            True if listener is present, False otherwise

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        assert self.__device is not None

        return await self.__wrapper(self.__device.listener, pad, sad)

    async def lines(self) -> int:
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
        assert self.__device is not None

        return await self.__wrapper(self.__device.lines)

    async def ask(self, option: int) -> int:
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
        assert self.__device is not None

        return await self.__wrapper(self.__device.ask, option)

    async def clear(self) -> None:
        """
        Clear device by calling ibclr.
        """
        assert self.__device is not None

        await self.__wrapper(self.__device.clear)

    async def wait(self, eventmask: int) -> None:
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
        assert self.__device is not None

        await self.__wrapper(self.__device.wait, eventmask)
        # Check for timeout
        ibsta = await self.__wrapper(self.__device.ibsta)
        if ibsta & Gpib.TIMO:
            raise asyncio.TimeoutError("Timeout waiting for event.")

    async def serial_poll(self) -> int:
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
        assert self.__device is not None

        return await self.__wrapper(self.__device.serial_poll)

    async def trigger(self) -> None:
        """
        Trigger device by calling ibtrg.

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        assert self.__device is not None

        await self.__wrapper(self.__device.trigger)

    async def remote_enable(self, enable: bool) -> None:
        """
        Set remote enable by calling ibsre.

        Parameters
        ----------
        enable: bool
            if non-zero, set remote enable

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        assert self.__device is not None

        await self.__wrapper(self.__device.remote_enable, bool(enable))

    async def ibloc(self) -> int:
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
        assert self.__device is not None

        return await self.__wrapper(self.__device.ibloc)

    async def ibsta(self) -> int:
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
        assert self.__device is not None

        return await self.__wrapper(self.__device.ibsta)

    async def ibcnt(self) -> int:
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
        assert self.__device is not None

        return await self.__wrapper(self.__device.ibcnt)

    async def timeout(self, value: float | None) -> int:
        """
        Set IO timeout by calling ibtmo.

        Parameters
        ----------
        value: float or None
            timeout in seconds, it will be converted to one of the constants
            {TNONE, T10us, T30us, T100us, T300us, T1ms, T3ms, T10ms, T30ms, T100ms, T300ms, T1s, T3s, T10s,
             T30s, T100s, T300s, T1000s}

        Returns
        -------
        int
            ibsta value

        Raises
        ----------
        gpib.GpibError
        asyncio.TimeoutError
        """
        assert self.__device is not None

        return await self.__wrapper(self.__device.timeout, _calculate_timeout_value(value))

    @staticmethod
    async def version() -> str:
        """
        Get the GPIB library version. Not implemented on Windows.

        Returns
        -------
        str
             GPIB library version
        """
        return gpib.version().decode("utf-8")
