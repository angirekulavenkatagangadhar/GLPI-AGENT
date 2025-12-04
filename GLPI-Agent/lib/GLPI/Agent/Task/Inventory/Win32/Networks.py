# glpi_agent/task/inventory/win32/networks.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from glpi_agent.tools.network import get_interfaces
from GLPI.Agent.Tools.Win32 import get_registry_key


class Networks(InventoryModule):
    """Windows Networks inventory module."""
    
    @staticmethod
    def category():
        return "network"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        interfaces = get_interfaces()
        if not interfaces:
            return
        
        inventory = params.get('inventory')
        gateways = []
        dns = []
        
        keys = None
        if any(iface.get('PNPDEVICEID') for iface in interfaces):
            keys = get_registry_key(
                path="HKEY_LOCAL_MACHINE/SYSTEM/CurrentControlSet/Control/Network/{4D36E972-E325-11CE-BFC1-08002BE10318}",
                required=['PnpInstanceID', 'MediaSubType']
            )
        
        for interface in interfaces:
            if interface.get('IPGATEWAY'):
                gateways.append(interface['IPGATEWAY'])
            
            if interface.get('dns'):
                dns.append(interface['dns'])
            
            # Cleanup not necessary values
            interface.pop('dns', None)
            interface.pop('DNSDomain', None)
            interface.pop('GUID', None)
            
            if interface.get('PNPDEVICEID') and not interface.get('TYPE'):
                media_type = self._get_media_type(interface['PNPDEVICEID'], keys)
                if media_type is not None:
                    interface['TYPE'] = media_type
            
            inventory.add_entry(
                section='NETWORKS',
                entry=interface
            )
        
        # Remove duplicates while preserving order
        unique_gateways = []
        seen = set()
        for gw in gateways:
            if gw not in seen:
                seen.add(gw)
                unique_gateways.append(gw)
        
        unique_dns = []
        seen = set()
        for d in dns:
            if d not in seen:
                seen.add(d)
                unique_dns.append(d)
        
        inventory.set_hardware({
            'DEFAULTGATEWAY': '/'.join(unique_gateways),
            'DNS': '/'.join(unique_dns),
        })
    
    def _get_media_type(self, deviceid, keys):
        if not deviceid or not keys:
            return None
        
        subtype = None
        
        for subkey_name, subkey_value in keys.items():
            # skip variables
            if subkey_name.startswith('/'):
                continue
            
            if not isinstance(subkey_value, dict):
                continue
            
            subkey_connection = subkey_value.get('Connection/')
            if not subkey_connection:
                continue
            
            subkey_deviceid = subkey_connection.get('/PnpInstanceID')
            if not subkey_deviceid:
                continue
            
            # Normalize PnpInstanceID
            subkey_deviceid = subkey_deviceid.replace('\\\\', '\\')
            
            if subkey_deviceid.lower() == deviceid.lower():
                subtype = subkey_connection.get('/MediaSubType')
                break
        
        if subtype is None:
            return None
        
        media_type_map = {
            '0x00000001': 'ethernet',
            '0x00000002': 'wifi',
            '0x00000007': 'bluetooth'
        }
        
        return media_type_map.get(subtype)