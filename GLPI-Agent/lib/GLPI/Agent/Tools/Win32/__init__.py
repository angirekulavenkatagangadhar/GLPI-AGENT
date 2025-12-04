"""
GLPI Agent Win32 Tools Module

Windows-specific tools and utilities.
"""

# Import functions from parent Win32.py file (sibling to Win32/ directory)
import sys
import os
import importlib.util

# Get the Win32.py file path (sibling to Win32/ directory)
win32_file = os.path.join(os.path.dirname(__file__), '..', 'Win32.py')
win32_file = os.path.abspath(win32_file)

if os.path.exists(win32_file):
    spec = importlib.util.spec_from_file_location("GLPI.Agent.Tools.Win32Module", win32_file)
    if spec and spec.loader:
        win32_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(win32_module)
        # Export functions
        get_wmi_objects = win32_module.get_wmi_objects
        get_registry_key = win32_module.get_registry_key
        __all__ = ['get_wmi_objects', 'get_registry_key']
    else:
        __all__ = []
else:
    __all__ = []

