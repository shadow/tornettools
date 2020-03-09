#!/usr/bin/env python

from distutils.core import setup

setup(name='TorNetGen',
      version="0.0.0",
      description='A utility to generate private Tor network configurations',
      author='Rob Jansen',
      url='https://github.com/shadow/tornetgen',
      packages=['tornetgen'],
      scripts=['tornetgen/tornetgen'],
     )
