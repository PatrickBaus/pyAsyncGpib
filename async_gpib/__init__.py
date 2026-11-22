"""
This is a Python AsyncIO wrapper for Linux GPIB and the gpib_ctypes package.
"""

from ._version import __version__
from .async_gpib import AsyncGpib, EosType, GpibError

__all__ = ["AsyncGpib", "EosType", "GpibError", "__version__"]
