# glpi_agent/task/inventory/win32/registry.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools.Win32 import get_registry_value


class Registry(InventoryModule):
    """Windows Registry inventory module."""
    
    HIVES = [
        'HKEY_CLASSES_ROOT',
        'HKEY_CURRENT_USER',
        'HKEY_LOCAL_MACHINE',
        'HKEY_USERS',
        'HKEY_CURRENT_CONFIG',
        'HKEY_DYN_DATA'
    ]
    
    @staticmethod
    def category():
        return "registry"
    
    def is_enabled(self, **params):
        registry = params.get('registry')
        return registry and len(registry) > 0
    
    def _get_registry_data(self, **params):
        data = []
        registry = params.get('registry')
        logger = params.get('logger')
        
        # Handle both list and single dict
        param_data = registry.get('PARAM')
        if isinstance(param_data, list):
            registrys = param_data
        else:
            registrys = [param_data] if param_data else []
        
        for option in registrys:
            name = option.get('NAME')
            regkey = option.get('REGKEY')
            regtree = option.get('REGTREE')
            content = option.get('content')
            
            # This should never happen, err wait...
            if not content:
                continue
            
            regkey = regkey.replace('\\', '/')
            path = f"{self.HIVES[regtree]}/{regkey}/{content}"
            
            value = get_registry_value(path=path, logger=logger)
            
            if isinstance(value, dict):
                for key, val in value.items():
                    data.append({
                        'section': 'REGISTRY',
                        'entry': {
                            'NAME': name,
                            'REGVALUE': f"{key}={val}"
                        }
                    })
            else:
                data.append({
                    'section': 'REGISTRY',
                    'entry': {
                        'NAME': name,
                        'REGVALUE': value
                    }
                })
        
        return data
    
    def do_inventory(self, **params):
        registry = params.get('registry')
        
        if not registry or registry.get('NAME') != 'REGISTRY':
            return
        
        inventory = params.get('inventory')
        logger = params.get('logger')
        
        for data in self._get_registry_data(registry=registry, logger=logger):
            inventory.add_entry(**data)