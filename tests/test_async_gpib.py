"""Unit tests for the AsyncGpib wrapper using a fake GPIB backend (no hardware or Linux GPIB required)."""

# pylint: disable=missing-function-docstring  # The test names are descriptive

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from types import SimpleNamespace
from typing import Any, override

import pytest
from gpib_ctypes import gpib as gpib_lib

import async_gpib
from async_gpib import AsyncGpib, EosType, GpibError
from async_gpib import async_gpib as async_gpib_module

TIMO = 0x4000


def make_gpib_error(message: str) -> Exception:
    """Create a GpibError without calling into the (not installed) GPIB library."""
    error = GpibError.__new__(GpibError)
    Exception.__init__(error, message)
    return error


class FakeDevice:  # pylint: disable=missing-function-docstring,too-many-instance-attributes,too-many-public-methods
    """Stand-in for Gpib.Gpib. Like the real library, ibsta is thread-local."""

    instances: list[FakeDevice] = []
    fail_init = False

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, name: int | str, pad: int | None, sad: int, timeout: int, send_eoi: bool, eos_mode: int
    ) -> None:
        if FakeDevice.fail_init:
            raise make_gpib_error("dev() error")
        self.args = (name, pad, sad, timeout, send_eoi, eos_mode)
        self.calls: list[tuple[Any, ...]] = []
        self.threads: set[int] = {threading.get_ident()}
        self.error: Exception | None = None
        self.error_status = 0
        self.wait_status = 0
        self.closed = False
        self.read_response = b"HEWLETT-PACKARD,3478A\n"
        self._status = threading.local()
        FakeDevice.instances.append(self)

    @override
    def __repr__(self) -> str:
        return f"FakeDevice{self.args}"

    def _call(self, name: str, *args: Any, status: int = 0) -> None:
        self.threads.add(threading.get_ident())
        self.calls.append((name, *args))
        if self.error is not None:
            self._status.value = self.error_status
            raise self.error
        self._status.value = status

    def ibsta(self) -> int:
        self.threads.add(threading.get_ident())
        return int(getattr(self._status, "value", 0))

    def ibcnt(self) -> int:
        self._call("ibcnt")
        return 42

    def close(self) -> None:
        self._call("close")
        self.closed = True

    def command(self, cmd: bytes) -> None:
        self._call("command", cmd)

    def config(self, option: int, value: int) -> int:
        self._call("config", option, value)
        return 0x100

    def interface_clear(self) -> None:
        self._call("interface_clear")

    def write(self, data: bytes) -> None:
        self._call("write", data)

    def read(self, length: int) -> bytes:
        self._call("read", length)
        return self.read_response[:length]

    def listener(self, pad: int, sad: int) -> int:
        self._call("listener", pad, sad)
        return 1 if pad == 22 else 0

    def lines(self) -> int:
        self._call("lines")
        return 0xFF00

    def ask(self, option: int) -> int:
        self._call("ask", option)
        return 22

    def clear(self) -> None:
        self._call("clear")

    def wait(self, mask: int) -> None:
        self._call("wait", mask, status=self.wait_status)

    def serial_poll(self) -> int:
        self._call("serial_poll")
        return 0x41

    def trigger(self) -> None:
        self._call("trigger")

    def remote_enable(self, enable: bool) -> None:
        self._call("remote_enable", enable)

    def ibloc(self) -> int:
        self._call("ibloc")
        return 0x100

    def timeout(self, value: int) -> int:
        self._call("timeout", value)
        return 0x100


@pytest.fixture(autouse=True)
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the Gpib module with the fake device."""
    FakeDevice.instances = []
    FakeDevice.fail_init = False
    monkeypatch.setattr(async_gpib_module, "Gpib", SimpleNamespace(Gpib=FakeDevice, TIMO=TIMO))


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine to completion."""
    return asyncio.run(coro)


async def connected(**kwargs: Any) -> tuple[AsyncGpib, FakeDevice]:
    """Create and connect a device."""
    gpib = AsyncGpib(**kwargs)
    await gpib.connect()
    return gpib, FakeDevice.instances[-1]


def test_package_exports() -> None:
    assert isinstance(async_gpib.__version__, str)
    assert set(async_gpib.__all__) == {"AsyncGpib", "EosType", "GpibError", "__version__"}
    assert GpibError is gpib_lib.GpibError


