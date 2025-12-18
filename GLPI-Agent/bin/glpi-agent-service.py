#!/usr/bin/env python3
"""
GLPI Agent Windows Service
Runs continuously in the background and collects inventory every 24 hours
"""

import sys
import os
import time
import threading
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Add lib directory to path
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    base_path = Path(sys._MEIPASS)
    script_dir = Path(sys.executable).parent
else:
    # Running as script
    script_dir = Path(__file__).parent.parent.resolve()
    base_path = script_dir

lib_dir = base_path / 'lib'
# Add lib directory to Python path - must be first
if str(lib_dir) not in sys.path:
    sys.path.insert(0, str(lib_dir))
# Also add parent of lib (in case of relative imports)
if str(base_path) not in sys.path:
    sys.path.insert(0, str(base_path))

try:
    import setup
    sys.path.insert(0, setup.setup.get('libdir', str(lib_dir)))
    SETUP_CONFIG = setup.setup.copy()
    # Ensure vardir is an absolute path
    if 'vardir' in SETUP_CONFIG:
        SETUP_CONFIG['vardir'] = str(Path(SETUP_CONFIG['vardir']).resolve())
except ImportError:
    SETUP_CONFIG = {
        'libdir': str(lib_dir),
        'datadir': str(base_path / 'share'),
        'vardir': str((script_dir / 'var').resolve())  # Use absolute path
    }

# Import GLPI Agent
try:
    from GLPI.Agent import GLPIAgent
except ImportError as e:
    print(f"Error: Could not import GLPI Agent: {e}", file=sys.stderr)
    sys.exit(1)

# Windows service imports
try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
except ImportError:
    print("ERROR: pywin32 module is required for Windows service support")
    print("Install it with: pip install pywin32")
    sys.exit(1)


