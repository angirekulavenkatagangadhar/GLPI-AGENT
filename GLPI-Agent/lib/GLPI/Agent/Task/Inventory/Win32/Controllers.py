# glpi_agent/task/inventory/win32/controllers.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools.Generic import get_pci_device_vendor
from GLPI.Agent.Tools.Win32 import get_wmi_objects


class Controllers(InventoryModule):
    """Windows Controllers inventory module."""
    
    @staticmethod
    def category():
        return "controller"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        logger = params.get('logger')
        datadir = params.get('datadir')
        
        hardware = inventory.get_hardware()
        physical = hardware.get('VMSYSTEM') == 'Physical' if hardware else False
        
        for controller in self._get_controllers(logger=logger, datadir=datadir):
            inventory.add_entry(
                section='CONTROLLERS',
                entry=controller
            )
            
            if physical and controller.get('NAME') and 'QEMU' in controller['NAME'].upper():
                inventory.set_hardware({'VMSYSTEM': 'QEMU'})
    
    def _get_controllers(self, **params):
        controllers = []
        seen = {}
        
        for controller in self._get_controllers_from_wmi(**params):
            device_id = controller.get('deviceid', '')
            
            import re
            
            # Extract vendor and product IDs
            match = re.search(r'PCI\\VEN_(\S{4})&DEV_(\S{4})', device_id)
            if match:
                controller['VENDORID'] = match.group(1).lower()
                controller['PRODUCTID'] = match.group(2).lower()
            
            # Extract subsystem ID
            match = re.search(r'&SUBSYS_(\S{4})(\S{4})', device_id)
            if match:
                controller['PCISUBSYSTEMID'] = f"{match.group(2).lower()}:{match.group(1).lower()}"
            
            # only devices with a PCIID sounds reasonable
            if not controller.get('VENDORID') or not controller.get('PRODUCTID'):
                continue
            
            # avoid duplicates
            vendor_id = controller['VENDORID']
            product_id = controller['PRODUCTID']
            
            if vendor_id not in seen:
                seen[vendor_id] = {}
            if product_id in seen[vendor_id]:
                continue
            seen[vendor_id][product_id] = True
            
            del controller['deviceid']
            
            vendor_id_lower = vendor_id.lower()
            device_id_lower = product_id.lower()
            subdevice_id = controller.get('PCISUBSYSTEMID', '').lower()
            
            vendor = get_pci_device_vendor(id=vendor_id_lower, **params)
            if vendor:
                controller['MANUFACTURER'] = vendor['name']
                
                if vendor.get('devices', {}).get(device_id_lower):
                    entry = vendor['devices'][device_id_lower]
                    controller['CAPTION'] = entry['name']
                    
                    if subdevice_id and entry.get('subdevices', {}).get(subdevice_id):
                        controller['NAME'] = entry['subdevices'][subdevice_id]['name']
                    else:
                        controller['NAME'] = entry['name']
            
            controllers.append(controller)
        
        return controllers
    
    def _get_controllers_from_wmi(self, **params):
        controllers = []
        
        classes = [
            'Win32_FloppyController', 'Win32_IDEController', 'Win32_SCSIController',
            'Win32_VideoController', 'Win32_InfraredDevice', 'Win32_USBController',
            'Win32_1394Controller', 'Win32_PCMCIAController', 'CIM_LogicalDevice'
        ]
        
        for class_name in classes:
            for obj in get_wmi_objects(
                class_name=class_name,
                properties=['Name', 'Manufacturer', 'Caption', 'DeviceID']
            ):
                controllers.append({
                    'NAME': obj.get('Name'),
                    'MANUFACTURER': obj.get('Manufacturer'),
                    'CAPTION': obj.get('Caption'),
                    'TYPE': obj.get('Caption'),
                    'deviceid': obj.get('DeviceID'),
                })
        
        return controllers