def test_properties() -> None:
    gpib = AsyncGpib(name=0, pad=22, sad=0x60)
    assert gpib.id == 0
    assert gpib.pad == 22
    assert gpib.sad == 0x60
    assert str(gpib) == "Linux-GPIB at Gpib(0)"
    assert not gpib.is_connected


def test_connect_arguments() -> None:
    async def main() -> FakeDevice:
        gpib, device = await connected(
            name=1, pad=22, sad=0x61, timeout=2.0, send_eoi=0, eos_mode=EosType.REOS | EosType.BIN, eos_character=b"\n"
        )
        await gpib.disconnect()
        return device

    device = run(main())
    assert device.args == (1, 22, 0x61, gpib_lib.T3s, False, ord("\n") | (1 << 10) | (1 << 12))


def test_default_eos_mode() -> None:
    async def main() -> FakeDevice:
        gpib, device = await connected()
        await gpib.close()
        return device

    device = run(main())
    assert device.args == ("gpib0", None, 0, gpib_lib.T10s, True, 0)


@pytest.mark.parametrize("eos_character", [b"", b"\r\n"])
def test_invalid_eos_character(eos_character: bytes) -> None:
    with pytest.raises(ValueError):
        AsyncGpib(eos_character=eos_character)


@pytest.mark.parametrize(
    "timeout, expected",
    [
        (None, "TNONE"),
        (0, "T10us"),
        (10e-6, "T10us"),
        (11e-6, "T30us"),
        (1.0, "T1s"),
        (1.5, "T3s"),
        (1000.0, "T1000s"),
        (1e6, "T1000s"),
    ],
)
def test_calculate_timeout_value(timeout: float | None, expected: str) -> None:
    # pylint: disable=protected-access
    assert async_gpib_module._calculate_timeout_value(timeout) == getattr(gpib_lib, expected)


def test_negative_timeout() -> None:
    with pytest.raises(ValueError):
        AsyncGpib(timeout=-1)


def test_context_manager() -> None:
    async def main() -> tuple[AsyncGpib, FakeDevice]:
        async with AsyncGpib(name=0, pad=22) as gpib:
            assert gpib.is_connected
            return gpib, FakeDevice.instances[-1]

    gpib, device = run(main())
    assert not gpib.is_connected
    assert device.closed


def test_connect_twice_is_noop() -> None:
    async def main() -> None:
        gpib = AsyncGpib()
        await gpib.connect()
        await gpib.connect()
        assert len(FakeDevice.instances) == 1
        await gpib.close()

    run(main())


def test_reconnect() -> None:
    async def main() -> None:
        gpib = AsyncGpib()
        await gpib.connect()
        await gpib.close()
        await gpib.connect()
        assert gpib.is_connected
        assert len(FakeDevice.instances) == 2
        await gpib.close()

    run(main())


def test_connect_failure() -> None:
    FakeDevice.fail_init = True

    async def main() -> AsyncGpib:
        gpib = AsyncGpib()
        with pytest.raises(GpibError):
            await gpib.connect()
        return gpib

    gpib = run(main())
    assert not gpib.is_connected
    run(gpib.disconnect())  # must not raise


def test_close_without_connect() -> None:
    gpib = AsyncGpib()
    run(gpib.close())
    run(gpib.disconnect())


def test_close_failure_still_releases_resources() -> None:
    async def main() -> AsyncGpib:
        gpib, device = await connected()
        device.error = make_gpib_error("close() error")
        with pytest.raises(GpibError):
            await gpib.close()
        return gpib

    gpib = run(main())
    assert not gpib.is_connected


@pytest.mark.parametrize(
    "method, args, expected_call, expected_result",
    [
        ("command", (b"\x3f",), ("command", b"\x3f"), None),
        ("config", (1, 2), ("config", 1, 2), 0x100),
        ("interface_clear", (), ("interface_clear",), None),
        ("write", (b"*IDN?",), ("write", b"*IDN?"), None),
        ("read", (), ("read", 512), b"HEWLETT-PACKARD,3478A\n"),
        ("read", (4,), ("read", 4), b"HEWL"),
        ("listener", (22,), ("listener", 22, 0), True),
        ("listener", (5, 0x60), ("listener", 5, 0x60), False),
        ("lines", (), ("lines",), 0xFF00),
        ("ask", (1,), ("ask", 1), 22),
        ("clear", (), ("clear",), None),
        ("serial_poll", (), ("serial_poll",), 0x41),
        ("trigger", (), ("trigger",), None),
        ("remote_enable", (1,), ("remote_enable", True), None),
        ("remote_enable", (0,), ("remote_enable", False), None),
        ("ibloc", (), ("ibloc",), 0x100),
        ("ibcnt", (), ("ibcnt",), 42),
        ("timeout", (0.5,), ("timeout", gpib_lib.T1s), 0x100),
        ("timeout", (None,), ("timeout", gpib_lib.TNONE), 0x100),
    ],
)
def test_methods(method: str, args: tuple[Any, ...], expected_call: tuple[Any, ...], expected_result: Any) -> None:
    async def main() -> tuple[Any, FakeDevice]:
        async with AsyncGpib(name=0, pad=22) as gpib:
            return await getattr(gpib, method)(*args), FakeDevice.instances[-1]

    result, device = run(main())
    assert result == expected_result
    assert device.calls[0] == expected_call