class GLPIAgentService(win32serviceutil.ServiceFramework):
    """Windows Service for GLPI Agent"""
    
    _svc_name_ = "GLPIAgent"
    _svc_display_name_ = "GLPI Agent Service"
    _svc_description_ = "GLPI Agent service that collects and sends inventory data every 24 hours"
    
    def __init__(self, args):
        try:
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            self.stop_requested = False
            self.inventory_thread = None
            self.config_file = None
            self.server_url = None
            self.last_run_time = None
            self.inventory_interval = 24 * 60 * 60  # 24 hours in seconds
            self.logger = None
            # Force write a diagnostic file to temp directory (most reliable location)
            # Try multiple locations in case one fails
            diag_written = False
            for temp_path in [
                os.environ.get('TEMP', 'C:\\Temp'),
                os.environ.get('TMP', 'C:\\Temp'),
                'C:\\Temp',
                str(Path.home() / 'AppData' / 'Local' / 'Temp')
            ]:
                try:
                    temp_dir = Path(temp_path)
                    if temp_dir.exists():
                        diag_file = temp_dir / 'glpi-agent-service-diag.txt'
                        with open(diag_file, 'w') as f:
                            f.write(f"Service initialization at {datetime.now()}\n")
                            f.write(f"script_dir: {script_dir}\n")
                            f.write(f"sys.executable: {sys.executable}\n")
                            f.write(f"vardir: {SETUP_CONFIG.get('vardir', 'NOT SET')}\n")
                            f.write(f"frozen: {getattr(sys, 'frozen', False)}\n")
                            if getattr(sys, 'frozen', False):
                                f.write(f"_MEIPASS: {sys._MEIPASS}\n")
                            f.write(f"TEMP env: {os.environ.get('TEMP', 'NOT SET')}\n")
                        diag_written = True
                        break
                except Exception:
                    continue
            if not diag_written:
                # Last resort: try C:\Windows\Temp
                try:
                    diag_file = Path('C:\\Windows\\Temp') / 'glpi-agent-service-diag.txt'
                    with open(diag_file, 'w') as f:
                        f.write(f"Service initialization at {datetime.now()}\n")
                        f.write("Note: Could not write to user temp, using C:\\Windows\\Temp\n")
                except:
                    pass
            self.setup_logging()
        except Exception as e:
            # Try to log error even if logging setup failed
            try:
                import traceback
                error_file = Path(os.environ.get('TEMP', 'C:\\Temp')) / 'glpi-agent-service-init-error.txt'
                with open(error_file, 'w') as f:
                    f.write(f"Service initialization error: {e}\n")
                    f.write(traceback.format_exc())
            except:
                pass
            raise
        
    def setup_logging(self):
        """Setup logging for the service"""
        try:
            # Use absolute path to avoid working directory issues
            vardir = SETUP_CONFIG.get('vardir', str((script_dir / 'var').resolve()))
            # Ensure vardir is absolute
            if not Path(vardir).is_absolute():
                vardir = str((script_dir / vardir).resolve())
            log_dir = Path(vardir).resolve() / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            
            log_file = log_dir.resolve() / 'glpi-agent-service.log'
            
            # Verify we can write to the directory
            try:
                test_file = log_dir / '.write-test'
                test_file.write_text('test')
                test_file.unlink()
            except Exception as perm_error:
                # If we can't write, try using temp directory
                log_dir = Path(os.environ.get('TEMP', 'C:\\Temp')) / 'glpi-agent-logs'
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = log_dir / 'glpi-agent-service.log'
            
            # Clear any existing handlers to avoid duplicates
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            # Create file handler with explicit error handling
            try:
                # Ensure the log file can be created by touching it first
                log_file.parent.mkdir(parents=True, exist_ok=True)
                log_file.touch(exist_ok=True)
                
                file_handler = logging.FileHandler(str(log_file), mode='a', encoding='utf-8')
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            except Exception as e:
                # If file handler fails, try to write error to temp file
                error_file = Path(os.environ.get('TEMP', 'C:\\Temp')) / 'glpi-agent-logging-error.txt'
                try:
                    with open(error_file, 'w') as f:
                        f.write(f"Failed to create log file handler: {e}\n")
                        f.write(f"Log file path: {log_file}\n")
                        f.write(f"Log directory: {log_dir}\n")
                        f.write(f"Directory exists: {log_dir.exists()}\n")
                except:
                    pass
                raise
            
            # Create stream handler for console output
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(logging.INFO)
            stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            
            # Configure root logger
            root_logger.setLevel(logging.INFO)
            root_logger.addHandler(file_handler)
            root_logger.addHandler(stream_handler)
            
            self.logger = logging.getLogger('GLPIAgentService')
            # Force a test write to verify logging works
            self.logger.info(f"Logging initialized. Log file: {log_file}")
            self.logger.info(f"Service starting - script_dir: {script_dir}, vardir: {vardir}")
            # Force flush to ensure the message is written
            for handler in self.logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    handler.flush()
            
        except Exception as e:
            # Last resort: try to write to temp file
            error_file = Path(os.environ.get('TEMP', 'C:\\Temp')) / 'glpi-agent-setup-logging-error.txt'
            try:
                with open(error_file, 'w') as f:
                    import traceback
                    f.write(f"Failed to setup logging: {e}\n")
                    f.write(traceback.format_exc())
                    f.write(f"\nvardir: {SETUP_CONFIG.get('vardir', 'NOT SET')}\n")
                    f.write(f"script_dir: {script_dir}\n")
            except:
                pass
            # Create a minimal logger that at least works
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
            self.logger = logging.getLogger('GLPIAgentService')
            self.logger.error(f"Failed to setup file logging: {e}")
        
    def load_config(self):
        """Load configuration from file"""
        # Try multiple locations for config file
        possible_configs = [
            script_dir / 'glpi-agent-service.json',  # Development/script mode
            Path(sys.executable).parent / 'glpi-agent-service.json',  # Installed service
            Path(os.environ.get('ProgramFiles', 'C:\\Program Files')) / 'GLPI-Agent' / 'glpi-agent-service.json',  # Standard install
        ]
        
        config_file = None
        for cfg_path in possible_configs:
            if cfg_path.exists():
                config_file = cfg_path
                break
        
        if not config_file:
            # Use the first possible location as default
            config_file = possible_configs[0]
        
        self.config_file = config_file
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    self.server_url = config.get('server_url')
                    self.inventory_interval = config.get('inventory_interval', 24 * 60 * 60)
                    self.logger.info(f"Loaded configuration from {config_file}: server={self.server_url}, interval={self.inventory_interval}s")
            except Exception as e:
                self.logger.error(f"Error loading config: {e}")
                # Use default config
                self.create_default_config()
        else:
            self.logger.warning(f"Config file not found at {config_file}, creating default")
            self.create_default_config()
            
    def create_default_config(self):
        """Create default configuration file"""
        if not self.config_file:
            self.config_file = script_dir / 'glpi-agent-service.json'
            
        default_config = {
            "server_url": "http://your-server.com/glpi/front/inventory.php",
            "inventory_interval": 86400,  # 24 hours in seconds
            "description": "GLPI Agent Service Configuration"
        }
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(default_config, f, indent=4)
            self.logger.info(f"Created default config file: {self.config_file}")
            self.server_url = default_config['server_url']
            self.inventory_interval = default_config['inventory_interval']
        except Exception as e:
            self.logger.error(f"Error creating config file: {e}")
            
    def SvcStop(self):
        """Stop the service"""
        self.logger.info("Service stop requested")
        self.stop_requested = True
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        
    def SvcDoRun(self):
        """Main service execution"""
        try:
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, '')
            )
            self.logger.info("GLPI Agent Service started")
            
            # Load configuration
            try:
                self.load_config()
            except Exception as e:
                self.logger.error(f"Failed to load configuration: {e}", exc_info=True)
                servicemanager.LogErrorMsg(f"Failed to load configuration: {e}")
                # Continue anyway with defaults
            
            # Check if server URL is configured
            if not self.server_url or self.server_url == "http://your-server.com/glpi/front/inventory.php":
                self.logger.warning("Server URL not configured! Please edit glpi-agent-service.json")
                self.logger.warning("Service will start but will not collect inventory until configured.")
                servicemanager.LogErrorMsg("Server URL not configured in glpi-agent-service.json - Service running but idle")
                # Don't return - let the service run so it can be configured
                # Just wait in the loop without running inventory
            
            # Run initial inventory if configured
            if self.server_url and self.server_url != "http://your-server.com/glpi/front/inventory.php":
                try:
                    self.run_inventory()
                    self.last_run_time = time.time()
                except Exception as e:
                    self.logger.error(f"Failed to run initial inventory: {e}", exc_info=True)
                    self.last_run_time = time.time()  # Set anyway so loop can continue
            
            # Main service loop
            while not self.stop_requested:
                try:
                    # Check if it's time to run inventory (only if configured)
                    if self.server_url and self.server_url != "http://your-server.com/glpi/front/inventory.php":
                        current_time = time.time()
                        time_since_last_run = current_time - self.last_run_time
                        
                        if time_since_last_run >= self.inventory_interval:
                            self.logger.info(f"24 hours elapsed, running inventory collection")
                            try:
                                self.run_inventory()
                                self.last_run_time = current_time
                            except Exception as e:
                                self.logger.error(f"Failed to run inventory: {e}", exc_info=True)
                                self.last_run_time = current_time  # Update time to avoid rapid retries
                    
                    # Wait for stop event or timeout (check every minute)
                    wait_result = win32event.WaitForSingleObject(
                        self.stop_event,
                        60000  # 1 minute timeout
                    )
                    
                    if wait_result == win32event.WAIT_OBJECT_0:
                        # Stop event was signaled
                        break
                        
                except Exception as e:
                    self.logger.error(f"Error in service loop: {e}", exc_info=True)
                    time.sleep(60)  # Wait before retrying
            
            self.logger.info("GLPI Agent Service stopped")
        except Exception as e:
            error_msg = f"Fatal error in service: {e}"
            try:
                self.logger.error(error_msg, exc_info=True)
            except:
                pass
            servicemanager.LogErrorMsg(error_msg)
            raise
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, '')
        )
        
    def run_inventory(self):
        """Run inventory collection and send to server"""
        if self.inventory_thread and self.inventory_thread.is_alive():
            self.logger.warning("Inventory collection already in progress, skipping")
            return
            
        def inventory_worker():
            """Worker thread for inventory collection"""
            try:
                self.logger.info(f"Starting inventory collection for server: {self.server_url}")
                
                # Create agent instance
                datadir = SETUP_CONFIG.get('datadir', str(base_path / 'share'))
                libdir = SETUP_CONFIG.get('libdir', str(base_path / 'lib'))
                vardir = SETUP_CONFIG.get('vardir', str(script_dir / 'var'))
                
                # Ensure directories exist
                os.makedirs(vardir, exist_ok=True)
                
                agent = GLPIAgent(
                    datadir=datadir,
                    libdir=libdir,
                    vardir=vardir
                )
                
                # Initialize with server option
                options = {
                    'server': [self.server_url],
                    'force': True,
                    'no-task': []
                }
                
                agent.init(options=options)
                
                self.logger.info("Collecting system inventory...")
                agent.run()
                
                self.logger.info("✅ Inventory successfully sent to server!")
                
            except Exception as e:
                self.logger.error(f"❌ Error during inventory collection: {e}", exc_info=True)
        
        # Start inventory collection in a separate thread
        self.inventory_thread = threading.Thread(target=inventory_worker, daemon=True)
        self.inventory_thread.start()
        
        # Wait for completion (with timeout)
        self.inventory_thread.join(timeout=3600)  # 1 hour timeout
        
        if self.inventory_thread.is_alive():
            self.logger.warning("Inventory collection timed out after 1 hour")


