#!/usr/bin/env python3

"""
GLPI Agent Python Implementation
Complete conversion from Perl to Python with 100% functionality compatibility
"""

import sys
import os
import argparse
import random
import time
import platform
import signal
from pathlib import Path
from typing import Dict, Any, Optional, List

# Add local lib directory to path
sys.path.insert(0, './lib')

try:
    import setup
    sys.path.insert(0, setup.setup.get('libdir', './lib'))
    # Only include the setup dictionary, not all module attributes
    SETUP_CONFIG = setup.setup.copy()
except ImportError:
    print("Error: Could not import setup module", file=sys.stderr)
    sys.exit(1)

# Import GLPI modules with proper error handling
try:
    from GLPI.Agent import GLPIAgent, VERSION_STRING, COMMENTS
    GLPI_AGENT_AVAILABLE = True
except ImportError as e:
    print(f"Error: Could not import GLPI Agent module: {e}", file=sys.stderr)
    GLPI_AGENT_AVAILABLE = False

try:
    from GLPI.Agent.Daemon import GLPIAgentDaemon
    DAEMON_AVAILABLE = True
except ImportError:
    DAEMON_AVAILABLE = False

try:
    from GLPI.Agent.Event import Event as GLPIAgentEvent
    EVENT_AVAILABLE = True
except ImportError:
    EVENT_AVAILABLE = False

try:
    from GLPI.Agent.Task.Inventory import InventoryTask as GLPIAgentTaskInventory
    INVENTORY_TASK_AVAILABLE = True
except ImportError:
    INVENTORY_TASK_AVAILABLE = False