def test_ibsta() -> None:
    async def main() -> int:
        async with AsyncGpib() as gpib:
            await gpib.wait(0x800)
            return await gpib.ibsta()

    assert run(main()) == 0


def test_timeout_is_kept_on_reconnect() -> None:
    async def main() -> FakeDevice:
        gpib = AsyncGpib(timeout=10.0)
        await gpib.connect()
        await gpib.timeout(1.0)
        await gpib.close()
        await gpib.connect()
        await gpib.close()
        return FakeDevice.instances[-1]

    assert run(main()).args[3] == gpib_lib.T1s


def test_all_calls_run_in_a_single_worker_thread() -> None:
    async def main() -> FakeDevice:
        async with AsyncGpib() as gpib:
            await gpib.write(b"*IDN?")
            await gpib.read()
            await gpib.serial_poll()
            return FakeDevice.instances[-1]

    device = run(main())
    assert len(device.threads) == 1
    assert threading.get_ident() not in device.threads


@pytest.mark.parametrize(
    "method, args",
    [
        ("command", (b"\x3f",)),
        ("config", (1, 2)),
        ("interface_clear", ()),
        ("write", (b"*IDN?",)),
        ("read", ()),
        ("listener", (22,)),
        ("lines", ()),
        ("ask", (1,)),
        ("clear", ()),
        ("wait", (0x800,)),
        ("serial_poll", ()),
        ("trigger", ()),
        ("remote_enable", (True,)),
        ("ibloc", ()),
        ("ibsta", ()),
        ("ibcnt", ()),
        ("timeout", (1.0,)),
    ],
)
def test_not_connected(method: str, args: tuple[Any, ...]) -> None:
    with pytest.raises(ConnectionError):
        run(getattr(AsyncGpib(), method)(*args))


def test_gpib_error_with_timeout_becomes_timeout_error() -> None:
    """The timeout is detected even though ibsta is thread-local, because it is read in the worker thread."""

    async def main() -> None:
        gpib, device = await connected()
        device.error = make_gpib_error("read() error")
        device.error_status = TIMO | 0x8000
        with pytest.raises(TimeoutError):
            await gpib.read()

    run(main())


def test_gpib_error_without_timeout_is_reraised() -> None:
    async def main() -> None:
        gpib, device = await connected()
        error = make_gpib_error("write() error")
        device.error = error
        device.error_status = 0x8000
        with pytest.raises(GpibError) as exc_info:
            await gpib.write(b"foo")
        assert exc_info.value is error

    run(main())


def test_other_errors_are_not_touched() -> None:
    async def main() -> None:
        gpib, device = await connected()
        device.error = OSError("Library not loaded")
        with pytest.raises(OSError):
            await gpib.trigger()

    run(main())


def test_wait() -> None:
    async def main() -> FakeDevice:
        gpib, device = await connected()
        await gpib.wait(0x800)
        await gpib.close()
        return device

    assert run(main()).calls[0] == ("wait", 0x800)


def test_wait_timeout() -> None:
    async def main() -> None:
        gpib, device = await connected()
        device.wait_status = TIMO
        with pytest.raises(TimeoutError):
            await gpib.wait(0x800 | TIMO)

    run(main())


@pytest.mark.parametrize("version, expected", [(b"4.3.6", "4.3.6"), ("4.3.6", "4.3.6"), (None, None)])
def test_version(monkeypatch: pytest.MonkeyPatch, version: bytes | str | None, expected: str | None) -> None:
    monkeypatch.setattr(async_gpib_module, "gpib", SimpleNamespace(version=lambda: version))
    assert run(AsyncGpib.version()) == expected
