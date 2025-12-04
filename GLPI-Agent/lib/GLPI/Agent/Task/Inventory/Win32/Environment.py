# glpi_agent/task/inventory/win32/environment.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools.Win32 import get_wmi_objects


class Environment(InventoryModule):
    """Windows Environment inventory module."""
    
    @staticmethod
    def category():
        return "environment"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        
        for obj in get_wmi_objects(
            class_name='Win32_Environment',
            properties=['SystemVariable', 'Name', 'VariableValue']
        ):
            system_variable = obj.get('SystemVariable')
            
            # 'true' value is provided when run remotely
            if not system_variable:
                continue
            
            if str(system_variable) not in ('1', 'true', 'True'):
                continue
            
            inventory.add_entry(
                section='ENVS',
                entry={
                    'KEY': obj.get('Name'),
                    'VAL': obj.get('VariableValue')
                }
            )