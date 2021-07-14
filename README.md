# async_gpib
Python3 AsyncIO [Linux GPIB Wrapper](https://linux-gpib.sourceforge.io/). The library requires Python [asyncio](https://docs.python.org/3/library/asyncio.html) and is a thin wrapper for the threaded Linux GPIB Wrapper library.

## Supported Devices

### Instruments
|Device|Supported|Tested|Comments|
|--|--|--|--|
|[Fluke 5440B](https://github.com/PatrickBaus/pyAsyncFluke5440B)|:heavy_check_mark:|:heavy_check_mark:|  |
|[HP 3478A](https://github.com/PatrickBaus/pyAsyncHP3478A)|:heavy_check_mark:|:heavy_check_mark:|  |

## Setup
There are currently no packages for Linux GPIB available on all platforms. To install the library it is required to install Linux GPIB.

### Linux GPIB:
These instructions are for Ubuntu:
```bash
sudo apt install subversion build-essential autoconf libtool flex bison python3-dev
svn checkout svn://svn.code.sf.net/p/linux-gpib/code/trunk linux-gpib-code
cd ~/linux-gpib-code/linux-gpib-kernel
make
sudo make install  # ignore the signing errors
sudo groupadd gpib  # seems not to be installed
sudo modprobe ni_usb_gpib
cd ~/linux-gpib-code/linux-gpib-user
./bootstrap
./configure --sysconfdir=/etc
make
sudo make install
sudo ldconfig
```

### Linux GPIB Python module:
Once Linux GPIB is installed, you can either install the python package or use the `gpib-ctypes` package.
```bash
python3 -m venv env  # virtual environment, optional
source env/bin/activate
pip install -e ~/linux-gpib-code/linux-gpib-user/language/python/
```

### async_gpib Python module
There is an install script available to make installation simple
```bash
python3 -m venv env  # virtual environment, optional
source env/bin/activate
pip python3 setup.py install
```

## Usage
Initialize the GPIB adapter
```python
from async_gpib.async_gpib import AsyncGpib
# Create a controller and talk to device address 22
gpib_device = AsyncGpib(name=0, pad=22)

# Connect to the controller. This must be done inside the loop
await gpib_device.connect()

# Add your code here

# Disconnect after we are done
await gpib_device.disconnect()
```
See [examples/](examples/) for more working examples.

## Support for Multiple Devices
> :warning: **Concurrency with multiple devices**: Note, that when using a single adapter to control multiple devices, there is no concurrency on the GPIB bus. This means, there is **no** speed increase, when making asynchronous reads from multiple devices on the bus regarding the transfer time.

## Versioning

I use [SemVer](http://semver.org/) for versioning. For the versions available, see the [tags on this repository](https://github.com/PatrickBaus/pyAsyncPrologix/tags). 

## Authors

* **Patrick Baus** - *Initial work* - [PatrickBaus](https://github.com/PatrickBaus)

## License


This project is licensed under the GPL v3 license - see the [LICENSE](LICENSE) file for details

