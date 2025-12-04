# glpi_agent/task/inventory/win32/license.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools import has_file
from glpi_agent.tools.license import (
    decode_microsoft_key, get_adobe_licenses_without_sqlite
)
from GLPI.Agent.Tools.Win32 import (
    get_wmi_objects, get_registry_key, get_registry_key_value, is64bit
)


class License(InventoryModule):
    """Windows License inventory module."""
    
    def __init__(self):
        super().__init__()
        self._seen_products = {}
    
    @staticmethod
    def category():
        return "licenseinfo"
    
    def is_enabled(self, **params):
        return True
    
    def _reset_seen_products(self):
        self._seen_products = {}
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        
        licenses = []
        
        # Important for remote inventory optimization
        required_for_office = [
            'DigitalProductID', 'ProductCode', 'ProductName', 'ProductNameBrand',
            'ProductID', 'SPLevel', 'OEM', 'ConvertToEdition',
            'ProductNameNonQualified', 'ProductNameVersion', 'TrialType'
        ]
        
        office_key = get_registry_key(
            path="HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft/Office",
            required=required_for_office
        )
        if office_key:
            self._scan_office_licences(office_key)
        
        file_adobe = 'C:\\Program Files\\Common Files\\Adobe\\Adobe PCD\\cache\\cache.db'
        if is64bit():
            file_adobe = 'C:\\Program Files (x86)\\Common Files\\Adobe\\Adobe PCD\\cache\\cache.db'
            office_key32 = get_registry_key(
                path="HKEY_LOCAL_MACHINE/SOFTWARE/Wow6432Node/Microsoft/Office",
                required=required_for_office
            )
            if office_key32:
                self._scan_office_licences(office_key32)
        
        if has_file(file_adobe):
            licenses.extend(get_adobe_licenses_without_sqlite(file_adobe))
        
        self._scan_wmi_software_licensing_products()
        
        licenses.extend(self._get_seen_products())
        
        for license_entry in licenses:
            inventory.add_entry(
                section='LICENSEINFOS',
                entry=license_entry
            )
        
        self._reset_seen_products()
    
    def _get_seen_products(self):
        if not self._seen_products:
            return []
        
        products = [p for p in self._seen_products.values() if p.get('KEY')]
        
        return sorted(products, key=lambda x: (
            x.get('NAME', ''),
            x.get('FULLNAME', ''),
            x.get('KEY', '')
        ))
    
    def _scan_wmi_software_licensing_products(self):
        for obj in get_wmi_objects(
            moniker='winmgmts:\\\\.\\root\\CIMV2',
            class_name='SoftwareLicensingProduct',
            properties=[
                'Name', 'Description', 'LicenseStatus', 'PartialProductKey',
                'ID', 'ProductKeyChannel', 'ProductKeyID', 'ProductKeyID2',
                'ApplicationID'
            ]
        ):
            if not obj.get('PartialProductKey') or not obj.get('LicenseStatus'):
                continue
            
            # Skip operating system license as still set from OS module
            description = obj.get('Description', '')
            if description and 'Operating System' in description:
                continue
            
            obj_id = obj.get('ID')
            if obj_id:
                wmi_licence = self._get_wmi_license(obj)
                uuid_lc = obj_id.lower()
                
                if uuid_lc not in self._seen_products:
                    self._seen_products[uuid_lc] = wmi_licence
                else:
                    if self._seen_products[uuid_lc].get('FULLNAME'):
                        wmi_licence['FULLNAME'] = self._seen_products[uuid_lc]['FULLNAME']
                    if self._seen_products[uuid_lc].get('TRIAL'):
                        wmi_licence['TRIAL'] = self._seen_products[uuid_lc]['TRIAL']
                    
                    uuid_to_delete = uuid_lc
                    if self._seen_products[uuid_lc].get('PRODUCTCODE'):
                        # Change key Target
                        uuid_lc = self._seen_products[uuid_lc]['PRODUCTCODE']
                        if (self._seen_products.get(uuid_lc) and 
                            self._seen_products[uuid_lc].get('KEY')):
                            wmi_key = wmi_licence['KEY'][-5:]
                            if wmi_key in self._seen_products[uuid_lc]['KEY']:
                                # Skip this licence - Registry give more information
                                continue
                    
                    del self._seen_products[uuid_to_delete]
                    self._seen_products[uuid_lc] = wmi_licence
    
    def _scan_office_licences(self, key):
        if not key:
            return
        
        for version_key, version_value in key.items():
            # Skip value keys
            if version_key.startswith('/'):
                continue
            
            if not isinstance(version_value, dict):
                continue
            
            registration_key = version_value.get('Registration/')
            if not registration_key:
                continue
            
            for uuid_key, uuid_value in registration_key.items():
                # Skip value keys
                if uuid_key.startswith('/'):
                    continue
                
                if not isinstance(uuid_value, dict):
                    continue
                
                import re
                match = re.search(r'([-\w]+)', uuid_key)
                if not match:
                    continue
                
                clean_uuid_key = match.group(1).lower()
                
                # Keep in memory seen product with ProductCode value or DigitalProductID
                if uuid_value.get('/DigitalProductID'):
                    self._seen_products[clean_uuid_key] = self._get_office_license(uuid_value)
                
                product_name = get_registry_key_value(uuid_value, 'ProductName')
                if uuid_value.get('/ProductCode') and product_name:
                    product_code = uuid_value['/ProductCode']
                    match = re.search(r'([-\w]+)', product_code)
                    productcode = match.group(1).lower() if match else ""
                    
                    self._seen_products[clean_uuid_key] = {
                        'PRODUCTCODE': productcode,
                        'FULLNAME': product_name,
                    }
                    
                    product_name_brand = uuid_value.get('/ProductNameBrand', '')
                    if product_name_brand and 'trial' in product_name_brand.lower():
                        self._seen_products[clean_uuid_key]['TRIAL'] = 1
    
    def _get_wmi_license(self, wmi):
        key = wmi.get('PartialProductKey', '')
        if key and len(key) == 5:
            key = f"XXXXX-XXXXX-XXXXX-XXXXX-{key}"
        
        channel = wmi.get('ProductKeyChannel', '')
        
        license_entry = {
            'KEY': key,
            'PRODUCTID': wmi.get('ProductKeyID2') or wmi.get('ApplicationID') or wmi.get('ProductKeyID'),
            'OEM': 1 if 'OEM' in channel.upper() else 0,
            'FULLNAME': wmi.get('Description'),
            'NAME': wmi.get('Name')
        }
        
        return license_entry
    
    def _get_office_license(self, key):
        license_entry = {
            'KEY': decode_microsoft_key(key.get('/DigitalProductID')),
            'PRODUCTID': key.get('/ProductID'),
            'UPDATE': key.get('/SPLevel'),
            'OEM': key.get('/OEM'),
            'FULLNAME': (get_registry_key_value(key, 'ProductName') or
                        get_registry_key_value(key, 'ConvertToEdition')),
            'NAME': (get_registry_key_value(key, 'ProductNameNonQualified') or
                    get_registry_key_value(key, 'ProductNameVersion'))
        }
        
        trial_type = key.get('/TrialType')
        if trial_type:
            import re
            match = re.search(r'(\d+)$', str(trial_type))
            if match:
                license_entry['TRIAL'] = int(match.group(1))
        
        products = []
        for variable in key.keys():
            import re
            match = re.match(r'/(\w+)NameVersion$', variable)
            if match:
                products.append(match.group(1))
        
        if products:
            license_entry['COMPONENTS'] = '/'.join(sorted(products))
        
        return license_entry