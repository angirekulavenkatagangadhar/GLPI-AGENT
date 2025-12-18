#!/usr/bin/env python3
"""
GLPI Agent GUI Application with Background Service
Interactive UI where user can enter server URL and start background collection every 24 hours
"""

import sys
import os
import time
import json
import threading
from pathlib import Path
from datetime import datetime, timedelta

# Add lib directory to path
if getattr(sys, 'frozen', False):
    base_path = Path(sys._MEIPASS)
    script_dir = Path(sys.executable).parent
else:
    script_dir = Path(__file__).parent.parent.resolve()
    base_path = script_dir

lib_dir = base_path / 'lib'
if str(lib_dir) not in sys.path:
    sys.path.insert(0, str(lib_dir))
if str(base_path) not in sys.path:
    sys.path.insert(0, str(base_path))

try:
    import setup
    sys.path.insert(0, setup.setup.get('libdir', str(lib_dir)))
    SETUP_CONFIG = setup.setup.copy()
except ImportError:
    SETUP_CONFIG = {
        'libdir': str(lib_dir),
        'datadir': str(base_path / 'share'),
        'vardir': str(script_dir / 'var')
    }

# Import GLPI Agent
try:
    from GLPI.Agent import GLPIAgent
except ImportError as e:
    print(f"Error: Could not import GLPI Agent: {e}", file=sys.stderr)
    sys.exit(1)

# GUI imports
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext
except ImportError:
    print("Error: tkinter not available. Please install Python with tkinter support.", file=sys.stderr)
    sys.exit(1)


