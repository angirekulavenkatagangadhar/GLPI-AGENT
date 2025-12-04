# glpi_agent/task/inventory/win32/antivirus.py

import os
import re
import time
import json
from pathlib import Path

from GLPI.Agent.Task.Inventory.Module import InventoryModule
from GLPI.Agent.Tools import (
    can_run, has_file, has_folder, get_all_lines, get_first_line,
    get_first_match, get_directory_handle, get_sanitized_string, 
    dec2hex, hex2dec, first
)
from GLPI.Agent.Tools.Win32 import (
    get_wmi_objects, get_registry_key, get_registry_key_value, 
    is64bit, get_services
)


class AntiVirus(InventoryModule):
    """Windows AntiVirus inventory module."""
    
    @staticmethod
    def category():
        return "antivirus"
    
    def is_enabled(self, **params):
        return True
    
    def do_inventory(self, **params):
        inventory = params.get('inventory')
        logger = params.get('logger')
        seen = {}
        found_enabled = 0
        
        # Doesn't work on Win2003 Server
        # On Win7, we need to use SecurityCenter2
        for instance in ['SecurityCenter', 'SecurityCenter2']:
            moniker = f"winmgmts:{{impersonationLevel=impersonate,(security)}}!//./root/{instance}"
            
            for obj in get_wmi_objects(
                moniker=moniker,
                class_name="AntiVirusProduct",
                properties=[
                    'companyName', 'displayName', 'instanceGuid',
                    'onAccessScanningEnabled', 'productUptoDate',
                    'versionNumber', 'productState'
                ]
            ):
                if not obj:
                    continue
                
                antivirus = {
                    'COMPANY': obj.get('companyName'),
                    'NAME': obj.get('displayName'),
                    'GUID': obj.get('instanceGuid'),
                    'VERSION': obj.get('versionNumber'),
                    'ENABLED': obj.get('onAccessScanningEnabled'),
                    'UPTODATE': obj.get('productUptoDate')
                }
                
                if obj.get('productState'):
                    hex_state = dec2hex(obj['productState'])
                    if logger:
                        logger.debug(f"Found {antivirus['NAME']} (state={hex_state})")
                    
                    # See http://neophob.com/2010/03/wmi-query-windows-securitycenter2/
                    if len(hex_state) >= 4:
                        enabled = hex_state[-4:-2]
                        uptodate = hex_state[-2:]
                        antivirus['ENABLED'] = 1 if enabled[0] == '1' else 0
                        antivirus['UPTODATE'] = 1 if uptodate == '00' else 0
                        if antivirus['ENABLED']:
                            found_enabled += 1
                else:
                    if logger:
                        logger.debug(f"Found {antivirus['NAME']}")
                
                # Also support WMI access to Windows Defender
                if not antivirus.get('VERSION') and antivirus.get('NAME') and 'Windows Defender' in antivirus['NAME']:
                    self._set_win_defender_infos(antivirus)
                    if antivirus.get('ENABLED'):
                        found_enabled += 1
                
                # Try to get version from software installation in registry
                if not antivirus.get('VERSION') or not antivirus.get('COMPANY'):
                    registry = self._get_antivirus_uninstall(antivirus.get('NAME'))
                    if registry:
                        if not antivirus.get('VERSION'):
                            version = get_registry_key_value(registry, "DisplayVersion")
                            if version:
                                antivirus['VERSION'] = version
                        if not antivirus.get('COMPANY'):
                            company = get_registry_key_value(registry, "Publisher")
                            if company:
                                antivirus['COMPANY'] = company
                
                # Check for other product data for update
                name = antivirus.get('NAME', '')
                if 'McAfee' in name:
                    self._set_mcafee_infos(antivirus, logger)
                elif 'Kaspersky' in name:
                    self._set_kaspersky_infos(antivirus)
                elif 'ESET' in name:
                    self._set_eset_infos(antivirus)
                elif 'Avira' in name:
                    self._set_avira_infos(antivirus)
                elif 'Security Essentials' in name:
                    self._set_ms_essentials_infos(antivirus)
                elif 'F-Secure' in name:
                    self._set_fsecure_infos(antivirus)
                elif 'Bitdefender' in name:
                    self._set_bitdefender_infos(antivirus, logger, "C:\\Program Files\\Bitdefender\\Endpoint Security\\product.console.exe")
                elif 'Norton' in name or 'Symantec' in name:
                    self._set_norton_infos(antivirus)
                elif 'Trend Micro Security Agent' in name:
                    self._set_trend_micro_security_agent_infos(antivirus)
                elif 'Cortex XDR' in name:
                    self._set_cortex_infos(antivirus, logger, "C:\\Program Files\\Palo Alto Networks\\Traps\\cytool.exe")
                elif 'CrowdStrike Falcon Sensor' in name:
                    self._set_crowdstrike_infos(antivirus, logger, "C:\\Program Files\\CrowdStrike\\CSSensorSettings.exe")
                
                # Avoid duplicates
                av_name = antivirus.get('NAME', '')
                av_version = antivirus.get('VERSION', '_undef_')
                if av_name not in seen:
                    seen[av_name] = {}
                if av_version in seen[av_name]:
                    continue
                seen[av_name][av_version] = True
                
                inventory.add_entry(
                    section='ANTIVIRUS',
                    entry=antivirus
                )
                
                if logger:
                    version_str = f" v{antivirus['VERSION']}" if antivirus.get('VERSION') else ""
                    logger.debug2(f"Added {antivirus['NAME']}{version_str}")
        
        # Try to add AV support on Windows server where no active AV is detected via WMI
        if not found_enabled:
            services = get_services(logger=logger)
            
            supports = [
                {
                    'name': "Windows Defender",
                    'service': "WinDefend",
                    'func': self._set_win_defender_infos,
                },
                {
                    'name': "Cortex XDR",
                    'service': "cyserver",
                    'path': "C:\\Program Files\\Palo Alto Networks\\Traps",
                    'command': "cytool.exe",
                    'func': self._set_cortex_infos,
                },
                {
                    'name': "Bitdefender Endpoint Security",
                    'service': "EPSecurityService",
                    'path': "C:\\Program Files\\Bitdefender\\Endpoint Security",
                    'command': "product.console.exe",
                    'func': self._set_bitdefender_infos,
                },
                {
                    'name': "Trellix",
                    'service': "masvc",
                    'path': [
                        "C:\\Program Files\\McAfee\\Agent",
                        "C:\\Program Files (x86)\\McAfee\\Common Framework",
                    ],
                    'command': "CmdAgent.exe",
                    'func': self._set_mcafee_infos,
                },
                {
                    'name': "SentinelOne",
                    'service': "SentinelAgent",
                    'command': "SentinelCtl.exe",
                    'func': self._set_sentinelone_infos,
                },
                {
                    'name': "CrowdStrike Falcon Sensor",
                    'service': "csagent",
                    'path': "C:\\Program Files\\CrowdStrike",
                    'command': "CSSensorSettings.exe",
                    'func': self._set_crowdstrike_infos,
                },
            ]
            
            for support in supports:
                service = services.get(support['service'])
                if not service:
                    continue
                
                antivirus = {}
                antivirus['NAME'] = support.get('name') or service.get('NAME')
                antivirus['ENABLED'] = 1 if service.get('STATUS') and 'running' in service['STATUS'].lower() else 0
                
                if support.get('command'):
                    paths = []
                    if service.get('PATHNAME'):
                        # First use pathname extracted from service PATHNAME
                        if service['PATHNAME'].startswith('"'):
                            match = re.match(r'^"([^"]+)"', service['PATHNAME'])
                        else:
                            match = re.match(r'^(\S+)', service['PATHNAME'])
                        
                        if match:
                            path = match.group(1)
                            # Remove filename part
                            if not has_folder(path) and '\\' in path:
                                path = path.rsplit('\\', 1)[0]
                            if path:
                                paths.append(path)
                    
                    if support.get('path'):
                        if isinstance(support['path'], list):
                            paths.extend(support['path'])
                        else:
                            paths.append(support['path'])
                    
                    tried = set()
                    for path in paths:
                        if path in tried:
                            continue
                        tried.add(path)
                        
                        cmd = os.path.join(path, support['command'])
                        if not can_run(cmd):
                            continue
                        
                        support['func'](antivirus, logger, cmd)
                        break
                elif support.get('func'):
                    support['func'](antivirus)
                
                # Avoid duplicates
                av_name = antivirus.get('NAME', '')
                av_version = antivirus.get('VERSION', '_undef_')
                if av_name not in seen:
                    seen[av_name] = {}
                if av_version in seen[av_name]:
                    continue
                seen[av_name][av_version] = True
                
                inventory.add_entry(
                    section='ANTIVIRUS',
                    entry=antivirus
                )
                
                if logger:
                    version_str = f" v{antivirus['VERSION']}" if antivirus.get('VERSION') else ""
                    logger.debug2(f"Added {antivirus['NAME']}{version_str}")
    
    def _get_antivirus_uninstall(self, name):
        if not name:
            return None
        
        # Cleanup name from localized chars to keep a clean regex pattern
        match = re.match(r'^([a-zA-Z0-9 ._-]+)', name)
        if not match:
            return None
        
        pattern = match.group(1)
        # Escape dot in pattern
        pattern = pattern.replace('.', '\\.')
        pattern_re = re.compile(f'^{pattern}', re.IGNORECASE)
        
        return self._get_software_registry_keys(
            'Microsoft/Windows/CurrentVersion/Uninstall',
            ['DisplayName', 'DisplayVersion', 'Publisher'],
            lambda registry: first(
                lambda v: isinstance(v, dict) and 
                         v.get('/DisplayName') and 
                         pattern_re.match(v['/DisplayName']),
                registry.values()
            )
        )
    
    def _set_win_defender_infos(self, antivirus, logger=None, command=None):
        defender = None
        # Don't try to access Windows Defender class if not enabled
        if antivirus.get('ENABLED'):
            defender_objs = get_wmi_objects(
                moniker='winmgmts://./root/microsoft/windows/defender',
                class_name="MSFT_MpComputerStatus",
                properties=['AMProductVersion', 'AntivirusEnabled', 'AntivirusSignatureVersion']
            )
            defender = defender_objs[0] if defender_objs else None
        
        if defender:
            if defender.get('AMProductVersion'):
                antivirus['VERSION'] = defender['AMProductVersion']
            if defender.get('AntivirusEnabled') and str(defender['AntivirusEnabled']).lower() in ('1', 'true'):
                antivirus['ENABLED'] = 1
            if defender.get('AntivirusSignatureVersion'):
                antivirus['BASE_VERSION'] = defender['AntivirusSignatureVersion']
        
        antivirus['COMPANY'] = "Microsoft Corporation"
        
        # Finally try registry for base version
        if not antivirus.get('BASE_VERSION'):
            defender = self._get_software_registry_keys(
                'Microsoft/Windows Defender/Signature Updates',
                ['AVSignatureVersion']
            )
            if defender and defender.get('/AVSignatureVersion'):
                antivirus['BASE_VERSION'] = defender['/AVSignatureVersion']
    
    def _set_mcafee_infos(self, antivirus, logger=None, command=None):
        if command:
            version = get_first_match(
                command=f'"{command}" /i',
                pattern=r'^Version: (.*)$',
                logger=logger
            )
            if version:
                antivirus['VERSION'] = version
            if not antivirus.get('COMPANY'):
                antivirus['COMPANY'] = "Trellix"
        
        endpoint_reg = self._get_software_registry_keys(
            'McAfee/Endpoint/ATP',
            ['enabled', 'ProductVersion', 'BuildNumber']
        )
        
        if endpoint_reg:
            version = endpoint_reg.get('ProductVersion')
            build = endpoint_reg.get('BuildNumber')
            if version and build:
                version = f"{version}.{build}"
            if version:
                antivirus['VERSION'] = version
            
            enabled = endpoint_reg.get('enabled')
            if enabled:
                antivirus['ENABLED'] = 1 if hex2dec(enabled) else 0
        
        properties = {
            'BASE_VERSION': ['AVDatVersion', 'AVDatVersionMinor'],
        }
        
        regvalues = [val for vals in properties.values() for val in vals]
        
        mcafee_reg = self._get_software_registry_keys('McAfee/AVEngine', regvalues)
        if not mcafee_reg:
            return
        
        # major.minor versions properties
        for property_name, keys in properties.items():
            major = mcafee_reg.get('/' + keys[0])
            minor = mcafee_reg.get('/' + keys[1])
            if major is not None and minor is not None:
                antivirus[property_name] = f"{hex2dec(major):04d}.{hex2dec(minor):04d}"
    
    def _set_kaspersky_infos(self, antivirus):
        regvalues = ['LastSuccessfulUpdate', 'LicKeyType', 'LicDaysTillExpiration']
        
        kaspersky_reg = self._get_software_registry_keys('KasperskyLab/protected', regvalues)
        if not kaspersky_reg:
            return
        
        found = first(
            lambda v: isinstance(v, dict) and 
                     v.get("Data/") and 
                     v["Data/"].get("/LastSuccessfulUpdate"),
            kaspersky_reg.values()
        )
        
        if found:
            lastupdate = hex2dec(found["Data/"]["/LastSuccessfulUpdate"])
            if lastupdate and lastupdate != 0xFFFFFFFF:
                import time
                date = time.localtime(lastupdate)
                # Format BASE_VERSION as YYYYMMDD
                antivirus['BASE_VERSION'] = f"{date.tm_year:04d}{date.tm_mon:02d}{date.tm_mday:02d}"
            
            # Set expiration date only if we found a licence key type
            keytype = hex2dec(found["Data/"].get("/LicKeyType"))
            if keytype:
                expiration = hex2dec(found["Data/"].get("/LicDaysTillExpiration"))
                if expiration is not None:
                    exp_time = time.time() + 86400 * expiration
                    date = time.localtime(exp_time)
                    antivirus['EXPIRATION'] = f"{date.tm_mday:02d}/{date.tm_mon:02d}/{date.tm_year:04d}"
    
    def _set_eset_infos(self, antivirus):
        eset_reg = self._get_software_registry_keys(
            'ESET/ESET Security/CurrentVersion/Info',
            ['ProductVersion', 'ScannerVersion', 'ProductName', 'AppDataDir']
        )
        if not eset_reg:
            return
        
        if not antivirus.get('VERSION'):
            if eset_reg.get('/ProductVersion'):
                antivirus['VERSION'] = eset_reg['/ProductVersion']
        
        if eset_reg.get('/ScannerVersion'):
            antivirus['BASE_VERSION'] = eset_reg['/ScannerVersion']
        
        if eset_reg.get('/ProductName'):
            antivirus['NAME'] = eset_reg['/ProductName']
        
        # Look at license file
        if eset_reg.get('/AppDataDir') and has_folder(eset_reg['/AppDataDir'] + '/License'):
            license_file = eset_reg['/AppDataDir'] + '/License/license.lf'
            content = get_all_lines(file=license_file)
            if content:
                string = ''.join(get_sanitized_string(line) for line in content)
                # Extract XML
                xml_match = re.search(r'(<ESET\s.*</ESET>)', string)
                if xml_match:
                    expiration = None
                    try:
                        from glpi_agent.xml import XML
                        tree = XML(string=xml_match.group(1)).dump_as_hash()
                        expiration = tree.get('ESET', {}).get('PRODUCT_LICENSE_FILE', {}).get('LICENSE', {}).get('ACTIVE_PRODUCT', {}).get('-EXPIRATION_DATE')
                    except:
                        pass
                    
                    # Extracted expiration is like: 2018-11-17T12:00:00Z
                    if expiration:
                        exp_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})T', expiration)
                        if exp_match:
                            antivirus['EXPIRATION'] = f"{exp_match.group(3)}/{exp_match.group(2)}/{exp_match.group(1)}"
    
    def _set_avira_infos(self, antivirus):
        avira_infos = get_wmi_objects(
            moniker='winmgmts://./root/CIMV2/Applications/Avira_AntiVir',
            class_name="License_Info",
            properties=['License_Expiration']
        )
        
        if avira_infos and avira_infos[0].get('License_Expiration'):
            expiration_match = re.match(r'^(\d+\.\d+\.\d+)', avira_infos[0]['License_Expiration'])
            if expiration_match:
                expiration = expiration_match.group(1).replace('.', '/')
                antivirus['EXPIRATION'] = expiration
        
        avira_reg = self._get_software_registry_keys(
            'Avira/Antivirus',
            ['VdfVersion']
        )
        if not avira_reg:
            return
        
        if avira_reg.get('/VdfVersion'):
            antivirus['BASE_VERSION'] = avira_reg['/VdfVersion']
    
    def _set_ms_essentials_infos(self, antivirus):
        mse_reg = self._get_software_registry_keys(
            'Microsoft/Microsoft Antimalware/Signature Updates',
            ['AVSignatureVersion']
        )
        if not mse_reg:
            return
        
        if mse_reg.get('/AVSignatureVersion'):
            antivirus['BASE_VERSION'] = mse_reg['/AVSignatureVersion']
    
    def _set_fsecure_infos(self, antivirus):
        fsec_reg = self._get_software_registry_keys(
            'F-Secure/Ultralight/Updates/aquarius',
            ['file_set_visible_version']
        )
        if not fsec_reg:
            return
        
        found = first(
            lambda v: isinstance(v, dict) and v.get('/file_set_visible_version'),
            fsec_reg.values()
        )
        
        if found and found.get('/file_set_visible_version'):
            antivirus['BASE_VERSION'] = found['/file_set_visible_version']
        
        # Try to find license "expiry_date" from a specific json file
        fsec_reg = self._get_software_registry_keys(
            'F-Secure/CCF/DLLHoster/100/Plugins/CosmosService',
            ['DataPath']
        )
        if not fsec_reg:
            return
        
        path = fsec_reg.get('/DataPath')
        if not path or not has_folder(path):
            return
        
        # This is the full path for the expected json file
        path += "\\safe.S-1-5-18.local.cosmos"
        if not has_file(path):
            return
        
        infos = get_all_lines(file=path)
        if not infos:
            return
        
        try:
            import json
            infos = json.loads(infos)
            licenses = infos.get('local', {}).get('windows', {}).get('secl', {}).get('subscription', {}).get('license_table', [])
        except:
            return
        
        if not licenses:
            return
        
        expiry_date = None
        # In the case more than one license is found, assume we need the one with appid=2
        for license_entry in licenses:
            if license_entry.get('expiry_date'):
                expiry_date = license_entry['expiry_date']
            if expiry_date and license_entry.get('appid') == 2:
                break
        
        if not expiry_date:
            return
        
        date = time.localtime(expiry_date)
        antivirus['EXPIRATION'] = f"{date.tm_mday:02d}/{date.tm_mon:02d}/{date.tm_year:04d}"
    
    def _set_bitdefender_infos(self, antivirus, logger=None, command=None):
        # Use given default command, but try to find it if installation path is not the default one
        command_found = can_run(command) if command else False
        
        if not command_found:
            installpath = self._get_software_registry_keys(
                'BitDefender/Endpoint Security',
                ['InstallPath'],
                lambda reg: next(
                    (reg[key]["Install/"]["/InstallPath"] 
                     for key in reg.keys()
                     if re.match(r'^\{[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}\/$', key, re.IGNORECASE)
                     and reg[key].get("Install/") 
                     and reg[key]["Install/"].get("/InstallPath")),
                    None
                )
            )
            
            if installpath:
                sep = "" if installpath.endswith("\\") else "\\"
                command = installpath + sep + "product.console.exe"
                command_found = can_run(command)
        
        # Don't check data in registry if Bitdefender Endpoint Security Tools is found
        if command_found:
            version = get_first_line(command=f'"{command}" /c GetVersion product', logger=logger)
            if version:
                antivirus['VERSION'] = version
            
            base_version = get_first_line(command=f'"{command}" /c GetVersion antivirus', logger=logger)
            if base_version:
                antivirus['BASE_VERSION'] = base_version
            
            # Don't check if up-to-date with command if still reported by WMI on Windows Desktop
            if 'UPTODATE' not in antivirus:
                update_status = get_all_lines(command=f'"{command}" /c GetUpdateStatus product', logger=logger)
                attempt_time = next((int(line.split(': ')[1]) for line in update_status if line.startswith('lastAttemptedTime: ')), None)
                success_time = next((int(line.split(': ')[1]) for line in update_status if line.startswith('lastSucceededTime: ')), None)
                uptodate = 1 if attempt_time and success_time and attempt_time == success_time else 0
                
                if uptodate:
                    update_status = get_all_lines(command=f'"{command}" /c GetUpdateStatus antivirus', logger=logger)
                    attempt_time = next((int(line.split(': ')[1]) for line in update_status if line.startswith('lastAttemptedTime: ')), None)
                    success_time = next((int(line.split(': ')[1]) for line in update_status if line.startswith('lastSucceededTime: ')), None)
                    if attempt_time and success_time and attempt_time == success_time:
                        uptodate += 1
                
                antivirus['UPTODATE'] = 1 if uptodate > 1 else 0
            
            if not antivirus.get('COMPANY'):
                antivirus['COMPANY'] = "Bitdefender"
            return
        
        bitdefender_reg = self._get_software_registry_keys(
            'BitDefender/About',
            ['ProductName', 'ProductVersion']
        )
        
        if not bitdefender_reg:
            return
        
        if bitdefender_reg.get('/ProductVersion'):
            antivirus['VERSION'] = bitdefender_reg['/ProductVersion']
        if bitdefender_reg.get('/ProductName'):
            antivirus['NAME'] = bitdefender_reg['/ProductName']
        
        path = self._get_software_registry_keys(
            'BitDefender',
            ['Bitdefender Scan Server'],
            lambda reg: reg.get('/Bitdefender Scan Server')
        )
        
        if path and has_folder(path):
            handle = get_directory_handle(directory=path)
            if handle:
                major, minor = 0, 0
                for entry in os.listdir(path):
                    match = re.match(r'Antivirus_(\d+)_(\d+)', entry)
                    if not match:
                        continue
                    
                    entry_path = os.path.join(path, entry)
                    if not (has_folder(f"{entry_path}/Plugins") and has_file(f"{entry_path}/Plugins/update.txt")):
                        continue
                    
                    entry_major, entry_minor = int(match.group(1)), int(match.group(2))
                    if entry_major < major or (entry_major == major and entry_minor < minor):
                        continue
                    
                    major, minor = entry_major, entry_minor
                    update_lines = get_all_lines(file=f"{entry_path}/Plugins/update.txt")
                    update = {}
                    for line in update_lines:
                        if ':' in line:
                            key, val = line.split(':', 1)
                            update[key.strip()] = val.strip()
                    
                    if update.get("Signature number"):
                        antivirus['BASE_VERSION'] = update["Signature number"]
        
        surveydata = self._get_software_registry_keys(
            'BitDefender/Install',
            ['SurveyDataInfo'],
            lambda reg: reg.get('/SurveyDataInfo')
        )
        
        if surveydata:
            try:
                import json
                datas = json.loads(surveydata)
                days_left = datas.get('days_left')
                if days_left is not None:
                    exp_time = time.time() + 86400 * days_left
                    date = time.localtime(exp_time)
                    antivirus['EXPIRATION'] = f"{date.tm_mday:02d}/{date.tm_mon:02d}/{date.tm_year:04d}"
            except:
                pass
    
    def _set_norton_infos(self, antivirus):
        # ref: https://support.symantec.com/en_US/article.TECH251363.html
        norton_reg = self._get_software_registry_keys(
            'Norton/{0C55C096-0F1D-4F28-AAA2-85EF591126E7}',
            ['PRODUCTVERSION']
        )
        if norton_reg and norton_reg.get('PRODUCTVERSION'):
            antivirus['VERSION'] = norton_reg['PRODUCTVERSION']
        
        # Lookup for BASE_VERSION as CurDefs in definfo.dat in some places
        datadirs = [
            'C:/ProgramData/Symantec/Symantec Endpoint Protection/CurrentVersion/Data',
            'C:/Documents and Settings/All Users/Application Data/Symantec/Symantec Endpoint Protection/CurrentVersion/Data',
        ]
        
        norton_reg = self._get_software_registry_keys(
            'Norton/{0C55C096-0F1D-4F28-AAA2-85EF591126E7}/Common Client/PathExpansionMap',
            ['DATADIR']
        )
        if norton_reg and norton_reg.get('DATADIR'):
            datadir = norton_reg['DATADIR'].replace('\\', '/')
            if has_folder(datadir):
                datadirs.insert(0, datadir)
        
        # Extract BASE_VERSION from the first found valid definfo.dat file
        for datadir in datadirs:
            defdir = None
            for subdir in ['Definitions/SDSDefs', 'Definitions/VirusDefs']:
                if has_folder(f"{datadir}/{subdir}"):
                    defdir = subdir
                    break
            
            if not defdir:
                continue
            
            definfo = f"{datadir}/{defdir}/definfo.dat"
            if not has_file(definfo):
                continue
            
            lines = get_all_lines(file=definfo)
            curdefs = first(lambda line: line.startswith('CurDefs='), lines)
            if curdefs:
                match = re.match(r'^CurDefs=(.*)$', curdefs)
                if match:
                    antivirus['BASE_VERSION'] = match.group(1)
                    break
    

    def _set_trend_micro_security_agent_infos(self, antivirus):
        security_agent_reg = self._get_software_registry_keys(
            'TrendMicro/PC-cillinNTCorp/CurrentVersion/Misc.',
            ['InternalNonCrcPatternVer', 'TmListen_Ver']
        )
        if security_agent_reg:
            antivirus['COMPANY'] = "Trend Micro Inc."
            if security_agent_reg.get('TmListen_Ver'):
                antivirus['VERSION'] = security_agent_reg['TmListen_Ver']
            
            if security_agent_reg.get('InternalNonCrcPatternVer'):
                version_hex = security_agent_reg['InternalNonCrcPatternVer']
                try:
                    if isinstance(version_hex, str) and version_hex.startswith('0x'):
                        version = int(version_hex, 16)
                    else:
                        version = int(version_hex)
                    
                    major = version // 100000
                    minor = (version % 100000) // 100
                    rev = version % 100
                    
                    if major:
                        antivirus['BASE_VERSION'] = f"{major}.{minor:03d}.{rev:02d}"
                except:
                    pass
    
    def _set_cortex_infos(self, antivirus, logger=None, command=None):
        if not antivirus:
            antivirus = {'NAME': "Cortex XDR"}
        
        antivirus['COMPANY'] = "Palo Alto Networks"
        
        if command:
            version = get_first_match(
                command=f'"{command}" info',
                pattern=r'^Cortex XDR .* ([0-9.]+)$',
                logger=logger
            )
            if version:
                antivirus['VERSION'] = version
            
            base_version = get_first_match(
                command=f'"{command}" info query',
                pattern=r'^Content Version:\s+(\S+)$',
                logger=logger
            )
            if base_version:
                antivirus['BASE_VERSION'] = base_version
    
    def _set_sentinelone_infos(self, antivirus, logger=None, command=None):
        antivirus['COMPANY'] = "Sentinel Labs Inc."
        
        if command:
            lines = get_all_lines(
                command=f'"{command}" status',
                logger=logger
            )
            
            version_line = first(lambda line: 'Monitor Build id:' in line, lines)
            if version_line:
                match = re.search(r'Monitor Build id:\s+([0-9.]+)', version_line)
                if match:
                    antivirus['VERSION'] = match.group(1)
            
            disabled_line = first(lambda line: 'Disable State: Agent disabled' in line, lines)
            antivirus['ENABLED'] = 0 if disabled_line else 1
            
            # Not supported so we just assume it is updated when enabled
            antivirus['UPTODATE'] = antivirus['ENABLED']
    
    def _set_crowdstrike_infos(self, antivirus, logger=None, command=None):
        antivirus['COMPANY'] = "CrowdStrike"
        
        if command:
            version = get_first_match(
                command=f'"{command}" --version',
                pattern=r'^CsSensorSettings Version: ([0-9.]+)$',
                logger=logger
            )
            if version:
                antivirus['VERSION'] = version
        
        # Not supported on Windows Server so we just assume it is updated when enabled
        if 'UPTODATE' not in antivirus:
            antivirus['UPTODATE'] = antivirus.get('ENABLED', 0)
    
    def _get_software_registry_keys(self, base, values, callback=None):
        """Get software registry keys with support for both 32-bit and 64-bit paths."""
        reg = None
        
        if is64bit():
            reg = get_registry_key(
                path=f'HKEY_LOCAL_MACHINE/SOFTWARE/Wow6432Node/{base}',
                required=values
            )
            if reg:
                if callback:
                    result = callback(reg)
                    if result:
                        return result
                else:
                    return reg
        
        reg = get_registry_key(
            path=f'HKEY_LOCAL_MACHINE/SOFTWARE/{base}',
            required=values
        )
        
        return callback(reg) if callback and reg else reg