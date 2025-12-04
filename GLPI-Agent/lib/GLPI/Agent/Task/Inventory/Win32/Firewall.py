# glpi_agent/task/inventory/win32/firewall.py

from copy import deepcopy

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools import hex2dec
from GLPI.Agent.Tools.Win32 import get_registry_value, get_registry_key
from glpi_agent.tools.network import get_interfaces
from glpi_agent.tools.constants import STATUS_ON, STATUS_OFF


class Firewall(InventoryModule):
    """Windows Firewall inventory module."""
    
    MAPPING_FIREWALL_PROFILES = ['public', 'standard', 'domain']
    
    @staticmethod
    def category():
        return "firewall"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        
        for profile in self._make_profile_and_connections_association():
            inventory.add_entry(
                section='FIREWALL',
                entry=profile
            )
    
    def _get_firewall_profiles(self, **params):
        path = "HKEY_LOCAL_MACHINE/SYSTEM/CurrentControlSet/Services/SharedAccess/Parameters/FirewallPolicy"
        
        sub_keys = {
            'domain': 'DomainProfile',
            'public': 'PublicProfile',
            'standard': 'StandardProfile'
        }
        
        profiles = {}
        
        for profile, sub_key in sub_keys.items():
            enabled = hex2dec(get_registry_value(
                path=f"{path}/{sub_key}/EnableFirewall",
                method="GetDWORDValue"
            ))
            profiles[profile] = {
                'STATUS': STATUS_ON if enabled else STATUS_OFF,
                'PROFILE': sub_key
            }
        
        return profiles
    
    def _make_profile_and_connections_association(self, **params):
        firewall_profiles = self._get_firewall_profiles()
        if not firewall_profiles:
            return []
        
        profiles_key = params.get('profilesKey') or get_registry_key(
            path='HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft/Windows NT/CurrentVersion/NetworkList/Profiles',
            required=['ProfileName', 'Category']
        )
        
        if not profiles_key:
            return []
        
        signatures_key = params.get('signaturesKey') or get_registry_key(
            path='HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft/Windows NT/CurrentVersion/NetworkList/Signatures',
            required=['ProfileGuid', 'FirstNetwork']
        )
        
        if not signatures_key:
            return []
        
        dns_registered_adapters = get_registry_key(
            path='HKEY_LOCAL_MACHINE/SYSTEM/CurrentControlSet/services/Tcpip/Parameters/DNSRegisteredAdapters',
            required=['PrimaryDomainName']
        )
        
        if not dns_registered_adapters:
            return []
        
        for interface in get_interfaces():
            if interface.get('STATUS') != 'Up':
                continue
            
            profile = None
            guid = interface.get('GUID')
            domain_settings = dns_registered_adapters.get(f"{guid}/") if guid else None
            
            # check if connection with domain
            if domain_settings:
                profile = self._retrieve_firewall_profile_with_domain(
                    profileName=domain_settings.get('/PrimaryDomainName'),
                    profilesKey=profiles_key
                )
            else:
                profile = self._retrieve_firewall_profile_without_domain(
                    DNSDomain=interface.get('DNSDomain'),
                    profilesKey=profiles_key,
                    signaturesKey=signatures_key
                )
            
            if not profile:
                continue
            
            category = hex2dec(profile.get('/Category'))
            if category is None or category >= len(self.MAPPING_FIREWALL_PROFILES):
                continue
            
            profile_name = self.MAPPING_FIREWALL_PROFILES[category]
            
            if 'CONNECTIONS' not in firewall_profiles[profile_name]:
                firewall_profiles[profile_name]['CONNECTIONS'] = []
            
            connection = {'DESCRIPTION': interface.get('DESCRIPTION')}
            if interface.get('IPADDRESS'):
                connection['IPADDRESS'] = interface['IPADDRESS']
            if interface.get('IPADDRESS6'):
                connection['IPADDRESS6'] = interface['IPADDRESS6']
            
            firewall_profiles[profile_name]['CONNECTIONS'].append(connection)
        
        profiles = []
        for profil in sorted(firewall_profiles.keys()):
            p = firewall_profiles[profil]
            p_list = []
            
            if p.get('CONNECTIONS') and isinstance(p['CONNECTIONS'], list):
                conns = p['CONNECTIONS']
                del p['CONNECTIONS']
                for conn in conns:
                    new_p = deepcopy(p)
                    for k, v in conn.items():
                        new_p[k] = v
                    p_list.append(new_p)
            else:
                p_list.append(p)
            
            profiles.extend(p_list)
        
        return profiles
    
    def _retrieve_firewall_profile_without_domain(self, **params):
        dns_domain = params.get('DNSDomain')
        profiles_key = params.get('profilesKey')
        signatures_key = params.get('signaturesKey')
        
        if not dns_domain or not profiles_key or not signatures_key:
            return None
        
        profile_guid = None
        
        # Check both Managed and Unmanaged signatures
        for sig_type in ['Managed/', 'Unmanaged/']:
            sigs = signatures_key.get(sig_type, {})
            if isinstance(sigs, dict):
                for sig in sigs.values():
                    if isinstance(sig, dict) and sig.get('/FirstNetwork') == dns_domain:
                        profile_guid = sig.get('/ProfileGuid')
                        break
            if profile_guid:
                break
        
        if not profile_guid:
            return None
        
        profile_key = f"{profile_guid}/"
        if profile_key not in profiles_key:
            return None
        
        return profiles_key[profile_key]
    
    def _retrieve_firewall_profile_with_domain(self, **params):
        profile_name = params.get('profileName')
        profiles_key = params.get('profilesKey')
        
        if not profile_name or not profiles_key:
            return None
        
        for p in profiles_key.values():
            if isinstance(p, dict) and p.get('/ProfileName') == profile_name:
                return p
        
        return None