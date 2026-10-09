"""Build dist/DataStore.exe (single file). Run inside a venv with: pip install pyinstaller pillow"""
import os

import PyInstaller.__main__

PyInstaller.__main__.run([
    "DataStore.py",
    "--name", "DataStore",
    "--onefile",
    "--console",  # the window shows the address; closing it stops the app
    "--add-data", f"datastore/web{os.pathsep}datastore/web",
    "--noconfirm",
    "--clean",
])