class BackgroundCollector:
    """Background inventory collector that runs every 24 hours"""
    
    def __init__(self, server_url, log_callback, status_callback):
        self.server_url = server_url
        self.log_callback = log_callback
        self.status_callback = status_callback
        self.running = False
        self.thread = None
        self.stop_event = threading.Event()
        self.inventory_interval = 24 * 60 * 60  # 24 hours in seconds
        self.last_run_time = None
        self.is_collecting = False
        
    def start(self):
        """Start the background collector"""
        if self.running:
            return False
        
        self.running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.log_callback("Background service started. Will collect inventory every 24 hours.", "INFO")
        return True
    
    def stop(self):
        """Stop the background collector"""
        if not self.running:
            return False
        
        self.running = False
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.log_callback("Background service stopped.", "INFO")
        return True
    
    def _run_loop(self):
        """Main background loop"""
        # Run initial inventory
        self._run_inventory()
        self.last_run_time = time.time()
        
        # Main loop - check every minute
        while self.running and not self.stop_event.is_set():
            try:
                current_time = time.time()
                time_since_last_run = current_time - self.last_run_time
                
                if time_since_last_run >= self.inventory_interval:
                    self._run_inventory()
                    self.last_run_time = current_time
                
                # Wait 1 minute before checking again
                self.stop_event.wait(60)
                
            except Exception as e:
                self.log_callback(f"Error in background loop: {e}", "ERROR")
                time.sleep(60)  # Wait before retrying
    
    def _run_inventory(self):
        """Run inventory collection"""
        if self.is_collecting:
            self.log_callback("Inventory collection already in progress, skipping...", "WARNING")
            return
        
        self.is_collecting = True
        try:
            self.log_callback("=" * 60, "INFO")
            self.log_callback(f"Starting scheduled inventory collection...", "INFO")
            self.log_callback(f"Server: {self.server_url}", "INFO")
            self.status_callback("Collecting inventory (background)...")
            
            # Create agent instance
            if getattr(sys, 'frozen', False):
                base_path = Path(sys._MEIPASS)
                exe_dir = Path(sys.executable).parent
            else:
                base_path = Path(__file__).parent.parent.resolve()
                exe_dir = base_path
            
            datadir = SETUP_CONFIG.get('datadir', str(base_path / 'share'))
            libdir = SETUP_CONFIG.get('libdir', str(base_path / 'lib'))
            vardir = SETUP_CONFIG.get('vardir', str(exe_dir / 'var'))
            
            os.makedirs(vardir, exist_ok=True)
            
            agent = GLPIAgent(
                datadir=datadir,
                libdir=libdir,
                vardir=vardir
            )
            
            options = {
                'server': [self.server_url],
                'force': True,
                'no-task': []
            }
            
            agent.init(options=options)
            agent.run()
            
            self.log_callback("✅ Inventory successfully sent to server!", "SUCCESS")
            next_run = datetime.now() + timedelta(seconds=self.inventory_interval)
            self.log_callback(f"Next collection scheduled for: {next_run.strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
            self.status_callback("Background service running - Last collection successful")
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            self.log_callback(f"❌ Error during inventory collection: {error_msg}", "ERROR")
            self.log_callback(f"Traceback: {traceback.format_exc()}", "ERROR")
            self.status_callback(f"Background service running - Last collection failed: {error_msg[:50]}")
        finally:
            self.is_collecting = False


class GLPIAgentBackgroundGUI:
    """GUI Application with Background Service"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("GLPI Agent - Background Inventory Service")
        self.root.geometry("800x700")
        self.root.resizable(True, True)
        
        # Configuration file
        self.config_file = script_dir / 'glpi-agent-config.json'
        
        # Variables
        self.server_url = tk.StringVar()
        self.background_running = False
        self.background_collector = None
        self.is_manual_running = False
        
        # Load saved configuration
        self.load_config()
        
        # Setup GUI
        self.setup_ui()
        self.center_window()
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Update status periodically
        self.update_status_display()
    
    def center_window(self):
        """Center the window on screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def load_config(self):
        """Load saved configuration"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.server_url.set(config.get('server_url', 'http://'))
            except Exception as e:
                print(f"Error loading config: {e}")
                self.server_url.set('http://')
        else:
            self.server_url.set('http://')
    
    def save_config(self):
        """Save configuration to file"""
        try:
            config = {
                'server_url': self.server_url.get().strip(),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            self.log(f"Error saving config: {e}", "ERROR")
    
    def setup_ui(self):
        """Setup the user interface"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Title
        title_label = ttk.Label(
            main_frame,
            text="GLPI Agent - Background Inventory Service",
            font=("Arial", 16, "bold")
        )
        title_label.grid(row=0, column=0, pady=(0, 10))
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        main_frame.rowconfigure(1, weight=1)
        
        # Tab 1: Main/Service tab
        self.service_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.service_tab, text="Service")
        self.setup_service_tab()
        
        # Tab 2: Connections tab
        self.connections_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.connections_tab, text="Connections")
        self.setup_connections_tab()
    
    def setup_service_tab(self):
        """Setup the service/main tab"""
        main_frame = self.service_tab
        
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)
        
        # Server address section
        server_frame = ttk.LabelFrame(main_frame, text="Server Configuration", padding="10")
        server_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        server_frame.columnconfigure(1, weight=1)
        
        ttk.Label(server_frame, text="Server URL:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        server_entry = ttk.Entry(server_frame, textvariable=self.server_url, width=50)
        server_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))
        
        example_label = ttk.Label(
            server_frame,
            text="Example: http://server.domain.com/glpi/front/inventory.php or http://192.168.1.100:80",
            font=("Arial", 8),
            foreground="gray"
        )
        example_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        
        # Background service section
        service_frame = ttk.LabelFrame(main_frame, text="Background Service (24-Hour Collection)", padding="10")
        service_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        service_info = ttk.Label(
            service_frame,
            text="The background service will automatically collect and send inventory every 24 hours.",
            font=("Arial", 9),
            foreground="darkblue"
        )
        service_info.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        
        button_frame = ttk.Frame(service_frame)
        button_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W)
        
        self.start_service_button = ttk.Button(
            button_frame,
            text="▶ Start Background Service",
            command=self.start_background_service,
            width=25
        )
        self.start_service_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_service_button = ttk.Button(
            button_frame,
            text="⏹ Stop Background Service",
            command=self.stop_background_service,
            width=25,
            state=tk.DISABLED
        )
        self.stop_service_button.pack(side=tk.LEFT, padx=5)
        
        self.service_status_label = ttk.Label(
            service_frame,
            text="Status: Stopped",
            font=("Arial", 9, "bold"),
            foreground="red"
        )
        self.service_status_label.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))
        
        # Manual collection section
        manual_frame = ttk.LabelFrame(main_frame, text="Manual Collection", padding="10")
        manual_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.send_button = ttk.Button(
            manual_frame,
            text="Send Inventory Now",
            command=self.send_inventory_manual,
            width=30
        )
        self.send_button.pack()
        
        # Status/Log section
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=15,
            width=80,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 9)
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Status bar
        self.status_label = ttk.Label(
            main_frame,
            text="Ready - Enter server URL and start background service",
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding="5"
        )
        self.status_label.grid(row=4, column=0, sticky=(tk.W, tk.E))
        
        # Initial log message
        self.log("Application started. Configure server URL and start background service.", "INFO")
    
    def setup_connections_tab(self):
        """Setup the connections tab to show monitors, printers, etc."""
        main_frame = self.connections_tab
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Header with refresh button
        header_frame = ttk.Frame(main_frame)
        header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(
            header_frame,
            text="Connected Devices",
            font=("Arial", 14, "bold")
        ).pack(side=tk.LEFT, padx=(0, 20))
        
        refresh_button = ttk.Button(
            header_frame,
            text="🔄 Refresh",
            command=self.refresh_connections,
            width=15
        )
        refresh_button.pack(side=tk.LEFT)
        
        # Treeview for displaying devices
        tree_frame = ttk.Frame(main_frame)
        tree_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        
        # Create treeview with scrollbars
        tree_scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        
        self.connections_tree = ttk.Treeview(
            tree_frame,
            columns=("Details",),
            show="tree headings",
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set
        )
        
        tree_scroll_y.config(command=self.connections_tree.yview)
        tree_scroll_x.config(command=self.connections_tree.xview)
        
        # Configure columns
        self.connections_tree.heading("#0", text="Device", anchor=tk.W)
        self.connections_tree.heading("Details", text="Details", anchor=tk.W)
        self.connections_tree.column("#0", width=250, minwidth=200)
        self.connections_tree.column("Details", width=400, minwidth=300)
        
        # Pack treeview and scrollbars
        self.connections_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        tree_scroll_y.grid(row=0, column=1, sticky=(tk.N, tk.S))
        tree_scroll_x.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        # Status label
        self.connections_status = ttk.Label(
            main_frame,
            text="Click 'Refresh' to scan for connected devices",
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding="5"
        )
        self.connections_status.grid(row=2, column=0, sticky=(tk.W, tk.E))
        
        # Auto-refresh on tab open
        self.refresh_connections()
    
    def log(self, message, level="INFO"):
        """Add message to log"""
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()
    
    def update_status(self, message):
        """Update status bar"""
        self.status_label.config(text=message)
        self.root.update_idletasks()
    
    def update_status_display(self):
        """Update service status display periodically"""
        if self.background_running:
            self.service_status_label.config(text="Status: Running", foreground="green")
            self.start_service_button.config(state=tk.DISABLED)
            self.stop_service_button.config(state=tk.NORMAL)
        else:
            self.service_status_label.config(text="Status: Stopped", foreground="red")
            self.start_service_button.config(state=tk.NORMAL)
            self.stop_service_button.config(state=tk.DISABLED)
        
        # Schedule next update
        self.root.after(1000, self.update_status_display)
    
    def validate_server_url(self):
        """Validate server URL"""
        server_url = self.server_url.get().strip()
        if not server_url or server_url == "http://":
            messagebox.showerror("Error", "Please enter a valid server URL.")
            return None
        
        if not (server_url.startswith("http://") or server_url.startswith("https://")):
            messagebox.showerror("Error", "Server URL must start with http:// or https://")
            return None
        
        return server_url
    
    def start_background_service(self):
        """Start the background service"""
        server_url = self.validate_server_url()
        if not server_url:
            return
        
        if self.background_running:
            messagebox.showwarning("Warning", "Background service is already running.")
            return
        
        # Save configuration
        self.save_config()
        
        # Create and start background collector
        self.background_collector = BackgroundCollector(
            server_url,
            self.log,
            self.update_status
        )
        
        if self.background_collector.start():
            self.background_running = True
            self.log(f"Background service started with server: {server_url}", "SUCCESS")
            self.update_status("Background service running - Will collect inventory every 24 hours")
            messagebox.showinfo("Success", 
                "Background service started!\n\n"
                "The service will:\n"
                "• Collect inventory immediately\n"
                "• Run automatically every 24 hours\n"
                "• Continue running in the background\n\n"
                "You can minimize this window, but keep it running.")
        else:
            messagebox.showerror("Error", "Failed to start background service.")
    
    def stop_background_service(self):
        """Stop the background service"""
        if not self.background_running:
            return
        
        if messagebox.askyesno("Confirm", "Stop the background service?"):
            if self.background_collector and self.background_collector.stop():
                self.background_running = False
                self.background_collector = None
                self.log("Background service stopped by user.", "INFO")
                self.update_status("Background service stopped")
            else:
                messagebox.showerror("Error", "Failed to stop background service.")
    
    def send_inventory_manual(self):
        """Send inventory manually (one-time)"""
        if self.is_manual_running:
            messagebox.showwarning("Warning", "Manual inventory collection is already in progress.")
            return
        
        server_url = self.validate_server_url()
        if not server_url:
            return
        
        # Save configuration
        self.save_config()
        
        # Run in separate thread
        thread = threading.Thread(target=self._send_inventory_thread, args=(server_url,), daemon=True)
        thread.start()
    
    def _send_inventory_thread(self, server_url):
        """Send inventory in background thread"""
        self.is_manual_running = True
        self.send_button.config(state=tk.DISABLED)
        self.update_status("Collecting inventory manually...")
        
        try:
            self.log("=" * 60, "INFO")
            self.log(f"Starting manual inventory collection...", "INFO")
            self.log(f"Server: {server_url}", "INFO")
            
            if getattr(sys, 'frozen', False):
                base_path = Path(sys._MEIPASS)
                exe_dir = Path(sys.executable).parent
            else:
                base_path = Path(__file__).parent.parent.resolve()
                exe_dir = base_path
            
            datadir = SETUP_CONFIG.get('datadir', str(base_path / 'share'))
            libdir = SETUP_CONFIG.get('libdir', str(base_path / 'lib'))
            vardir = SETUP_CONFIG.get('vardir', str(exe_dir / 'var'))
            
            os.makedirs(vardir, exist_ok=True)
            
            agent = GLPIAgent(
                datadir=datadir,
                libdir=libdir,
                vardir=vardir
            )
            
            options = {
                'server': [server_url],
                'force': True,
                'no-task': []
            }
            
            self.log("Initializing agent...", "INFO")
            agent.init(options=options)
            
            self.log("Collecting system inventory...", "INFO")
            self.update_status("Collecting inventory data...")
            
            agent.run()
            
            self.log("✅ Inventory successfully sent to server!", "SUCCESS")
            self.update_status("Manual inventory sent successfully!")
            messagebox.showinfo("Success", f"Inventory successfully sent to:\n{server_url}")
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            self.log(f"❌ Error: {error_msg}", "ERROR")
            self.log(f"Traceback:\n{traceback.format_exc()}", "ERROR")
            self.update_status(f"Error: {error_msg}")
            messagebox.showerror("Error", f"Failed to send inventory:\n{error_msg}\n\nSee log for details.")
        
        finally:
            self.is_manual_running = False
            self.send_button.config(state=tk.NORMAL)
            if not self.is_manual_running:
                self.update_status("Ready")
    
    def refresh_connections(self):
        """Refresh the connections display"""
        self.connections_status.config(text="Scanning for connected devices...")
        self.root.update_idletasks()
        
        # Clear existing items
        for item in self.connections_tree.get_children():
            self.connections_tree.delete(item)
        
        # Run in separate thread to avoid freezing UI
        thread = threading.Thread(target=self._collect_connections_thread, daemon=True)
        thread.start()
    
    def _collect_connections_thread(self):
        """Collect connection information in background thread"""
        try:
            import subprocess
            import json as json_lib
            
            # Collect monitors
            monitors = self._get_monitors()
            
            # Collect printers
            printers = self._get_printers()
            
            # Collect USB devices
            usb_devices = self._get_usb_devices()
            
            # Update UI in main thread
            self.root.after(0, self._update_connections_tree, monitors, printers, usb_devices)
            
        except Exception as e:
            import traceback
            error_msg = f"Error collecting connections: {e}"
            self.root.after(0, lambda: self.connections_status.config(
                text=f"Error: {error_msg}"
            ))
    
    def _get_monitors(self):
        """Get monitor information using PowerShell"""
        try:
            import subprocess
            import json as json_lib
            
            ps_script = '''
            $monitors = @()
            try {
                $desktopMonitors = Get-CimInstance Win32_DesktopMonitor -ErrorAction SilentlyContinue | Where-Object { $_.Availability -eq 3 -or $_.Availability -eq $null }
                if (-not $desktopMonitors) {
                    $desktopMonitors = Get-CimInstance Win32_DesktopMonitor -ErrorAction SilentlyContinue
                }
                
                $monitorIDs = Get-CimInstance -Namespace root\\wmi WmiMonitorID -ErrorAction SilentlyContinue
                
                foreach ($mon in $desktopMonitors) {
                    $monitorID = $monitorIDs | Where-Object { $_.InstanceName -like "*$($mon.PNPDeviceID)*" } | Select-Object -First 1
                    
                    $manufacturer = if ($monitorID) {
                        [System.Text.Encoding]::ASCII.GetString($monitorID.ManufacturerName -ne 0 | ForEach-Object {[byte]$_})
                    } else {
                        $mon.MonitorManufacturer
                    }
                    
                    $product = if ($monitorID) {
                        [System.Text.Encoding]::ASCII.GetString($monitorID.ProductCodeID -ne 0 | ForEach-Object {[byte]$_})
                    } else {
                        $mon.MonitorType
                    }
                    
                    $serial = if ($monitorID) {
                        [System.Text.Encoding]::ASCII.GetString($monitorID.SerialNumberID -ne 0 | ForEach-Object {[byte]$_})
                    } else {
                        ""
                    }
                    
                    $monitors += [PSCustomObject]@{
                        Name = $mon.Caption
                        Manufacturer = if ($manufacturer) { $manufacturer } else { "Unknown" }
                        Model = if ($product) { $product } else { "Unknown" }
                        Serial = if ($serial) { $serial } else { "N/A" }
                        PNPDeviceID = $mon.PNPDeviceID
                    }
                }
            } catch {
                # Fallback: just get basic info
                $monitors = Get-CimInstance Win32_DesktopMonitor -ErrorAction SilentlyContinue | ForEach-Object {
                    [PSCustomObject]@{
                        Name = $_.Caption
                        Manufacturer = if ($_.MonitorManufacturer) { $_.MonitorManufacturer } else { "Unknown" }
                        Model = if ($_.MonitorType) { $_.MonitorType } else { "Unknown" }
                        Serial = "N/A"
                        PNPDeviceID = $_.PNPDeviceID
                    }
                }
            }
            $monitors | ConvertTo-Json -Depth 10
            '''
            
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout.strip():
                monitors = json_lib.loads(result.stdout)
                if not isinstance(monitors, list):
                    monitors = [monitors] if monitors else []
                return monitors
            return []
        except Exception as e:
            return []
    
    def _get_printers(self):
        """Get printer information using PowerShell"""
        try:
            import subprocess
            import json as json_lib
            
            ps_script = '''
            $printers = Get-CimInstance Win32_Printer -ErrorAction SilentlyContinue | Where-Object { $_.Name -and $_.PortName } | ForEach-Object {
                # Try to get manufacturer from PNP device
                $manufacturer = "Unknown"
                if ($_.PNPDeviceID) {
                    try {
                        $pnpDevice = Get-CimInstance Win32_PnPEntity -Filter "PNPDeviceID='$($_.PNPDeviceID)'" -ErrorAction SilentlyContinue
                        if ($pnpDevice -and $pnpDevice.Manufacturer) {
                            $manufacturer = $pnpDevice.Manufacturer
                        }
                    } catch { }
                }
                
                # If still unknown, try to extract from driver name
                if ($manufacturer -eq "Unknown" -and $_.DriverName) {
                    $driverParts = $_.DriverName -split " "
                    if ($driverParts.Count -gt 0) {
                        $commonBrands = @("HP", "Canon", "Epson", "Brother", "Lexmark", "Xerox", "Samsung", "Ricoh", "Kyocera", "Konica", "Toshiba", "Sharp", "Panasonic", "Dell", "Lenovo")
                        foreach ($brand in $commonBrands) {
                            if ($_.DriverName -like "*$brand*") {
                                $manufacturer = $brand
                                break
                            }
                        }
                    }
                }
                
                [PSCustomObject]@{
                    Name = $_.Name
                    Manufacturer = $manufacturer
                    Driver = $_.DriverName
                    Port = $_.PortName
                    Status = $_.PrinterStatus
                    Network = $_.Network
                    Shared = $_.Shared
                    Default = $_.Default
                }
            }
            $printers | ConvertTo-Json -Depth 10
            '''
            
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout.strip():
                printers = json_lib.loads(result.stdout)
                if not isinstance(printers, list):
                    printers = [printers] if printers else []
                return printers
            return []
        except Exception as e:
            return []
    
    def _get_usb_devices(self):
        """Get USB device information"""
        try:
            import subprocess
            import json as json_lib
            
            ps_script = '''
            $usbDevices = Get-CimInstance Win32_USBControllerDevice -ErrorAction SilentlyContinue | ForEach-Object {
                $device = Get-CimInstance -CimInstance $_.Dependent
                if ($device -and $device.Name) {
                    [PSCustomObject]@{
                        Name = $device.Name
                        Description = $device.Description
                        Manufacturer = $device.Manufacturer
                        PNPDeviceID = $device.PNPDeviceID
                    }
                }
            } | Where-Object { $_.Name -and $_.Name -notlike "*USB Root*" -and $_.Name -notlike "*USB Host*" } | Select-Object -First 20
            $usbDevices | ConvertTo-Json -Depth 10
            '''
            
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout.strip():
                devices = json_lib.loads(result.stdout)
                if not isinstance(devices, list):
                    devices = [devices] if devices else []
                return devices
            return []
        except Exception as e:
            return []
    
    def _update_connections_tree(self, monitors, printers, usb_devices):
        """Update the connections treeview with collected data"""
        # Clear existing items
        for item in self.connections_tree.get_children():
            self.connections_tree.delete(item)
        
        # Add monitors
        if monitors:
            monitor_parent = self.connections_tree.insert("", tk.END, text="🖥️ Monitors", values=("",))
            for monitor in monitors:
                if isinstance(monitor, dict):
                    manufacturer = monitor.get('Manufacturer', 'Unknown')
                    model = monitor.get('Model', 'Unknown')
                    serial = monitor.get('Serial', 'N/A')
                    # Display with brand first: "Brand Model"
                    display_name = f"{manufacturer} {model}".strip()
                    if display_name == "Unknown Unknown" or not display_name:
                        display_name = monitor.get('Name', 'Unknown Monitor')
                    details = f"Brand: {manufacturer} | Model: {model} | Serial: {serial}"
                    self.connections_tree.insert(monitor_parent, tk.END, text=display_name, values=(details,))
        else:
            self.connections_tree.insert("", tk.END, text="🖥️ Monitors", values=("No monitors detected",))
        
        # Add printers
        if printers:
            printer_parent = self.connections_tree.insert("", tk.END, text="🖨️ Printers", values=("",))
            for printer in printers:
                if isinstance(printer, dict):
                    name = printer.get('Name', 'Unknown Printer')
                    manufacturer = printer.get('Manufacturer', 'Unknown')
                    driver = printer.get('Driver', 'N/A')
                    port = printer.get('Port', 'N/A')
                    status = printer.get('Status', 'Unknown')
                    network = "Network" if printer.get('Network') else "Local"
                    shared = "Shared" if printer.get('Shared') else "Not Shared"
                    default = " (Default)" if printer.get('Default') else ""
                    # Display with brand: "Brand - Printer Name"
                    display_name = f"{manufacturer} - {name}" if manufacturer != "Unknown" else name
                    details = f"Brand: {manufacturer} | {network} | Port: {port} | Driver: {driver} | Status: {status} | {shared}{default}"
                    self.connections_tree.insert(printer_parent, tk.END, text=display_name, values=(details,))
        else:
            self.connections_tree.insert("", tk.END, text="🖨️ Printers", values=("No printers detected",))
        
        # Add USB devices
        if usb_devices:
            usb_parent = self.connections_tree.insert("", tk.END, text="🔌 USB Devices", values=("",))
            for device in usb_devices:
                if isinstance(device, dict):
                    name = device.get('Name', 'Unknown Device')
                    manufacturer = device.get('Manufacturer', 'Unknown')
                    description = device.get('Description', '')
                    # Display with brand: "Brand - Device Name"
                    display_name = f"{manufacturer} - {name}" if manufacturer and manufacturer != "Unknown" else name
                    details = f"Brand: {manufacturer}"
                    if description:
                        details += f" | {description}"
                    self.connections_tree.insert(usb_parent, tk.END, text=display_name, values=(details,))
        else:
            self.connections_tree.insert("", tk.END, text="🔌 USB Devices", values=("No USB devices detected",))
        
        # Update status
        total = len(monitors) + len(printers) + len(usb_devices)
        self.connections_status.config(
            text=f"Found {len(monitors)} monitor(s), {len(printers)} printer(s), {len(usb_devices)} USB device(s) - Total: {total} devices"
        )
    
    def on_closing(self):
        """Handle window closing"""
        if self.background_running:
            if messagebox.askyesno("Confirm Exit", 
                "Background service is running.\n\n"
                "If you close this window, the background service will stop.\n\n"
                "Do you want to stop the service and exit?"):
                if self.background_collector:
                    self.background_collector.stop()
                self.root.destroy()
            else:
                return  # Don't close
        else:
            self.root.destroy()


def main():
    """Main entry point"""
    try:
        root = tk.Tk()
        app = GLPIAgentBackgroundGUI(root)
        root.mainloop()
    except Exception as e:
        import traceback
        error_msg = f"Failed to start GUI: {e}\n\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr)
        try:
            import tkinter.messagebox as mb
            mb.showerror("Fatal Error", f"Failed to start GLPI Agent GUI:\n\n{str(e)}\n\nSee console for details.")
        except:
            print("\n" + "="*60)
            print("GLPI Agent GUI - Fatal Error")
            print("="*60)
            print(error_msg)
            print("="*60)
            try:
                input("\nPress Enter to exit...")
            except:
                import time
                time.sleep(10)
        sys.exit(1)


if __name__ == "__main__":
    main()

