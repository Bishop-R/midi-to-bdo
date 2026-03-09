#!/usr/bin/env python3
"""Bundle midi2bdo_gui into a standalone executable using PyInstaller.

Requirements:
    pip install pyinstaller

Usage:
    python build.py

Must be run on the target OS (Windows for .exe, Linux for Linux binary).
"""

import os
import sys

import PyInstaller.__main__

sep = ';' if sys.platform.startswith('win') else ':'

PyInstaller.__main__.run([
    'midi2bdo_gui.py',
    '--onefile',
    '--windowed',
    '--name', 'MIDI to BDO',
    '--collect-all', 'customtkinter',
    '--hidden-import', '_ice',
    '--add-data', f'bdo_theme.json{sep}.',
    '--distpath', 'release',
    '--noconfirm',
])
