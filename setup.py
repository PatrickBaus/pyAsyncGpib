from setuptools import setup

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
   name='async_gpib',
   version='1.0.1',
   author='Patrick Baus',
   author_email='patrick.baus@physik.tu-darmstadt.de',
   url='https://github.com/PatrickBaus/pyAsyncGpib',
   description='An thin AsyncIO wrapper around Linux GPIB',
   long_description=long_description,
   classifiers=[
    'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
    'Programming Language :: Python',
    'Development Status :: 4 - Beta',
    'Intended Audience :: Developers',
    'Natural Language :: English',
    'Topic :: Automation',
   ],
   keywords='Linux GPIB',
   license='GPL',
   license_files=('LICENSE',),
   packages=['async_gpib'],  # same as name
   install_requires=[],  # external packages as dependencies
   extras_require={
        'GPIB':  ['gpib-ctypes>=0.3',],
    }
)
