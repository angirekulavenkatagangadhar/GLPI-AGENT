# glpi_agent/task/inventory/win32/softwares.py

import re
from datetime import datetime

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools import can_run, hex2dec
from GLPI.Agent.Tools.Win32 import (
    get_wmi_objects, get_registry_key, get_registry_key_value,
    is64bit, run_powershell, load_user_hive, cleanup_privileges
)
from glpi_agent.tools.win32.constants import (
    CATEGORY_APPLICATION, CATEGORY_SYSTEM_COMPONENT, CATEGORY_UPDATE,
    CATEGORY_SECURITY_UPDATE, CATEGORY_HOTFIX
)

# Module-level variables
_seen = {}
_remote_inventory = None


class Softwares(InventoryModule):
    """Windows Softwares inventory module."""
    
    @staticmethod
    def category():
        return "software"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        global _seen, _remote_inventory
        
        inventory = params.get('inventory')
        logger = params.get('logger')
        
        _remote_inventory = inventory.get_remote()
        
        is_64bit = is64bit()
        
        softwares64 = self._get_softwares_list(is64bit=is_64bit) or []
        for software in softwares64:
            self._add_software(inventory=inventory, entry=software)
        
        self._process_msie(inventory=inventory, is64bit=is_64bit)
        
        userprofiles = None
        if params.get('scan_profiles'):
            try:
                from glpi_agent.tools.win32.users import get_system_user_profiles
                userprofiles = get_system_user_profiles()
                self._load_user_software(
                    inventory=inventory,
                    profiles=userprofiles,
                    is64bit=is_64bit,
                    logger=logger
                )
            except ImportError:
                pass
        else:
            if logger:
                logger.debug(
                    "'scan-profiles' configuration parameter disabled, "
                    "ignoring software in user profiles"
                )
        
        if is_64bit:
            softwares32 = self._get_softwares_list(
                path="HKEY_LOCAL_MACHINE/SOFTWARE/Wow6432Node/Microsoft/Windows/CurrentVersion/Uninstall",
                is64bit=False
            ) or []
            for software in softwares32:
                self._add_software(inventory=inventory, entry=software)
            
            self._process_msie(inventory=inventory, is64bit=False)
            
            if params.get('scan_profiles') and userprofiles:
                self._load_user_software(
                    inventory=inventory,
                    profiles=userprofiles,
                    is64bit=False,
                    logger=logger
                )
        
        # Cleanup privileges if we had to load user profiles
        if params.get('scan_profiles'):
            cleanup_privileges()
        
        hotfixes = self._get_hotfixes_list(is64bit=is_64bit)
        for hotfix in hotfixes:
            # skip fixes already found in generic software list
            if hotfix['NAME'] not in _seen:
                self._add_software(inventory=inventory, entry=hotfix)
        
        # Lookup for UWP/Windows Store packages
        os_objs = get_wmi_objects(
            class_name='Win32_OperatingSystem',
            properties=['Version']
        )
        
        if os_objs and os_objs[0].get('Version'):
            match = re.match(r'^(\d+\.\d+)', os_objs[0]['Version'])
            if match:
                osversion = float(match.group(1))
                if osversion > 6.1:
                    packages = self._get_appx_packages(logger=logger)
                    if packages:
                        for package in packages:
                            self._add_software(inventory=inventory, entry=package)
        
        # Collect software from Program Files directories (portable apps, etc.)
        program_files_software = self._get_program_files_software(logger=logger, is64bit=is_64bit)
        if program_files_software:
            for software in program_files_software:
                self._add_software(inventory=inventory, entry=software)
        
        # Collect from additional registry locations
        additional_software = self._get_additional_registry_software(is64bit=is_64bit, logger=logger)
        if additional_software:
            for software in additional_software:
                self._add_software(inventory=inventory, entry=software)
        
        # Reset seen hash
        _seen = {}
    
    def _load_user_software(self, **params):
        profiles = params.get('profiles')
        if not profiles:
            return
        
        inventory = params.get('inventory')
        is_64bit = params.get('is64bit')
        logger = params.get('logger')
        userhives = []
        
        for profile in profiles:
            sid = profile.get('SID')
            if not sid:
                continue
            
            match = re.search(r'-(\d+)$', sid)
            userid = match.group(1) if match else None
            
            if not profile.get('LOADED'):
                ntuserdat = f"{profile['PATH']}/NTUSER.DAT"
                userhives.append(load_user_hive(sid=sid, file=ntuserdat))
            
            try:
                from glpi_agent.tools.win32.users import get_profile_username
                username = get_profile_username(profile)
            except (ImportError, AttributeError):
                username = None
            
            if not username:
                continue
            
            profile_soft = f"HKEY_USERS/{sid}/SOFTWARE/"
            if is64bit() and not is_64bit:
                profile_soft += "Wow6432Node/Microsoft/Windows/CurrentVersion/Uninstall"
            else:
                profile_soft += "Microsoft/Windows/CurrentVersion/Uninstall"
            
            softwares = self._get_softwares_list(
                path=profile_soft,
                is64bit=is_64bit,
                userid=userid,
                username=username
            ) or []
            
            if not softwares:
                continue
            
            if logger:
                logger.debug2(f'_loadUserSoftwareFromHKey_Users({sid}) : add of {len(softwares)} softwares in inventory')
            
            for software in softwares:
                self._add_software(inventory=inventory, entry=software)
    
    def _date_format(self, date):
        if not date:
            return None
        
        # YYYYMDD or YYYYMMDD format
        match = re.match(r'^(\d{4})(\d{1})(\d{2})$', str(date))
        if match:
            return f"{match.group(3)}/0{match.group(2)}/{match.group(1)}"
        
        match = re.match(r'^(\d{4})(\d{2})(\d{2})$', str(date))
        if match:
            return f"{match.group(3)}/{match.group(2)}/{match.group(1)}"
        
        # Re-order "M/D/YYYY" as "DD/MM/YYYY"
        match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', str(date))
        if match:
            return f"{int(match.group(2)):02d}/{int(match.group(1)):02d}/{int(match.group(3)):04d}"
        
        return None
    
    def _key_last_write_date_string(self, key):
        if _remote_inventory:
            return None
        
        # This would require Win32::TieRegistry functionality
        # For now, return None as it's Windows-specific and complex
        return None
    
    def _get_softwares_list(self, **params):
        softwares = get_registry_key(
            path="HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft/Windows/CurrentVersion/Uninstall",
            required=[
                'DisplayName', 'Comments', 'HelpLink', 'ReleaseType',
                'DisplayVersion', 'Publisher', 'URLInfoAbout', 
                'UninstallString', 'InstallDate', 'MinorVersion',
                'MajorVersion', 'NoRemove', 'SystemComponent'
            ],
            **params
        )
        
        if not softwares:
            return []
        
        mapping = {
            'NAME': 'DisplayName',
            'COMMENTS': 'Comments',
            'HELPLINK': 'HelpLink',
            'RELEASE_TYPE': 'ReleaseType',
            'VERSION': 'DisplayVersion',
            'PUBLISHER': 'Publisher',
            'URL_INFO_ABOUT': 'URLInfoAbout',
            'UNINSTALL_STRING': 'UninstallString',
        }
        
        # Get subkeys
        subkeys = [k.rstrip('/') for k in softwares.keys() if k.endswith('/')]
        if not subkeys:
            return []
        
        result = []
        
        for guid in sorted(subkeys):
            data = softwares.get(f"{guid}/")
            if not data:
                continue
            
            # Check if has more than 1 value
            value_count = len([k for k in data.keys() if k.startswith('/')])
            if value_count <= 1:
                continue
            
            software = {
                'FROM': 'registry',
                'NAME': guid,
                'INSTALLDATE': self._date_format(data.get('/InstallDate')),
                'VERSION_MINOR': hex2dec(data.get('/MinorVersion')),
                'VERSION_MAJOR': hex2dec(data.get('/MajorVersion')),
                'NO_REMOVE': hex2dec(data.get('/NoRemove')),
                'ARCH': 'x86_64' if params.get('is64bit') else 'i586',
                'GUID': guid,
            }
            
            sys_comp = data.get('/SystemComponent')
            if sys_comp and hex2dec(sys_comp):
                software['SYSTEM_CATEGORY'] = CATEGORY_SYSTEM_COMPONENT
            else:
                software['SYSTEM_CATEGORY'] = CATEGORY_APPLICATION
            
            for key, reg_key in mapping.items():
                value = get_registry_key_value(data, reg_key)
                if value:
                    software[key] = value
            
            if params.get('userid'):
                software['USERID'] = params['userid']
            if params.get('username'):
                software['USERNAME'] = params['username']
            
            # Workaround for #415
            if software.get('VERSION'):
                software['VERSION'] = re.sub(r'[\000-\037].*', '', software['VERSION'])
            
            # Set install date to last registry key update time
            if not software.get('INSTALLDATE'):
                installdate = self._date_format(self._key_last_write_date_string(data))
                if installdate:
                    software['INSTALLDATE'] = installdate
            
            # SQL Server handling
            if software.get('NAME'):
                match = re.match(r'^(SQL Server.*)(\sDatabase Engine Services)', software['NAME'])
                if match:
                    sql_edition = self._get_sql_edition(softwareversion=software.get('VERSION'))
                    if sql_edition:
                        software['NAME'] = f"{match.group(1)} {sql_edition}{match.group(2)}"
                else:
                    match = re.match(r'^(Microsoft SQL Server 200[0-9])$', software['NAME'])
                    if match and software.get('VERSION'):
                        sql_edition = self._get_sql_edition(softwareversion=software['VERSION'])
                        if sql_edition:
                            software['NAME'] = f"{match.group(1)} {sql_edition}"
            
            result.append(software)
        
        return result
    
    def _get_hotfixes_list(self, **params):
        hotfixes = []
        
        for obj in get_wmi_objects(
            class_name='Win32_QuickFixEngineering',
            properties=['HotFixID', 'Description', 'InstalledOn']
        ):
            release_type = None
            description = obj.get('Description', '')
            
            if description:
                match = re.match(r'^(Security Update|Hotfix|Update)', description)
                if match:
                    release_type = match.group(1)
            
            if not release_type:
                system_category = CATEGORY_UPDATE
            elif 'Security Update' in release_type:
                system_category = CATEGORY_SECURITY_UPDATE
            elif 'Hotfix' in release_type:
                system_category = CATEGORY_HOTFIX
            else:
                system_category = CATEGORY_UPDATE
            
            hotfix_id = obj.get('HotFixID', '')
            if not re.match(r'KB(\d{4,10})', hotfix_id, re.IGNORECASE):
                continue
            
            hotfixes.append({
                'NAME': hotfix_id,
                'COMMENTS': description,
                'INSTALLDATE': self._date_format(obj.get('InstalledOn')),
                'FROM': 'WMI',
                'RELEASE_TYPE': release_type,
                'ARCH': 'x86_64' if params.get('is64bit') else 'i586',
                'SYSTEM_CATEGORY': system_category
            })
        
        return hotfixes
    
    def _add_software(self, **params):
        global _seen
        
        entry = params['entry']
        
        # avoid duplicates
        name = entry.get('NAME')
        arch = entry.get('ARCH')
        version = entry.get('VERSION', '_undef_')
        
        if name not in _seen:
            _seen[name] = {}
        if arch not in _seen[name]:
            _seen[name][arch] = {}
        if version in _seen[name][arch]:
            return
        
        _seen[name][arch][version] = True
        params['inventory'].add_entry(section='SOFTWARES', entry=entry)
    
    def _process_msie(self, **params):
        name = "Internet Explorer (64bit)" if params.get('is64bit') else "Internet Explorer"
        
        if is64bit() and not params.get('is64bit'):
            path = "HKEY_LOCAL_MACHINE/SOFTWARE/Wow6432Node/Microsoft/Internet Explorer"
        else:
            path = "HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft/Internet Explorer"
        
        installed_key = get_registry_key(
            path=path,
            required=['svcVersion', 'Version'],
            maxdepth=0
        )
        
        if not installed_key:
            return
        
        version = installed_key.get('/svcVersion') or installed_key.get('/Version')
        if not version:
            return
        
        self._add_software(
            inventory=params['inventory'],
            entry={
                'FROM': 'registry',
                'ARCH': 'x86_64' if params.get('is64bit') else 'i586',
                'NAME': name,
                'VERSION': version,
                'PUBLISHER': 'Microsoft Corporation',
                'INSTALLDATE': self._date_format(self._key_last_write_date_string(installed_key))
            }
        )
    
    def _get_sql_edition(self, **params):
        software_version = params.get('softwareversion')
        
        instances_list = get_registry_key(
            path="HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft/Microsoft SQL Server/Instance Names/SQL"
        )
        
        if not instances_list:
            return None
        
        for instance_name, instance_value in instances_list.items():
            if instance_name.startswith('/'):
                continue
            
            edition = self._get_sql_instances_versions(
                SOFTVERSION=software_version,
                VALUE=instance_value
            )
            if edition:
                return edition
        
        return None
    
    def _get_sql_instances_versions(self, **params):
        software_version = params.get('SOFTVERSION')
        instance_value = params.get('VALUE')
        
        instance_versions = get_registry_key(
            path=f"HKEY_LOCAL_MACHINE/SOFTWARE/Microsoft/Microsoft SQL Server/{instance_value}/Setup",
            required=['Version', 'Edition']
        )
        
        if not instance_versions or not instance_versions.get('/Version'):
            return None
        
        if instance_versions['/Version'] != software_version:
            return None
        
        return instance_versions.get('/Edition')
    
    def _get_appx_packages(self, **params):
        """Get UWP/Windows Store AppX packages"""
        if not can_run('powershell'):
            return None
        
        logger = params.get('logger')
        
        try:
            # Use PowerShell to get all AppX packages
            ps_script = '''
            $packages = @()
            try {
                # Get all AppX packages for all users
                $allPackages = Get-AppxPackage -AllUsers -ErrorAction SilentlyContinue
                foreach ($pkg in $allPackages) {
                    $packages += [PSCustomObject]@{
                        Name = $pkg.Name
                        Publisher = $pkg.Publisher
                        Version = $pkg.Version.ToString()
                        InstallDate = if ($pkg.InstallDate) { $pkg.InstallDate.ToString('yyyyMMdd') } else { $null }
                        Architecture = $pkg.Architecture
                    }
                }
                
                # Also get provisioned packages
                $provisioned = Get-AppxProvisionedPackage -Online -ErrorAction SilentlyContinue
                foreach ($pkg in $provisioned) {
                    $packages += [PSCustomObject]@{
                        Name = $pkg.DisplayName
                        Publisher = $pkg.Publisher
                        Version = $pkg.Version.ToString()
                        InstallDate = $null
                        Architecture = $pkg.Architecture
                    }
                }
            } catch {
                # Fallback: try Get-AppxPackage without -AllUsers
                try {
                    $allPackages = Get-AppxPackage -ErrorAction SilentlyContinue
                    foreach ($pkg in $allPackages) {
                        $packages += [PSCustomObject]@{
                            Name = $pkg.Name
                            Publisher = $pkg.Publisher
                            Version = $pkg.Version.ToString()
                            InstallDate = if ($pkg.InstallDate) { $pkg.InstallDate.ToString('yyyyMMdd') } else { $null }
                            Architecture = $pkg.Architecture
                        }
                    }
                } catch { }
            }
            $packages | ConvertTo-Json -Depth 10
            '''
            
            # Run PowerShell and parse JSON output
            import subprocess
            import json as json_lib
            
            result = subprocess.run(
                ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', f"{ps_script}"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0 or not result.stdout.strip():
                return None
            
            try:
                json_output = json_lib.loads(result.stdout.strip())
            except json_lib.JSONDecodeError:
                if logger:
                    logger.debug("Failed to parse AppX packages JSON output")
                return None
            
            packages = []
            if isinstance(json_output, list):
                for pkg in json_output:
                    if isinstance(pkg, dict) and pkg.get('Name'):
                        packages.append({
                            'NAME': pkg.get('Name', ''),
                            'PUBLISHER': pkg.get('Publisher', ''),
                            'VERSION': pkg.get('Version', ''),
                            'INSTALLDATE': self._date_format(pkg.get('InstallDate')),
                            'ARCH': pkg.get('Architecture', 'x86_64'),
                            'FROM': 'AppX',
                            'SYSTEM_CATEGORY': CATEGORY_APPLICATION
                        })
            elif isinstance(json_output, dict) and json_output.get('Name'):
                pkg = json_output
                packages.append({
                    'NAME': pkg.get('Name', ''),
                    'PUBLISHER': pkg.get('Publisher', ''),
                    'VERSION': pkg.get('Version', ''),
                    'INSTALLDATE': self._date_format(pkg.get('InstallDate')),
                    'ARCH': pkg.get('Architecture', 'x86_64'),
                    'FROM': 'AppX',
                    'SYSTEM_CATEGORY': CATEGORY_APPLICATION
                })
            
            if logger and packages:
                logger.debug(f"Found {len(packages)} AppX/UWP packages")
            
            return packages
            
        except Exception as e:
            if logger:
                logger.debug(f"Error collecting AppX packages: {e}")
            return None
    
    def _get_program_files_software(self, **params):
        """Get software from Program Files directories (for portable apps and non-registry software)"""
        logger = params.get('logger')
        is_64bit = params.get('is64bit', True)
        
        if not can_run('powershell'):
            return None
        
        try:
            ps_script = '''
            $software = @()
            $programPaths = @()
            
            # Add standard Program Files paths
            if (Test-Path "$env:ProgramFiles") {
                $programPaths += "$env:ProgramFiles"
            }
            if (Test-Path "${env:ProgramFiles(x86)}") {
                $programPaths += "${env:ProgramFiles(x86)}"
            }
            if (Test-Path "$env:ProgramData") {
                $programPaths += "$env:ProgramData"
            }
            
            foreach ($path in $programPaths) {
                try {
                    $dirs = Get-ChildItem -Path $path -Directory -ErrorAction SilentlyContinue | Where-Object {
                        # Skip common system directories
                        $_.Name -notmatch '^(Windows|Common Files|Internet Explorer|Windows Defender|Windows Mail|Windows Media Player|Windows NT|Windows Photo Viewer|WindowsPowerShell|Microsoft|Intel|AMD|NVIDIA)$'
                    }
                    
                    foreach ($dir in $dirs) {
                        # Look for executable files that might indicate software
                        $exeFiles = Get-ChildItem -Path $dir.FullName -Filter "*.exe" -Recurse -Depth 2 -ErrorAction SilentlyContinue | 
                            Where-Object { $_.Name -notlike "*uninstall*" -and $_.Name -notlike "*setup*" -and $_.Name -notlike "*install*" }
                        
                        if ($exeFiles) {
                            $mainExe = $exeFiles | Select-Object -First 1
                            $versionInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($mainExe.FullName)
                            
                            $name = if ($versionInfo.FileDescription -and $versionInfo.FileDescription.Trim()) {
                                $versionInfo.FileDescription
                            } elseif ($versionInfo.ProductName -and $versionInfo.ProductName.Trim()) {
                                $versionInfo.ProductName
                            } else {
                                $dir.Name
                            }
                            
                            $version = if ($versionInfo.FileVersion -and $versionInfo.FileVersion.Trim()) {
                                $versionInfo.FileVersion
                            } elseif ($versionInfo.ProductVersion -and $versionInfo.ProductVersion.Trim()) {
                                $versionInfo.ProductVersion
                            } else {
                                $null
                            }
                            
                            $publisher = if ($versionInfo.CompanyName -and $versionInfo.CompanyName.Trim()) {
                                $versionInfo.CompanyName
                            } else {
                                $null
                            }
                            
                            # Only add if we have a meaningful name and it's not already in registry
                            if ($name -and $name -ne $dir.Name -and $name.Length -gt 2) {
                                $software += [PSCustomObject]@{
                                    Name = $name
                                    Version = $version
                                    Publisher = $publisher
                                    InstallPath = $dir.FullName
                                    InstallDate = (Get-Item $dir.FullName).CreationTime.ToString('yyyyMMdd')
                                }
                            }
                        }
                    }
                } catch { }
            }
            
            $software | Select-Object -Unique -Property Name,Version,Publisher,InstallPath,InstallDate | ConvertTo-Json -Depth 10
            '''
            
            # Run PowerShell and parse JSON output
            import subprocess
            import json as json_lib
            
            result = subprocess.run(
                ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', f"{ps_script}"],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0 or not result.stdout.strip():
                return None
            
            try:
                json_output = json_lib.loads(result.stdout.strip())
            except json_lib.JSONDecodeError:
                if logger:
                    logger.debug("Failed to parse Program Files software JSON output")
                return None
            
            software_list = []
            results = json_output if isinstance(json_output, list) else [json_output] if json_output else []
            
            for item in results:
                if isinstance(item, dict) and item.get('Name'):
                    software_list.append({
                        'NAME': item.get('Name', ''),
                        'VERSION': item.get('Version', ''),
                        'PUBLISHER': item.get('Publisher', ''),
                        'INSTALLDATE': self._date_format(item.get('InstallDate')),
                        'ARCH': 'x86_64' if is_64bit else 'i586',
                        'FROM': 'ProgramFiles',
                        'SYSTEM_CATEGORY': CATEGORY_APPLICATION,
                        'COMMENTS': f"Found in: {item.get('InstallPath', '')}"
                    })
            
            if logger and software_list:
                logger.debug(f"Found {len(software_list)} software items from Program Files")
            
            return software_list
            
        except Exception as e:
            if logger:
                logger.debug(f"Error collecting Program Files software: {e}")
            return None
    
    def _get_additional_registry_software(self, **params):
        """Get software from additional registry locations"""
        is_64bit = params.get('is64bit', True)
        logger = params.get('logger')
        
        additional_paths = []
        
        # Add user-specific registry paths if we can
        try:
            # HKEY_CURRENT_USER software (for current user)
            if is_64bit:
                additional_paths.append("HKEY_CURRENT_USER/SOFTWARE/Microsoft/Windows/CurrentVersion/Uninstall")
                additional_paths.append("HKEY_CURRENT_USER/SOFTWARE/Wow6432Node/Microsoft/Windows/CurrentVersion/Uninstall")
            else:
                additional_paths.append("HKEY_CURRENT_USER/SOFTWARE/Microsoft/Windows/CurrentVersion/Uninstall")
        except:
            pass
        
        software_list = []
        
        for path in additional_paths:
            try:
                softwares = self._get_softwares_list(
                    path=path,
                    is64bit=is_64bit
                ) or []
                software_list.extend(softwares)
            except Exception as e:
                if logger:
                    logger.debug(f"Error reading registry path {path}: {e}")
                continue
        
        if logger and software_list:
            logger.debug(f"Found {len(software_list)} additional software items from registry")
        
        return software_list