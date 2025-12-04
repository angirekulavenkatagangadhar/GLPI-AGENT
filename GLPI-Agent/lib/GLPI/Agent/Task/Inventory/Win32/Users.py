# glpi_agent/task/inventory/win32/users.py

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools.Win32 import get_wmi_objects, get_registry_value
from glpi_agent.tools.win32.users import get_users


class Users(InventoryModule):
    """Windows Users inventory module."""
    
    @staticmethod
    def other_categories():
        return ['local_user', 'local_group']
    
    @staticmethod
    def category():
        return "user"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        logger = params.get('logger')
        no_category = params.get('no_category', {})
        
        if not no_category.get('local_user'):
            for user in get_users(localusers=True, logger=logger):
                inventory.add_entry(
                    section='LOCAL_USERS',
                    entry={k: user[k] for k in ['NAME', 'ID'] if k in user}
                )
        
        if not no_category.get('local_group'):
            for group in self._get_local_groups(logger=logger):
                inventory.add_entry(
                    section='LOCAL_GROUPS',
                    entry=group
                )
        
        # Handles seen users without being case sensitive
        seen = set()
        
        last_logged_user = self._get_last_user(logger=logger)
        if last_logged_user:
            # Include last logged user as usual computer user
            if isinstance(last_logged_user, dict):
                fullname = last_logged_user.pop('_fullname', None)
                if fullname:
                    fullname = fullname.lower()
                else:
                    fullname = f"{last_logged_user['LOGIN'].lower()}@{last_logged_user['DOMAIN'].lower()}"
                
                if fullname not in seen:
                    seen.add(fullname)
                    inventory.add_entry(
                        section='USERS',
                        entry=last_logged_user
                    )
                
                # Obsolete in specs, to be removed with 3.0
                inventory.set_hardware({
                    'LASTLOGGEDUSER': last_logged_user['LOGIN']
                })
            else:
                # Obsolete in specs, to be removed with 3.0
                inventory.set_hardware({
                    'LASTLOGGEDUSER': last_logged_user
                })
        
        for user in self._get_logged_users(logger=logger):
            fullname = f"{user['LOGIN'].lower()}@{user['DOMAIN'].lower()}"
            if fullname not in seen:
                seen.add(fullname)
                inventory.add_entry(
                    section='USERS',
                    entry=user
                )
    
    def _get_local_groups(self, **params):
        query = (
            "SELECT * FROM Win32_Group "
            "WHERE LocalAccount='True'"
        )
        
        groups = []
        
        for obj in get_wmi_objects(
            moniker='winmgmts:\\\\.\\root\\CIMV2',
            query=query,
            properties=['Name', 'SID'],
            **params
        ):
            # Replace "right single quotation mark" by "simple quote" to avoid "Wide character in print" error
            name = obj.get('Name', '')
            name = name.replace('\u2019', "'")
            
            group = {
                'NAME': name,
                'ID': obj.get('SID'),
            }
            groups.append(group)
        
        return groups
    
    def _get_logged_users(self, **params):
        query = (
            "SELECT * FROM Win32_Process"
            " WHERE ExecutablePath IS NOT NULL"
            " AND ExecutablePath LIKE '%\\\\Explorer.exe'"
        )
        
        users = []
        seen = set()
        
        for user in get_wmi_objects(
            moniker='winmgmts:\\\\.\\root\\CIMV2',
            query=query,
            method='GetOwner',
            params=['User', 'Domain'],
            User=['string', ''],
            Domain=['string', ''],
            selector='Handle',  # For winrm support
            binds={
                'User': 'LOGIN',
                'Domain': 'DOMAIN'
            },
            **params
        ):
            login = user.get('LOGIN')
            if not login or login in seen:
                continue
            
            seen.add(login)
            users.append(user)
        
        return users
    
    def _get_last_user(self, **params):
        system_objs = get_wmi_objects(
            class_name='Win32_ComputerSystem',
            properties=['Name', 'UserName'],
            **params
        )
        
        system = system_objs[0] if system_objs else None
        
        if system and system.get('Name') and system.get('UserName'):
            user = {
                'DOMAIN': system['UserName'],
                'LOGIN': system['Name']
            }
            if '\\' in user['DOMAIN']:
                parts = user['DOMAIN'].split('\\', 1)
                if parts[0] != '.':
                    user['DOMAIN'] = parts[0]
                user['LOGIN'] = parts[1]
                
                # Handle AzureAD case
                if user.get('DOMAIN') == 'AzureAD':
                    upn = self._get_last_logged_azure_ad_user_upn(name=user['LOGIN'], **params)
                    if upn and '@' in upn:
                        login_part, domain_part = upn.split('@', 1)
                        user['_fullname'] = f"{user['LOGIN']}@AzureAD"
                        user['LOGIN'] = login_part
                        user['DOMAIN'] = domain_part
            
            return user
        
        # Try registry values
        user = None
        registry_paths = [
            'SOFTWARE/Microsoft/Windows/CurrentVersion/Authentication/LogonUI/LastLoggedOnSAMUser',
            'SOFTWARE/Microsoft/Windows/CurrentVersion/Authentication/LogonUI/LastLoggedOnUser',
            'SOFTWARE/Microsoft/Windows NT/CurrentVersion/Winlogon/DefaultUserName',
            'SOFTWARE/Microsoft/Windows NT/CurrentVersion/Winlogon/LastUsedUsername'
        ]
        
        for path in registry_paths:
            user = get_registry_value(path=f"HKEY_LOCAL_MACHINE/{path}", **params)
            if user:
                break
        
        if not user:
            return None
        
        # LastLoggedOnSAMUser becomes the mandatory value to detect last logged on user
        if '\\' in user:
            domain, login = user.split('\\', 1)
            user = {
                'DOMAIN': domain,
                'LOGIN': login
            }
            
            # Update domain if just a dot
            if user['DOMAIN'] == '.' and system and system.get('Name'):
                user['DOMAIN'] = system['Name']
            
            if user['DOMAIN'] == '.':
                useraccount_list = get_users(login=user['LOGIN'], **params)
                if useraccount_list:
                    useraccount = useraccount_list[0]
                    if useraccount.get('DOMAIN'):
                        user['DOMAIN'] = useraccount['DOMAIN']
            elif user['DOMAIN'] == 'AzureAD':
                # Handle AzureAD case
                upn = self._get_last_logged_azure_ad_user_upn(name=user['LOGIN'], **params)
                if upn and '@' in upn:
                    login_part, domain_part = upn.split('@', 1)
                    user['_fullname'] = f"{user['LOGIN']}@AzureAD"
                    user['LOGIN'] = login_part
                    user['DOMAIN'] = domain_part
        
        return user
    
    def _get_last_logged_azure_ad_user_upn(self, **params):
        name = params.get('name')
        
        sid = get_registry_value(
            path="HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft/Windows/CurrentVersion/Authentication/LogonUI/LastLoggedOnUserSID",
            **params
        )
        if not sid:
            return None
        
        samname = get_registry_value(
            path=f"HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft/IdentityStore/Cache/{sid}/IdentityCache/{sid}/SAMName",
            **params
        )
        if not samname or not name or samname != name:
            return None
        
        return get_registry_value(
            path=f"HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft/IdentityStore/Cache/{sid}/IdentityCache/{sid}/UserName",
            **params
        )