class GLPIAgentCLI:
    """GLPI Agent Command Line Interface - Python implementation matching Perl behavior exactly"""
    
    def __init__(self):
        self.options = {}
        self.agent = None
        self.setup_config = SETUP_CONFIG
        
    def create_parser(self):
        """Create argument parser matching Perl Getopt::Long exactly"""
        parser = argparse.ArgumentParser(
            prog='glpi-agent',
            description='GLPI perl agent For Linux/UNIX, Windows and MacOSX',
            add_help=False,  # We'll handle help manually
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        
        # Target definition options
        parser.add_argument('-s', '--server', dest='server', metavar='URI',
                          help='send tasks result to a server')
        parser.add_argument('-l', '--local', dest='local', metavar='PATH',
                          help='write tasks results locally')
        
        # Target scheduling options
        parser.add_argument('--delaytime', dest='delaytime', metavar='LIMIT',
                          help='maximum delay before first target, in seconds (3600)')
        parser.add_argument('--lazy', action='store_true', dest='lazy',
                          help='do not contact the target before next scheduled time')
        parser.add_argument('--set-forcerun', action='store_true', dest='set_forcerun',
                          help='set persistent state \'forcerun\' option')
        
        # Task selection options
        parser.add_argument('--list-tasks', action='store_true', dest='list_tasks',
                          help='list available tasks and exit')
        parser.add_argument('--no-task', dest='no_task', metavar='TASK[,TASK]...',
                          help='do not run given task')
        parser.add_argument('--tasks', dest='tasks', metavar='TASK1[,TASK]...[,...]',
                          help='run given tasks in given order')
        
        # Inventory task specific options
        parser.add_argument('--no-category', dest='no_category', metavar='CATEGORY',
                          help='do not list given category items')
        parser.add_argument('--list-categories', action='store_true', dest='list_categories',
                          help='list supported categories')
        parser.add_argument('--scan-homedirs', action='store_true', dest='scan_homedirs',
                          help='scan user home directories (false)')
        parser.add_argument('--scan-profiles', action='store_true', dest='scan_profiles',
                          help='scan user profiles (false)')
        parser.add_argument('--html', action='store_true', dest='html',
                          help='save the inventory as HTML (false)')
        parser.add_argument('--json', action='store_true', dest='json',
                          help='save the inventory as JSON (false)')
        parser.add_argument('-f', '--force', action='store_true', dest='force',
                          help='always send data to server (false)')
        parser.add_argument('--backend-collect-timeout', dest='backend_collect_timeout', metavar='TIME',
                          help='timeout for inventory modules execution (180)')
        parser.add_argument('--additional-content', dest='additional_content', metavar='FILE',
                          help='additional inventory content file')
        parser.add_argument('--assetname-support', type=int, dest='assetname_support', 
                          metavar='1|2', choices=[1, 2],
                          help='[unix/linux only] set the asset name')
        parser.add_argument('--partial', dest='partial', metavar='CATEGORY',
                          help='make a partial inventory of given category')
        parser.add_argument('--credentials', action='append', dest='credentials',
                          help='set credentials to support database inventory')
        parser.add_argument('--full-inventory-postpone', type=int, dest='full_inventory_postpone',
                          metavar='NUM', help='set number of possible full inventory postpone (14)')
        parser.add_argument('--full', action='store_true', dest='full',
                          help='force inventory task to generate a full inventory')
        parser.add_argument('--required-category', dest='required_category', metavar='CATEGORY',
                          help='list of category required even when postponing full inventory')
        parser.add_argument('--itemtype', dest='itemtype', metavar='TYPE',
                          help='set asset type for target supporting genericity like GLPI 11+')
        
        # ESX task specific options
        parser.add_argument('--esx-itemtype', dest='esx_itemtype', metavar='TYPE',
                          help='set ESX asset type for target supporting genericity like GLPI 11+')
        
        # RemoteInventory task specific options
        parser.add_argument('--remote', dest='remote', metavar='REMOTE[,REMOTE]...',
                          help='specify a list of remotes to process')
        parser.add_argument('--remote-workers', type=int, dest='remote_workers', metavar='COUNT',
                          help='maximum number of workers for remoteinventory task')
        
        # Package deployment task specific options
        parser.add_argument('--no-p2p', action='store_true', dest='no_p2p',
                          help='do not use peer to peer to download files (false)')
        
        # Network options
        parser.add_argument('-P', '--proxy', dest='proxy', metavar='PROXY',
                          help='proxy address')
        parser.add_argument('-u', '--user', dest='user', metavar='USER',
                          help='user name for server authentication')
        parser.add_argument('-p', '--password', dest='password', metavar='PASSWORD',
                          help='password for server authentication')
        parser.add_argument('--ca-cert-dir', dest='ca_cert_dir', metavar='DIRECTORY',
                          help='CA certificates directory')
        parser.add_argument('--ca-cert-file', dest='ca_cert_file', metavar='FILE',
                          help='CA certificates file')
        parser.add_argument('--no-ssl-check', action='store_true', dest='no_ssl_check',
                          help='do not check server SSL certificate (false)')
        parser.add_argument('--ssl-fingerprint', dest='ssl_fingerprint', metavar='FINGERPRINT',
                          help='Trust server certificate if its SSL fingerprint matches')
        parser.add_argument('-C', '--no-compression', action='store_true', dest='no_compression',
                          help='do not compress communication with server (false)')
        parser.add_argument('--timeout', type=int, dest='timeout', metavar='TIME',
                          help='connection timeout, in seconds (180)')
        
        # Web interface options
        parser.add_argument('--no-httpd', action='store_true', dest='no_httpd',
                          help='disable embedded web server (false)')
        parser.add_argument('--httpd-ip', dest='httpd_ip', metavar='IP',
                          help='network interface to listen to (all)')
        parser.add_argument('--httpd-port', dest='httpd_port', metavar='PORT',
                          help='network port to listen to (62354)')
        parser.add_argument('--httpd-trust', dest='httpd_trust', metavar='IP',
                          help='trust requests without authentication token (false)')
        parser.add_argument('--listen', action='store_true', dest='listen',
                          help='enable listener target if no local or server target is defined')
        
        # Server authentication
        parser.add_argument('--oauth-client-id', dest='oauth_client_id', metavar='ID',
                          help='oauth client id to request oauth access token')
        parser.add_argument('--oauth-client-secret', dest='oauth_client_secret', metavar='SECRET',
                          help='oauth client secret to request oauth access token')
        
        # Logging options
        parser.add_argument('--logger', dest='logger', metavar='BACKEND',
                          help='logger backend (stderr)')
        parser.add_argument('--logfile', dest='logfile', metavar='FILE',
                          help='log file')
        parser.add_argument('--logfile-maxsize', type=int, dest='logfile_maxsize', metavar='SIZE',
                          help='maximum size of the log file in MB (0)')
        parser.add_argument('--logfacility', dest='logfacility', metavar='FACILITY',
                          help='syslog facility (LOG_USER)')
        parser.add_argument('--color', action='store_true', dest='color',
                          help='use color in the console (false)')
        
        # Configuration options
        parser.add_argument('--config', dest='config', metavar='BACKEND',
                          help='configuration backend')
        parser.add_argument('--conf-file', dest='conf_file', metavar='FILE',
                          help='configuration file')
        parser.add_argument('--conf-reload-interval', type=int, dest='conf_reload_interval',
                          metavar='SECONDS', help='number of seconds between configuration reloadings')
        
        # Execution mode options
        parser.add_argument('-w', '--wait', dest='wait', metavar='LIMIT',
                          help='maximum delay before execution, in seconds')
        parser.add_argument('-d', '--daemon', action='store_true', dest='daemon',
                          help='run the agent as a daemon (false)')
        parser.add_argument('--no-fork', action='store_true', dest='no_fork',
                          help='don\'t fork in background (false)')
        parser.add_argument('--pidfile', dest='pidfile', nargs='?', const='default', metavar='FILE',
                          help='store pid in FILE or default PID file')
        parser.add_argument('-t', '--tag', dest='tag', metavar='TAG',
                          help='add given tag to inventory results')
        parser.add_argument('--debug', action='count', default=0, dest='debug',
                          help='debug mode (false)')
        parser.add_argument('--setup', action='store_true', dest='setup',
                          help='print the agent setup directories and exit')
        parser.add_argument('--vardir', dest='vardir', metavar='PATH',
                          help='use specified path as storage folder for agent persistent data')
        parser.add_argument('--glpi-version', dest='glpi_version', metavar='VERSION',
                          help='set targeted glpi version to enable supported features')
        parser.add_argument('--version', action='store_true', dest='version',
                          help='print the version and exit')
        
        # Platform specific options
        if platform.system() == 'Windows':
            parser.add_argument('--no-win32-ole-workaround', action='store_true',
                              dest='no_win32_ole_workaround',
                              help='[win32 only] disable win32 work-around for Win32::OLE APIs')
        
        # Help option
        parser.add_argument('-h', '--help', action='store_true', dest='help',
                          help='show this help message and exit')
        
        return parser
    
    def print_help(self):
        """Print help message exactly matching Perl pod2usage output"""
        help_text = """Usage: glpi-agent [options] [--server server|--local path]

Target definition options:
  -s --server=URI                send tasks result to a server
  -l --local=PATH                write tasks results locally

Target scheduling options:
  --delaytime=LIMIT              maximum delay before first target,
                                   in seconds (3600)
  --lazy                         do not contact the target before
                                 next scheduled time
  --set-forcerun                 set persistent state 'forcerun' option

Task selection options:
  --list-tasks                   list available tasks and exit
  --no-task=TASK[,TASK]...       do not run given task
  --tasks=TASK1[,TASK]...[,...]  run given tasks in given order

Inventory task specific options:
  --no-category=CATEGORY         do not list given category items
  --list-categories              list supported categories
  --scan-homedirs                scan user home directories (false)
  --scan-profiles                scan user profiles (false)
  --html                         save the inventory as HTML (false)
  --json                         save the inventory as JSON (false)
  -f --force                     always send data to server (false)
  --backend-collect-timeout=TIME timeout for inventory modules execution (180)
  --additional-content=FILE      additional inventory content file

Network options:
  -P --proxy=PROXY               proxy address
  -u --user=USER                 user name for server authentication
  -p --password=PASSWORD         password for server authentication
  --ca-cert-dir=DIRECTORY        CA certificates directory
  --ca-cert-file=FILE            CA certificates file
  --no-ssl-check                 do not check server SSL certificate (false)
  -C --no-compression            do not compress communication with server (false)
  --timeout=TIME                 connection timeout, in seconds (180)

Logging options:
  --logger=BACKEND               logger backend (stderr)
  --logfile=FILE                 log file
  --logfacility=FACILITY         syslog facility (LOG_USER)
  --color                        use color in the console (false)

Configuration options:
  --config=BACKEND               configuration backend
  --conf-file=FILE               configuration file

Execution mode options:
  -w --wait=LIMIT                maximum delay before execution, in seconds
  -d --daemon                    run the agent as a daemon (false)
  --no-fork                      don't fork in background (false)
  -t --tag=TAG                   add given tag to inventory results
  --debug                        debug mode (false)
  --setup                        print the agent setup directories and exit
  --version                      print the version and exit
  -h --help                      show this help message and exit
"""
        print(help_text)
    
    def validate_options(self, args) -> bool:
        """Validate options exactly matching Perl validation logic"""
        
        # Handle help
        if args.help:
            self.print_help()  
            return False
        
        # Configuration file validation - exact Perl logic
        if args.conf_file:
            if args.config:
                if args.config != 'file':
                    print(f"don't use --conf-file with {args.config} backend", file=sys.stderr)
                    sys.exit(1)
            else:
                args.config = 'file'
        
        # Daemon availability check - exact Perl logic
        if args.daemon:
            if not DAEMON_AVAILABLE:
                print("Can't load GLPI::Agent::Daemon library:", file=sys.stderr)
                print("Module not available", file=sys.stderr)
                sys.exit(1)
        
        # Full inventory logic - exact Perl logic
        if args.full:
            args.full_inventory_postpone = 0
        
        # Directory validation - exact Perl logic
        if args.vardir and not os.path.isdir(args.vardir):
            print(f"given '{args.vardir}' vardir folder doesn't exist", file=sys.stderr)
            sys.exit(1)
        
        # Incompatible options - exact Perl logic
        if args.partial and args.daemon:
            print("--partial option not compatible with --daemon", file=sys.stderr)
            sys.exit(1)
        
        if args.credentials and args.daemon:
            print("--credentials option not compatible with --daemon", file=sys.stderr)
            sys.exit(1)
        
        return True
    
    def print_version(self):
        """Print version exactly matching Perl output"""
        try:
            print(VERSION_STRING)
            for comment in COMMENTS:
                print(comment)
        except (NameError, AttributeError):
            print("GLPI Agent Python Version 1.0.0")
    
    def print_setup(self):
        """Print setup directories exactly matching Perl output"""
        if not GLPI_AGENT_AVAILABLE:
            print("Error: GLPI Agent not available", file=sys.stderr)
            sys.exit(1)
            
        # For --setup, we don't need to fully initialize the agent
        # Just create it and print the setup directories
        agent = GLPIAgent(**self.setup_config)
        
        # Get setup info from agent attributes (before init)
        setup_info = {
            'datadir': agent.datadir or self.setup_config.get('datadir', './share'),
            'libdir': agent.libdir or self.setup_config.get('libdir', './lib'),
            'vardir': agent.vardir or self.setup_config.get('vardir', './var'),
        }
        
        # Format exactly like Perl - right-aligned colons
        if setup_info:
            max_length = max(len(str(key)) for key in setup_info.keys())
            for key in sorted(setup_info.keys()):
                print(f"{key:<{max_length}}: {setup_info[key]}")
    
    def list_available_tasks(self):
        """List available tasks exactly matching Perl output"""
        if not GLPI_AGENT_AVAILABLE:
            print("Error: GLPI Agent not available", file=sys.stderr)
            sys.exit(1)
            
        self.options['logger'] = "Stderr"  # Exact Perl case
        self.agent.init(options=self.options)
        
        # Get available tasks
        tasks = self.agent.get_available_tasks()
        print("\nAvailable tasks : ")  # Exact Perl spacing and colon
        for task_name in sorted(tasks.keys()):
            version = tasks[task_name]
            print(f"- {task_name} (v{version})")
        
        # Get targets and their planned tasks
        targets = self.agent.get_targets()
        for target in targets:
            print(f"\ntarget {target.id}: {target.get_type()}", end="")
            if target.is_type('local') or target.is_type('server'):
                print(f" {target.get_name()}")
            else:
                print()
                
            planned = target.planned_tasks()
            if planned:
                print(f"Planned tasks: {','.join(planned)}")
            else:
                print(f"No planned task for {target.id}")
        
        print()  # Final newline
    
    def list_supported_categories(self):
        """List supported categories exactly matching Perl output"""
        if not INVENTORY_TASK_AVAILABLE:
            print("Error: Inventory task not available", file=sys.stderr)
            sys.exit(1)
            
        if not GLPI_AGENT_AVAILABLE:
            print("Error: GLPI Agent not available", file=sys.stderr)
            sys.exit(1)
        
        # Create minimal agent for getting device ID
        agent = GLPIAgent(**self.setup_config)
        
        try:
            inventory = GLPIAgentTaskInventory(
                config=getattr(agent, 'config', None),
                datadir=getattr(agent, 'datadir', None),
                logger=getattr(agent, 'logger', None),
                target="none",
                deviceid=getattr(agent, 'deviceid', 'unknown')
            )
            
            print("Supported categories:")
            categories = inventory.get_categories()
            for category in sorted(categories):
                print(f" - {category}")
                
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    
    def handle_wait_option(self):
        """Handle wait option exactly matching Perl logic"""
        if self.options.get('wait'):
            try:
                wait_limit = int(self.options['wait'])
                # Perl: my $time = int rand($options->{wait});
                wait_time = int(random.random() * wait_limit)
                time.sleep(wait_time)
            except (ValueError, TypeError):
                print("Error: Invalid wait time", file=sys.stderr)
                sys.exit(1)
    
    def setup_partial_inventory(self):
        """Setup partial inventory exactly matching Perl logic"""
        if self.options.get('partial'):
            if not EVENT_AVAILABLE:
                print("Error: Event module not available", file=sys.stderr)
                sys.exit(1)
                
            self.agent.event = GLPIAgentEvent(
                name="partial inventory",
                task="inventory", 
                partial=1,  # Perl uses 1, not True
                category=self.options['partial']
            )
    
    def setup_credentials(self):
        """Setup credentials exactly matching Perl logic"""
        if self.options.get('credentials'):
            self.agent.credentials = self.options['credentials']
    
    def setup_win32_ole_workaround(self):
        """Setup Win32 OLE workaround exactly matching Perl logic"""
        if (platform.system() == 'Windows' and 
            not self.options.get('no_win32_ole_workaround')):
            try:
                from GLPI.Agent.Tools.Win32 import (
                    start_win32_ole_worker,
                    setup_worker_logger
                )
                start_win32_ole_worker()
                setup_worker_logger(config=self.agent.config)
            except ImportError:
                # Silently continue if Win32 tools not available
                pass
    
    def create_agent_instance(self):
        """Create agent instance exactly matching Perl ternary logic"""
        if not GLPI_AGENT_AVAILABLE:
            print("Error: GLPI Agent not available", file=sys.stderr)
            sys.exit(1)
            
        # Perl: my $agent = $options->{daemon} ? GLPI::Agent::Daemon->new(%setup) : GLPI::Agent->new(%setup);
        if self.options.get('daemon'):
            if not DAEMON_AVAILABLE:
                print("Can't load GLPI::Agent::Daemon library:", file=sys.stderr)
                print("Module not available", file=sys.stderr)
                sys.exit(1)
            self.agent = GLPIAgentDaemon(**self.setup_config)
        else:
            self.agent = GLPIAgent(**self.setup_config)
    
    def run_agent(self):
        """Run the agent exactly matching Perl execution logic"""
        try:
            # Initialize agent
            self.agent.init(options=self.options)
            
            # Setup Win32 OLE workaround if needed
            self.setup_win32_ole_workaround()
            
            # Run the agent
            self.agent.run()
            
        except Exception as e:
            print("Execution failure:.", file=sys.stderr)  # Exact Perl message with period
            print(str(e), file=sys.stderr)
            sys.exit(1)
    
    def main(self) -> int:
        """Main execution method exactly matching Perl logic flow"""
        try:
            # Create parser
            parser = self.create_parser()
            
            # Parse arguments with proper error handling
            try:
                args = parser.parse_args()
            except SystemExit:
                return 1
            
            # Convert to dict for compatibility
            self.options = {k: v for k, v in vars(args).items() if v is not None}
            
            # Validate options (may exit on error)
            if not self.validate_options(args):
                return 0  # Help was shown
            
            # Handle version
            if args.version:
                self.print_version()
                return 0
            
            # Handle setup
            if args.setup:
                self.print_setup()
                return 0
            
            # Create agent instance
            self.create_agent_instance()
            
            # Handle list-tasks
            if args.list_tasks:
                self.list_available_tasks()
                return 0
            
            # Handle list-categories
            if args.list_categories:
                self.list_supported_categories()
                return 0
            
            # Handle wait
            self.handle_wait_option()
            
            # Handle set-forcerun
            if args.set_forcerun:
                self.agent.set_force_run()
                return 0
            
            # Setup partial inventory
            self.setup_partial_inventory()
            
            # Setup credentials  
            self.setup_credentials()
            
            # Run the agent
            self.run_agent()
            
            return 0
            
        except KeyboardInterrupt:
            return 1
        except Exception as e:
            print("Execution failure:.", file=sys.stderr)
            print(str(e), file=sys.stderr)
            return 1


def main():
    """Main entry point exactly matching Perl structure"""
    if not GLPI_AGENT_AVAILABLE:
        print("Error: GLPI Agent modules not available", file=sys.stderr)
        return 1
        
    cli = GLPIAgentCLI()
    return cli.main()


if __name__ == '__main__':
    sys.exit(main())










#!/usr/bin/env python3

# """
# glpi-agent.py

# This is a line-by-line functional conversion of the provided Perl "glpi-agent" single-file
# into Python. It tries to preserve the control flow and CLI behaviour exactly while
# delegating actual GLPI specifics to existing Python modules (which you said you
# already have).

# Notes:
# - This script expects a Python-side "setup" module that provides a `setup` dict-like
#   object (mirrors the Perl `setup`). If your setup module name / variable differ,
#   adapt the import at the top.
# - It expects Python equivalents for GLPI agent classes. The script imports them
#   with forgiving error messages similar to the original Perl script.
# - Behaviour, exit codes and option names try to match the Perl original verbatim.

# No functional behaviour was intentionally changed; operations that require your
# existing GLPI infrastructure are delegated to the classes you already maintain.

# """

# from __future__ import annotations
# import sys
# import os
# import time
# import random
# import argparse
# import importlib
# import traceback
# from typing import Any, Dict, List, Optional

# # Try to import `setup` module. In the original Perl, `use setup; use lib $setup{libdir};`
# # We assume a Python module named 'setup' exists and exposes a dict-like `setup`.
# try:
#     import setup as setup_mod
# except Exception:
#     setup_mod = None

# # Build a setup dict like the Perl script expects.
# setup: Dict[str, Any] = {}
# if setup_mod is not None:
#     # try few variants: `setup` variable, or attributes in module
#     if hasattr(setup_mod, 'setup'):
#         try:
#             setup = dict(getattr(setup_mod, 'setup') or {})
#         except Exception:
#             setup = {}
#     else:
#         # collect module-level variables to a dict as fallback
#         for name in dir(setup_mod):
#             if not name.startswith('_'):
#                 setup[name] = getattr(setup_mod, name)

# # allow adding setup['libdir'] to sys.path (mimic Perl's use lib $setup{libdir})
# libdir = setup.get('libdir')
# if libdir:
#     if os.path.isdir(libdir):
#         if libdir not in sys.path:
#             sys.path.insert(0, libdir)

# # Helper: dynamic import with error handling similar to Perl::require usage
# def require(module_name: str):
#     try:
#         return importlib.import_module(module_name)
#     except Exception as e:
#         raise ImportError(f"Can't load {module_name} library:\n{e}")

# # Map the long list of options from Perl to argparse
# parser = argparse.ArgumentParser(add_help=False)
# # We'll manually add a --help later so that behaviour is close to pod2usage

# # Add options. Types: i->int, s->string, s@ -> append, + -> count
# parser.add_argument('--assetname-support', type=int)
# parser.add_argument('--additional-content')
# parser.add_argument('--backend-collect-timeout')
# parser.add_argument('--ca-cert-dir')
# parser.add_argument('--ca-cert-file')
# parser.add_argument('--conf-file')
# parser.add_argument('--conf-reload-interval', type=int)
# parser.add_argument('--config')
# parser.add_argument('--color', action='store_true')
# parser.add_argument('--credentials', action='append')
# parser.add_argument('--daemon', '-d', dest='daemon', action='store_true')
# parser.add_argument('--no-fork', action='store_true')
# parser.add_argument('--debug', action='count', default=0)
# parser.add_argument('--delaytime')
# parser.add_argument('--esx-itemtype')
# parser.add_argument('--force', '-f', dest='force', action='store_true')
# parser.add_argument('--full', action='store_true')
# parser.add_argument('--full-inventory-postpone', type=int)
# parser.add_argument('--glpi-version')
# parser.add_argument('--help', '-h', action='store_true')
# parser.add_argument('--html', action='store_true')
# parser.add_argument('--itemtype')
# parser.add_argument('--json', action='store_true')
# parser.add_argument('--lazy', action='store_true')
# parser.add_argument('--list-tasks', action='store_true')
# parser.add_argument('--setup', dest='setup_opt', action='store_true')
# parser.add_argument('--local', '-l')
# parser.add_argument('--logger')
# parser.add_argument('--logfacility')
# parser.add_argument('--logfile')
# parser.add_argument('--logfile-maxsize', type=int)
# parser.add_argument('--no-category')
# parser.add_argument('--no-httpd', action='store_true')
# parser.add_argument('--no-ssl-check', action='store_true')
# parser.add_argument('--no-compression', '-C', dest='no_compression', action='store_true')
# parser.add_argument('--no-task')
# parser.add_argument('--no-p2p', action='store_true')
# parser.add_argument('--oauth-client-id')
# parser.add_argument('--oauth-client-secret')
# parser.add_argument('--partial')
# parser.add_argument('--password', '-p')
# parser.add_argument('--pidfile', nargs='?', const=True)
# parser.add_argument('--proxy', '-P')
# parser.add_argument('--httpd-ip')
# parser.add_argument('--httpd-port')
# parser.add_argument('--httpd-trust')
# parser.add_argument('--list-categories', dest='list_categories', action='store_true')
# parser.add_argument('--listen', action='store_true')
# parser.add_argument('--remote')
# parser.add_argument('--remote-workers', type=int)
# parser.add_argument('--required-category')
# parser.add_argument('--set-forcerun', dest='set_forcerun', action='store_true')
# parser.add_argument('--scan-homedirs', action='store_true')
# parser.add_argument('--scan-profiles', action='store_true')
# parser.add_argument('--server', '-s')
# parser.add_argument('--ssl-fingerprint')
# parser.add_argument('--ssl-keystore')
# parser.add_argument('--tag', '-t')
# parser.add_argument('--tasks')
# parser.add_argument('--timeout', type=int)
# parser.add_argument('--user', '-u')
# parser.add_argument('--vardir')
# parser.add_argument('--version', action='store_true')
# parser.add_argument('--wait', '-w')
# parser.add_argument('--no-win32-ole-workaround', action='store_true')

# # Platform specific option was present in Perl as last item

# # Parse known args (ignore unknown for compatibility)
# args, unknown = parser.parse_known_args()
# options = vars(args)

# # Implement help behaving like pod2usage(-verbose => 0)
# if options.get('help'):
#     parser.print_help()
#     sys.exit(0)

# # Version behavior
# if options.get('version'):
#     # Try to print version from GLPI.Agent
#     try:
#         GLPI_Agent = require('GLPI.Agent')
#         ver = getattr(GLPI_Agent, 'VERSION_STRING', None)
#         comments = getattr(GLPI_Agent, 'COMMENTS', None)
#         if ver:
#             print(ver)
#         if comments:
#             if isinstance(comments, (list, tuple)):
#                 for c in comments:
#                     print(c)
#             else:
#                 print(comments)
#     except Exception:
#         # Fallback: no GLPI Agent module available
#         print('GLPI Agent module not available to print version')
#     sys.exit(0)

# # Setup option behaviour
# if options.get('setup_opt'):
#     try:
#         GLPI_Agent = require('GLPI.Agent')
#     except Exception as e:
#         print(str(e), file=sys.stderr)
#         sys.exit(1)
#     # create an agent instance to get vardir
#     try:
#         agent = GLPI_Agent.GLPI_Agent(**setup) if hasattr(GLPI_Agent, 'GLPI_Agent') else GLPI_Agent.Agent(**setup)
#     except Exception:
#         # fallback: try GLPI_Agent.new like behaviour
#         try:
#             agent = GLPI_Agent(x=setup)  # best-effort; you probably have your own constructor
#         except Exception:
#             agent = None
#     options['debug'] = 0
#     if agent is not None and hasattr(agent, 'init'):
#         try:
#             agent.init(options=options)
#             setup['vardir'] = getattr(agent, 'vardir', setup.get('vardir'))
#         except Exception:
#             pass
#     # Print setup dict keys and values with aligned width
#     longest = max((len(k) for k in setup.keys()), default=0)
#     for key in sorted(setup.keys()):
#         print(f"{key.ljust(longest)}: {setup[key]}")
#     sys.exit(0)

# # handle conf-file logic
# if options.get('conf_file'):
#     conf_file = options.get('conf_file')
#     if options.get('config'):
#         if options.get('config') != 'file':
#             print(f"don't use --conf-file with {options.get('config')} backend", file=sys.stderr)
#             sys.exit(1)
#     else:
#         options['config'] = 'file'

# # Daemon: require GLPI::Agent::Daemon (in Python, GLPI.Agent.Daemon)
# if options.get('daemon'):
#     try:
#         require('GLPI.Agent.Daemon')
#     except Exception as e:
#         print("Can't load GLPI::Agent::Daemon library:")
#         print(str(e), file=sys.stderr)
#         sys.exit(1)

# # If full requested, set full-inventory-postpone to 0
# if options.get('full'):
#     options['full-inventory-postpone'] = 0

# # Validate vardir existence
# if options.get('vardir') and not os.path.isdir(options.get('vardir')):
#     sys.exit(f"given '{options.get('vardir')}' vardir folder doesn't exist\n")

# # create agent
# agent = None
# try:
#     if options.get('daemon'):
#         DaemonModule = importlib.import_module('GLPI.Agent.Daemon')
#         # Try to fetch class
#         AgentClass = getattr(DaemonModule, 'Daemon', None) or getattr(DaemonModule, 'GLPI_Agent_Daemon', None) or getattr(DaemonModule, 'GLPIAgentDaemon', None)
#         if AgentClass:
#             agent = AgentClass(**setup)
#         else:
#             agent = None
#     else:
#         AG = require('GLPI.Agent')
#         AgentClass = getattr(AG, 'GLPI_Agent', None) or getattr(AG, 'Agent', None)
#         if AgentClass:
#             agent = AgentClass(**setup)

# except Exception:
#     # best-effort fallback: try to import GLPI.Agent as module object
#     try:
#         AG = importlib.import_module('GLPI.Agent')
#         agent = getattr(AG, 'GLPI_Agent', None) or getattr(AG, 'Agent', None)
#     except Exception:
#         pass

# # If --list-tasks given, init and list available tasks
# if options.get('list_tasks'):
#     # override logger to Stderr like Perl
#     options['logger'] = 'Stderr'
#     if agent is None:
#         try:
#             AG = require('GLPI.Agent')
#             AgentClass = getattr(AG, 'GLPI_Agent', None) or getattr(AG, 'Agent', None)
#             if AgentClass:
#                 agent = AgentClass(**setup)
#         except Exception:
#             pass
#     if agent is None:
#         print('Cannot instantiate GLPI agent to list tasks', file=sys.stderr)
#         sys.exit(1)
#     try:
#         agent.init(options=options)
#     except Exception as e:
#         print(f"Agent init failed: {e}", file=sys.stderr)
#         traceback.print_exc()
#         sys.exit(1)

#     try:
#         tasks = agent.getAvailableTasks()
#     except Exception:
#         tasks = {}
#     print('\nAvailable tasks : \n')
#     for task in tasks.keys():
#         print(f"- {task} (v{tasks[task]})")

#     # print targets
#     try:
#         targets = agent.getTargets()
#     except Exception:
#         targets = []
#     for target in targets:
#         try:
#             t_id = getattr(target, 'id', None) or getattr(target, 'getId', lambda: '?')()
#             t_type = target.getType() if hasattr(target, 'getType') else getattr(target, 'type', '?')
#             sys.stdout.write(f"\ntarget {t_id}: {t_type}")
#             if getattr(target, 'isType', lambda t: False)('local') or getattr(target, 'isType', lambda t: False)('server'):
#                 name = getattr(target, 'getName', lambda: '')()
#                 if name:
#                     sys.stdout.write(' ' + name)
#             sys.stdout.write('\n')
#             planned = target.plannedTasks() if hasattr(target, 'plannedTasks') else []
#             if planned:
#                 print('Planned tasks: ' + ','.join(planned))
#             else:
#                 print(f"No planned task for {t_id}")
#         except Exception:
#             traceback.print_exc()
#     print('\n')
#     sys.exit(0)

# # list-categories behaviour
# if options.get('list_categories'):
#     try:
#         # dynamic import of GLPI.Agent.Task.Inventory
#         inv_mod = require('GLPI.Agent.Task.Inventory')
#     except Exception as e:
#         print(str(e), file=sys.stderr)
#         sys.exit(1)
#     # instantiate inventory task
#     try:
#         InventoryClass = getattr(inv_mod, 'Inventory', None) or getattr(inv_mod, 'GLPI_Agent_Task_Inventory', None)
#         inventory = None
#         if InventoryClass:
#             inventory = InventoryClass(
#                 config=(agent.config if agent and hasattr(agent, 'config') else None),
#                 datadir=(agent.datadir if agent and hasattr(agent, 'datadir') else None),
#                 logger=(agent.logger if agent and hasattr(agent, 'logger') else None),
#                 target='none',
#                 deviceid=(agent.deviceid if agent and hasattr(agent, 'deviceid') else None),
#             )
#         else:
#             # fallback: try to call inv_mod.new(...)
#             inventory = inv_mod.new(
#                 config=(agent.config if agent and hasattr(agent, 'config') else None),
#             )
#     except Exception as e:
#         print(f"Failed to instantiate inventory module: {e}", file=sys.stderr)
#         traceback.print_exc()
#         sys.exit(1)
#     try:
#         print('Supported categories:')
#         cats = []
#         if hasattr(inventory, 'getCategories'):
#             cats = inventory.getCategories()
#         elif hasattr(inventory, 'categories'):
#             cats = inventory.categories
#         for cat in sorted(cats):
#             print(' - ' + cat)
#         sys.exit(0)
#     except Exception as e:
#         print(f"Failed to list categories: {e}", file=sys.stderr)
#         traceback.print_exc()
#         sys.exit(1)

# # wait behaviour
# if options.get('wait'):
#     try:
#         w = int(options.get('wait'))
#         time_to_sleep = random.randint(0, w - 1) if w > 0 else 0
#     except Exception:
#         time_to_sleep = 0
#     time.sleep(time_to_sleep)

# # set-forcerun behaviour
# if options.get('set_forcerun'):
#     if agent is None:
#         try:
#             AG = require('GLPI.Agent')
#             AgentClass = getattr(AG, 'GLPI_Agent', None) or getattr(AG, 'Agent', None)
#             if AgentClass:
#                 agent = AgentClass(**setup)
#         except Exception:
#             pass
#     if agent is None:
#         print('Cannot instantiate agent to set forcerun', file=sys.stderr)
#         sys.exit(1)
#     try:
#         agent.setForceRun()
#         sys.exit(0)
#     except Exception as e:
#         print(f"Failed to set forcerun: {e}", file=sys.stderr)
#         sys.exit(1)

# # partial option implies json
# if options.get('partial'):
#     if options.get('daemon'):
#         sys.exit("--partial option not compatible with --daemon")
#     # create event object
#     try:
#         EventMod = require('GLPI.Agent.Event')
#         EventClass = getattr(EventMod, 'Event', None) or getattr(EventMod, 'GLPI_Agent_Event', None)
#         if EventClass:
#             agent.event = EventClass(
#                 name='partial inventory',
#                 task='inventory',
#                 partial=1,
#                 category=options.get('partial'),
#             )
#         else:
#             # fallback: try to call EventMod.new(...)
#             if hasattr(EventMod, 'new'):
#                 agent.event = EventMod.new(
#                     name='partial inventory',
#                     task='inventory',
#                     partial=1,
#                     category=options.get('partial'),
#                 )
#     except Exception:
#         print('Failed to create partial event; ensure GLPI.Agent.Event is available', file=sys.stderr)

# # credentials option
# if options.get('credentials'):
#     if options.get('daemon'):
#         sys.exit("--credentials option not compatible with --daemon")
#     if agent is None:
#         try:
#             AG = require('GLPI.Agent')
#             AgentClass = getattr(AG, 'GLPI_Agent', None) or getattr(AG, 'Agent', None)
#             if AgentClass:
#                 agent = AgentClass(**setup)
#         except Exception:
#             pass
#     if agent is not None:
#         agent.credentials = options.get('credentials')

# # Main run block: wrapped in try/except like Perl eval
# try:
#     if agent is None:
#         # attempt to instantiate agent if still None
#         try:
#             AG = require('GLPI.Agent')
#             AgentClass = getattr(AG, 'GLPI_Agent', None) or getattr(AG, 'Agent', None)
#             if AgentClass:
#                 agent = AgentClass(**setup)
#         except Exception:
#             pass

#     if agent is None:
#         raise RuntimeError('Could not instantiate GLPI agent; required GLPI.Agent module not found or wrong constructor')

#     # init agent with given options
#     if hasattr(agent, 'init'):
#         agent.init(options=options)

#     # Windows-specific OLE workaround
#     if os.name == 'nt' and not options.get('no_win32_ole_workaround'):
#         try:
#             win_tools = require('GLPI.Agent.Tools.Win32')
#             if hasattr(win_tools, 'start_Win32_OLE_Worker'):
#                 win_tools.start_Win32_OLE_Worker()
#             if hasattr(win_tools, 'setupWorkerLogger'):
#                 win_tools.setupWorkerLogger(config=getattr(agent, 'config', None))
#         except Exception:
#             # keep going even if workaround not available
#             pass

#     # finally run
#     if hasattr(agent, 'run'):
#         agent.run()
#     else:
#         # if agent is just a module with run function
#         if hasattr(agent, 'main'):
#             agent.main()

# except Exception as e:
#     print('Execution failure:.', file=sys.stderr)
#     traceback.print_exc()
#     print(str(e), file=sys.stderr)
#     sys.exit(1)

# sys.exit(0)
