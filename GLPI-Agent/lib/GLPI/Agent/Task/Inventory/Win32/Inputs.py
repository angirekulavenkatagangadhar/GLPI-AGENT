# glpi_agent/task/inventory/win32/inputs.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools.Win32 import get_wmi_objects


class Inputs(InventoryModule):
    """Windows Inputs inventory module."""
    
    MOUSE_INTERFACE = {
        1: 'Other',
        2: 'Unknown',
        3: 'Serial',
        4: 'PS/2',
        5: 'Infrared',
        6: 'HP-HIL',
        7: 'Bus Mouse',
        8: 'ADB (Apple Desktop Bus)',
        160: 'Bus Mouse DB-9',
        161: 'Bus Mouse Micro-DIN',
        162: 'USB',
    }
    
    @staticmethod
    def category():
        return "input"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        seen = set()
        inventory = params.get('inventory')
        
        # Keyboards
        for obj in get_wmi_objects(
            class_name='Win32_Keyboard',
            properties=['Name', 'Caption', 'Manufacturer', 'Description', 'Layout']
        ):
            input_entry = {
                'NAME': obj.get('Name'),
                'CAPTION': obj.get('Caption'),
                'MANUFACTURER': obj.get('Manufacturer'),
                'DESCRIPTION': obj.get('Description'),
                'LAYOUT': obj.get('Layout'),
            }
            
            # avoid duplicates
            name = input_entry.get('NAME')
            if name and name in seen:
                continue
            if name:
                seen.add(name)
            
            inventory.add_entry(
                section='INPUTS',
                entry=input_entry
            )
        
        # Pointing devices
        for obj in get_wmi_objects(
            class_name='Win32_PointingDevice',
            properties=['Name', 'Caption', 'Manufacturer', 'Description', 
                       'PointingType', 'DeviceInterface']
        ):
            device_interface = obj.get('DeviceInterface')
            interface = self.MOUSE_INTERFACE.get(device_interface) if device_interface else None
            
            input_entry = {
                'NAME': obj.get('Name'),
                'CAPTION': obj.get('Caption'),
                'MANUFACTURER': obj.get('Manufacturer'),
                'DESCRIPTION': obj.get('Description'),
                'POINTINGTYPE': obj.get('PointingType'),
                'INTERFACE': interface,
            }
            
            # avoid duplicates
            name = input_entry.get('NAME')
            if name and name in seen:
                continue
            if name:
                seen.add(name)
            
            inventory.add_entry(
                section='INPUTS',
                entry=input_entry
            )