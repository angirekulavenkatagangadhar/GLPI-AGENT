"""Compatibility: glpi_agent.tools.win32 -> GLPI.Agent.Tools.Win32"""
from GLPI.Agent.Tools.Win32 import get_wmi_objects, get_registry_key
__all__ = ['get_wmi_objects', 'get_registry_key']

