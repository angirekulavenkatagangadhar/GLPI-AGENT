# glpi_agent/task/inventory/win32/printers.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools import empty
from GLPI.Agent.Tools.Win32 import get_wmi_objects, get_registry_key


class Printers(InventoryModule):
    """Windows Printers inventory module."""
    
    STATUS = [
        'Unknown',  # 0 is not defined
        'Other',
        'Unknown',
        'Idle',
        'Printing',
        'Warming Up',
        'Stopped printing',
        'Offline',
    ]
    
    ERR_STATUS = [
        'Unknown',
        'Other',
        'No Error',
        'Low Paper',
        'No Paper',
        'Low Toner',
        'No Toner',
        'Door Open',
        'Jammed',
        'Service Requested',
        'Output Bin Full',
        'Paper Problem',
        'Cannot Print Page',
        'User Intervention Required',
        'Out of Memory',
        'Server Unknown',
    ]
    
    @staticmethod
    def category():
        return "printer"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        
        for printer in self._get_printers():
            inventory.add_entry(
                section='PRINTERS',
                entry=printer
            )
    
    def _get_printers(self):
        seen = {}
        
        for obj in get_wmi_objects(
            class_name='Win32_Printer',
            properties=[
                'ExtendedDetectedErrorState', 'HorizontalResolution', 
                'VerticalResolution', 'Name', 'Comment', 'Description', 
                'DriverName', 'PortName', 'Network', 'Shared', 
                'PrinterStatus', 'ServerName', 'ShareName', 'PrintProcessor'
            ]
        ):
            if empty(obj.get('Name')) or empty(obj.get('PortName')):
                continue
            
            # Deduplicate printers with different names but same portname
            port_name = obj['PortName']
            if port_name in seen and port_name != obj['Name']:
                continue
            
            network_val = obj.get('Network')
            network = 1 if network_val and str(network_val) in ('1', 'true', 'True') else 0
            
            shared_val = obj.get('Shared')
            shared = 1 if shared_val and str(shared_val) in ('1', 'true', 'True') else 0
            
            printer_status = obj.get('PrinterStatus', 0)
            if printer_status is None:
                printer_status = 0
            
            printer = {
                'NAME': obj.get('Name'),
                'DRIVER': obj.get('DriverName'),
                'PORT': port_name,
                'NETWORK': network,
                'SHARED': shared,
                'STATUS': self.STATUS[printer_status] if printer_status < len(self.STATUS) else 'Unknown',
                'PRINTPROCESSOR': obj.get('PrintProcessor'),
            }
            
            # Add optional fields if not empty
            for field in ['Comment', 'Description', 'ServerName', 'ShareName']:
                if not empty(obj.get(field)):
                    printer[field.upper()] = obj[field]
            
            if obj.get('HorizontalResolution'):
                printer['RESOLUTION'] = str(obj['HorizontalResolution'])
                if obj.get('VerticalResolution'):
                    printer['RESOLUTION'] += f"x{obj['VerticalResolution']}"
            
            if port_name and 'USB' in port_name:
                serial = self._get_usb_printer_serial(port_name)
                if serial:
                    printer['SERIAL'] = serial
            elif obj.get('Serial'):
                printer['SERIAL'] = obj['Serial']
            
            if obj.get('ExtendedDetectedErrorState'):
                err_state = obj['ExtendedDetectedErrorState']
                if err_state < len(self.ERR_STATUS):
                    printer['ERRSTATUS'] = self.ERR_STATUS[err_state]
            
            seen[port_name] = printer
        
        printers = sorted(seen.values(), key=lambda p: p['NAME'].lower())
        return printers
    
    def _get_usb_printer_serial(self, port_name):
        usbprint_key = get_registry_key(
            path="HKEY_LOCAL_MACHINE/SYSTEM/CurrentControlSet/Enum/USBPRINT",
            required=['PortName', 'ContainerID']
        )
        
        usb_key = get_registry_key(
            path="HKEY_LOCAL_MACHINE/SYSTEM/CurrentControlSet/Enum/USB",
            required=['ParentIdPrefix', 'ContainerID']
        )
        
        # ContainerID approach
        container_id = self._get_usb_container_id(usbprint_key, port_name)
        if container_id:
            serial = self._get_usb_serial_from_container_id(usb_key, container_id)
            if serial:
                # Cleanup any zero at the beginning
                serial = serial.lstrip('0') if not empty(serial) else serial
                if serial:
                    return serial
        
        # Fallback on ParentIdPrefix
        prefix = self._get_usb_prefix(usbprint_key, port_name)
        if prefix:
            serial = self._get_usb_serial_from_prefix(usb_key, prefix)
            if serial:
                return serial
        
        return None
    
    def _get_usb_container_id(self, print_key, port_name):
        if not print_key:
            return None
        
        for device in print_key.values():
            if not isinstance(device, dict):
                continue
            for subdevice_name, subdevice in device.items():
                if not isinstance(subdevice, dict):
                    continue
                
                dev_params = subdevice.get('Device Parameters/')
                if not dev_params or not isinstance(dev_params, dict):
                    continue
                
                if (dev_params.get('/PortName') == port_name):
                    return subdevice.get('/ContainerID')
        
        return None
    
    def _get_usb_prefix(self, print_key, port_name):
        if not print_key:
            return None
        
        for device in print_key.values():
            if not isinstance(device, dict):
                continue
            for subdevice_name, subdevice in device.items():
                if not isinstance(subdevice, dict):
                    continue
                
                dev_params = subdevice.get('Device Parameters/')
                if not dev_params or not isinstance(dev_params, dict):
                    continue
                
                if dev_params.get('/PortName') == port_name:
                    prefix = subdevice_name.rstrip('/')
                    prefix = prefix.replace(f"&{port_name}", '')
                    return prefix
        
        return None
    
    def _get_usb_serial_from_prefix(self, usb_key, prefix):
        if not usb_key:
            return None
        
        for device in usb_key.values():
            if not isinstance(device, dict):
                continue
            for subdevice_name, subdevice in device.items():
                if not isinstance(subdevice, dict):
                    continue
                
                if subdevice.get('/ParentIdPrefix') == prefix:
                    serial = subdevice_name.rstrip('/')
                    # pseudo serial generated by windows
                    if '&' in serial:
                        return None
                    return serial
        
        return None
    
    def _get_usb_serial_from_container_id(self, usb_key, container_id):
        if not usb_key:
            return None
        
        for device in usb_key.values():
            if not isinstance(device, dict):
                continue
            for subdevice_name, subdevice in device.items():
                if not isinstance(subdevice, dict):
                    continue
                
                if subdevice.get('/ContainerID') == container_id:
                    # pseudo serial generated by windows
                    if '&' in subdevice_name:
                        continue
                    serial = subdevice_name.rstrip('/')
                    return serial
        
        return None