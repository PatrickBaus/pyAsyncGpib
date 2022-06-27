# pylint: disable=missing-module-docstring
from ._version import __version__
from .async_gpib import AsyncGpib

try:
    import gpib.GpibError
except ModuleNotFoundError:
    from gpib_ctypes.gpib import GpibError
