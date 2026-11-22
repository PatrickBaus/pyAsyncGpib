"""
This is a Python AsyncIO wrapper for Linux GPIB and the gpib_ctypes package.
"""

import asyncio
import concurrent.futures
import logging
from collections.abc import Callable
from enum import Flag, unique
from types import TracebackType
from typing import Any, Self, override

# Import either the Linux GPIB module or gpib_ctypes. Prefer Linux GPIB.
try:
    import Gpib
    import gpib  # pragma: no cover  # The tests run against gpib_ctypes
except ModuleNotFoundError:
    from gpib_ctypes import Gpib, gpib

#: The ibsta bit, that is set when a read was ended by EOI or the EOS character. Linux GPIB does not export it.
_END = 0x2000
#: The number of bytes requested per ibrd() call, when reading until the end of the message
_READ_CHUNK_SIZE = 512

#: The exception raised by the GPIB library in use (Linux GPIB or gpib_ctypes)
GpibError: type[Exception] = gpib.GpibError

TIMEOUT_VALUES: dict[int, float] = {
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


def _calculate_timeout_value(timeout: float | None) -> int:
    """
    Convert a timeout in seconds to the smallest GPIB timeout constant, that is at least as long.

    Parameters
    ----------
    timeout: float or None
        The timeout in seconds. None disables the timeout.

    Returns
    -------
    int
        One of the gpib.T* constants. Timeouts longer than 1000 s are capped at gpib.T1000s.

    Raises
    ------
    ValueError
        If the timeout is negative.
    """
    if timeout is None:
        return int(gpib.TNONE)
    if timeout < 0:
        raise ValueError(f"Invalid timeout: {timeout}. The timeout must not be negative.")
    for key, value in TIMEOUT_VALUES.items():
        if value >= timeout:
            return key
    return int(gpib.T1000s)


class AsyncGpib:  # pylint: disable=too-many-public-methods, too-many-instance-attributes  # This is just a wrapper
    """
    A thin wrapper class, that uses a thread to execute the blocking gpib library calls.

    All calls are executed in the same worker thread, because the GPIB status variables (ibsta, ibcnt) are
    thread-local.
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
        int or None
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

    @property
    def is_connected(self) -> bool:
        """
        Returns
        -------
        bool
            True if the board or device handle is open.
        """
        return self.__device is not None

    @override
    def __str__(self) -> str:
        return f"Linux-GPIB at Gpib({self.__name})"

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
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
        send_eoi: bool, default=True
            assert EOI on write
        eos_mode: EosType, default=EosType.NONE
            end-of-string mode
        eos_character: bytes or None, default=None
            A single end-of-string character. None is the same as b"\\0".

        Raises
        ------
        ValueError
            If the timeout is negative or eos_character is not a single byte.
        """
        eos_character = eos_character if eos_character is not None else b"\0"
        if len(eos_character) != 1:
            raise ValueError(f"Invalid EOS character: {eos_character!r}. It must be a single byte.")
        self.__name = name
        self.__pad = pad
        self.__sad = sad
        self.__timeout = _calculate_timeout_value(timeout)
        self.__send_eoi = bool(send_eoi)
        self.__eos_mode = ord(eos_character) | eos_mode.value
        self.__device: Any = None  # Gpib.Gpib, which is untyped
        self.__threadpool: concurrent.futures.ThreadPoolExecutor | None = None

        self.__logger = logging.getLogger(__name__)

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """
        Open the board or device handle. Calling connect() on an open connection does nothing.

        Raises
        ------
        GpibError
            If the board or device cannot be opened.
        """
        if self.__device is not None:
            return

        threadpool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="AsyncGpib")
        try:
            self.__device = await asyncio.get_running_loop().run_in_executor(
                threadpool,
                Gpib.Gpib,
                self.__name,
                self.__pad,
                self.__sad,
                self.__timeout,
                self.__send_eoi,
                self.__eos_mode,
            )
        except BaseException:
            threadpool.shutdown(wait=False, cancel_futures=True)
            raise
        self.__threadpool = threadpool

    async def disconnect(self) -> None:
        """
        This is an alias for close().
        """
        await self.close()

    def __get_device(self) -> tuple[Any, concurrent.futures.ThreadPoolExecutor]:
        if self.__device is None or self.__threadpool is None:
            raise ConnectionError("Not connected. Call connect() first.")
        return self.__device, self.__threadpool

    async def __wrapper[T](self, func: Callable[..., T], *args: Any) -> T:
        """
        This is the actual wrapper, that runs the threaded Linux GPIB lib in the executor and
        returns a future to wait for.
        """
        device, threadpool = self.__get_device()

        def call() -> T:
            # ibsta is thread-local, so it must be read in the thread, that executed the failed call.
            try:
                return func(*args)
            except GpibError as error:
                if device.ibsta() & Gpib.TIMO:
                    raise TimeoutError(str(error)) from None
                raise

        return await asyncio.get_running_loop().run_in_executor(threadpool, call)

    async def close(self) -> None:
        """
        Close the board or device handle by calling ibonl. Calling close() on a closed connection does nothing.
        """
        if self.__device is None or self.__threadpool is None:
            return

        device, threadpool = self.__device, self.__threadpool
        try:
            await asyncio.get_running_loop().run_in_executor(threadpool, device.close)
        finally:
            self.__device = None
            self.__threadpool = None
            threadpool.shutdown(wait=True, cancel_futures=True)

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
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        await self.__wrapper(self.__get_device()[0].command, cmd)

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
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        return await self.__wrapper(self.__get_device()[0].config, option, value)

    async def interface_clear(self) -> None:
        """
        Clear interface by calling ibsic.

        Raises
        ----------
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        await self.__wrapper(self.__get_device()[0].interface_clear)

    async def write(self, command: bytes) -> None:
        """
        Write data bytes by calling ibwrt.

        Parameters
        ----------
        command: bytes
            sequence of bytes to write

        Raises
        ----------
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        device, _ = self.__get_device()
        self.__logger.debug("Writing data: %r", command)
        await self.__wrapper(device.write, command)

    async def read(self, length: int | None = 512) -> bytes:
        """
        Read a number of data bytes by calling ibread.

        Parameters
        ----------
        length: int or None, default=512
            The maximum number of bytes to read. The read also ends, when the device asserts EOI or sends the EOS
            character, if enabled. Set to None to read until the end of the message, however long it is.

        Returns
        -------
        bytes
            sequence of bytes which was read

        Raises
        ----------
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        device, _ = self.__get_device()

        def read_until_end() -> bytes:
            # ibsta is thread-local, so it must be read in the same thread as ibrd
            chunks: list[bytes] = []
            while True:
                chunks.append(device.read(_READ_CHUNK_SIZE))
                if device.ibsta() & _END:
                    return b"".join(chunks)

        result: bytes
        if length is None:
            result = await self.__wrapper(read_until_end)
        else:
            result = await self.__wrapper(device.read, length)
        self.__logger.debug("Data read: %r", result)
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
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        return bool(await self.__wrapper(self.__get_device()[0].listener, pad, sad))

    async def lines(self) -> int:
        """
        Obtain the status of the control and handshaking bus lines of the bus.

        Returns
        -------
        int
            line capability and status bits

        Raises
        ----------
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        return await self.__wrapper(self.__get_device()[0].lines)

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
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        return await self.__wrapper(self.__get_device()[0].ask, option)

    async def clear(self) -> None:
        """
        Clear device by calling ibclr.

        Raises
        ----------
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        await self.__wrapper(self.__get_device()[0].clear)

    async def wait(self, eventmask: int) -> None:
        """
        Wait for event by calling ibwait.

        Parameters
        ----------
        eventmask: int
            ibsta bits designating events to wait for

        Raises
        ----------
        GpibError
        TimeoutError
            If the timeout expired before the event occurred
        ConnectionError
            If not connected
        """
        device, _ = self.__get_device()

        def wait_and_check() -> int:
            # ibsta is thread-local, so it must be read in the same thread as ibwait
            device.wait(eventmask)
            return int(device.ibsta())

        ibsta = await self.__wrapper(wait_and_check)
        if ibsta & Gpib.TIMO:
            raise TimeoutError("Timeout waiting for event.")

    async def serial_poll(self) -> int:
        """
        Read status byte by calling ibrsp.

        Returns
        -------
        int
            serial poll status byte

        Raises
        ----------
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        return await self.__wrapper(self.__get_device()[0].serial_poll)

    async def trigger(self) -> None:
        """
        Trigger device by calling ibtrg.

        Raises
        ----------
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        await self.__wrapper(self.__get_device()[0].trigger)

    async def remote_enable(self, enable: bool) -> None:
        """
        Set remote enable by calling ibsre.

        Parameters
        ----------
        enable: bool
            if True, set remote enable

        Raises
        ----------
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        await self.__wrapper(self.__get_device()[0].remote_enable, bool(enable))

    async def ibloc(self) -> int:
        """
        Push device to local mode by calling ibloc.

        Returns
        -------
        int
            ibsta value

        Raises
        ----------
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        return await self.__wrapper(self.__get_device()[0].ibloc)

    async def ibsta(self) -> int:
        """
        Get status value of the last call by calling ThreadIbsta or reading ibsta.

        Returns
        -------
        int
            ibsta value

        Raises
        ----------
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        return await self.__wrapper(self.__get_device()[0].ibsta)

    async def ibcnt(self) -> int:
        """
        Get number of transferred bytes of the last call by calling ThreadIbcntl or reading ibcnt.

        Returns
        -------
        int
            number of transferred bytes

        Raises
        ----------
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        return await self.__wrapper(self.__get_device()[0].ibcnt)

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
        ValueError
            If the timeout is negative
        GpibError
        TimeoutError
        ConnectionError
            If not connected
        """
        timeout = _calculate_timeout_value(value)
        result: int = await self.__wrapper(self.__get_device()[0].timeout, timeout)
        self.__timeout = timeout
        return result

    @staticmethod
    async def version() -> str | None:
        """
        Get the GPIB library version. Not implemented on Windows.

        Returns
        -------
        str or None
             GPIB library version or None if the library does not support it.
        """
        version: bytes | str | None = gpib.version()
        if isinstance(version, bytes):
            return version.decode("utf-8")
        return version
