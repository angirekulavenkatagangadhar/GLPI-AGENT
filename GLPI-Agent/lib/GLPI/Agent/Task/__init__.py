"""
GLPI Agent Task Module

This package contains all task implementations for the GLPI Agent.
"""

# Import base task class from parent Task.py file
import sys
import os
import importlib.util

# Get the Task.py file path (sibling to Task/ directory)
task_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Task.py')
if os.path.exists(task_file):
    spec = importlib.util.spec_from_file_location("GLPI.Agent.TaskModule", task_file)
    if spec and spec.loader:
        task_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(task_module)
        GLPITask = task_module.GLPITask
else:
    GLPITask = None

# Import tasks with error handling
try:
    from GLPI.Agent.Task.Inventory import InventoryTask
except ImportError:
    InventoryTask = None

try:
    from GLPI.Agent.Task.Collect import CollectTask
except ImportError:
    CollectTask = None

try:
    from GLPI.Agent.Task.WakeOnLan import WakeOnLanTask
except ImportError:
    WakeOnLanTask = None

try:
    from GLPI.Agent.Task.ESX import ESXTask
except ImportError:
    ESXTask = None

try:
    from GLPI.Agent.Task.NetDiscovery import NetDiscoveryTask
except ImportError:
    NetDiscoveryTask = None

try:
    from GLPI.Agent.Task.NetInventory import NetInventoryTask
except ImportError:
    NetInventoryTask = None

try:
    from GLPI.Agent.Task.RemoteInventory import RemoteInventoryTask
except ImportError:
    RemoteInventoryTask = None

__all__ = [
    'GLPITask',
    'InventoryTask',
    'CollectTask',
    'WakeOnLanTask',
    'ESXTask',
    'NetDiscoveryTask',
    'NetInventoryTask',
    'RemoteInventoryTask',
]