def main():
    """Main entry point for service installation/removal"""
    if len(sys.argv) == 1:
        # Running as service - only works when started by Windows Service Manager
        try:
            servicemanager.Initialize()
            servicemanager.PrepareToHostSingle(GLPIAgentService)
            servicemanager.StartServiceCtrlDispatcher()
        except Exception as e:
            print(f"\n{'='*60}")
            print("GLPI Agent Service - Error")
            print("="*60)
            print(f"Error: Service can only be started by Windows Service Manager.")
            print(f"\nTo install the service, run:")
            print(f"  {sys.argv[0]} install")
            print(f"\nTo start the service, run:")
            print(f"  net start GLPIAgent")
            print(f"\nError details: {e}")
            print("="*60)
            # Pause so user can read the error
            try:
                input("\nPress Enter to exit...")
            except:
                import time
                time.sleep(10)  # Wait 10 seconds if input doesn't work
            sys.exit(1)
    else:
        # Handle service commands (install, remove, start, stop, etc.)
        try:
            win32serviceutil.HandleCommandLine(GLPIAgentService)
        except Exception as e:
            print(f"\n{'='*60}")
            print("GLPI Agent Service - Error")
            print("="*60)
            print(f"Error: {e}")
            print("="*60)
            # Pause so user can read the error
            try:
                input("\nPress Enter to exit...")
            except:
                import time
                time.sleep(10)  # Wait 10 seconds if input doesn't work
            sys.exit(1)


if __name__ == '__main__':
    main()

