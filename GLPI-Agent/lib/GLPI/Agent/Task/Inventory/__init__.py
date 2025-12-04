"""
GLPI Agent Task Inventory Module
"""

from GLPI.Agent.Task.Inventory.Version import VERSION

# Import InventoryTask from parent Inventory.py file
import sys
import os
import importlib.util

# Get the Inventory.py file path (sibling to Inventory/ directory)
inventory_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Inventory.py')
if os.path.exists(inventory_file):
    spec = importlib.util.spec_from_file_location("GLPI.Agent.Task.InventoryModule", inventory_file)
    if spec and spec.loader:
        inventory_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inventory_module)
        if hasattr(inventory_module, 'InventoryTask'):
            InventoryTask = inventory_module.InventoryTask
            __all__ = ['VERSION', 'InventoryTask']
        else:
            __all__ = ['VERSION']
else:
    __all__ = ['VERSION']

__version__ = VERSION

