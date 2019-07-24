#!/usr/bin/env python

from distutils.core import setup

setup(name='ShadowTorTools',
      version="0.0.1",
      description='A utility to generate ShadowTor networks, and to analyze and visualize ShadowTor output',
      author='Rob Jansen',
      url='https://github.com/shadow/shadow-plugin-tor',
      packages=['shadowtortools'],
      scripts=['shadowtortools/shadowtortools'],
     )
