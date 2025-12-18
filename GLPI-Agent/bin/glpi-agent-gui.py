#!/usr/bin/env python3
"""
GLPI Agent GUI Application
Simple GUI for sending inventory to GLPI server
"""

import sys
import os
import threading
from pathlib import Path

# Add lib directory to path
# Handle both development and PyInstaller bundled modes
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


class GLPIAgentGUI:
    """GUI Application for GLPI Agent"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("GLPI Agent - Inventory Sender")
        self.root.geometry("600x500")
        self.root.resizable(True, True)
        
        # Variables
        self.server_url = tk.StringVar(value="http://")
        self.is_running = False
        
        # Setup GUI
        self.setup_ui()
        
        # Center window
        self.center_window()
    
    def center_window(self):
        """Center the window on screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
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
            text="GLPI Agent Inventory Sender",
            font=("Arial", 16, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Server address section
        server_frame = ttk.LabelFrame(main_frame, text="Server Configuration", padding="10")
        server_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        server_frame.columnconfigure(1, weight=1)
        
        ttk.Label(server_frame, text="Server Address:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        server_entry = ttk.Entry(server_frame, textvariable=self.server_url, width=40)
        server_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))
        
        # Example label
        example_label = ttk.Label(
            server_frame,
            text="Example: http://server.domain.com or http://192.168.1.100:80",
            font=("Arial", 8),
            foreground="gray"
        )
        example_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10))
        
        self.send_button = ttk.Button(
            button_frame,
            text="Send Inventory",
            command=self.send_inventory,
            width=20
        )
        self.send_button.pack(side=tk.LEFT, padx=5)
        
        self.clear_button = ttk.Button(
            button_frame,
            text="Clear Log",
            command=self.clear_log,
            width=20
        )
        self.clear_button.pack(side=tk.LEFT, padx=5)
        
        # Status/Log section
        log_frame = ttk.LabelFrame(main_frame, text="Status & Log", padding="10")
        log_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=15,
            width=70,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 9)
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Status bar
        self.status_label = ttk.Label(
            main_frame,
            text="Ready",
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding="5"
        )
        self.status_label.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E))
    
    def log(self, message, level="INFO"):
        """Add message to log"""
        self.log_text.config(state=tk.NORMAL)
        timestamp = self.get_timestamp()
        color_map = {
            "INFO": "black",
            "SUCCESS": "green",
            "ERROR": "red",
            "WARNING": "orange"
        }
        color = color_map.get(level, "black")
        
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.root.update_idletasks()
    
    def get_timestamp(self):
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")
    
    def clear_log(self):
        """Clear the log text"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.update_status("Ready")
    
    def update_status(self, message):
        """Update status bar"""
        self.status_label.config(text=message)
        self.root.update_idletasks()
    
    def send_inventory(self):
        """Send inventory to server"""
        if self.is_running:
            messagebox.showwarning("Warning", "Inventory is already being sent. Please wait.")
            return
        
        server_url = self.server_url.get().strip()
        if not server_url or server_url == "http://":
            messagebox.showerror("Error", "Please enter a valid server address.")
            return
        
        # Validate URL format
        if not (server_url.startswith("http://") or server_url.startswith("https://")):
            messagebox.showerror("Error", "Server address must start with http:// or https://")
            return
        
        # Run in separate thread to avoid freezing GUI
        thread = threading.Thread(target=self._send_inventory_thread, args=(server_url,), daemon=True)
        thread.start()
    
    def _send_inventory_thread(self, server_url):
        """Send inventory in background thread"""
        self.is_running = True
        self.send_button.config(state=tk.DISABLED)
        self.update_status("Collecting inventory...")
        
        try:
            self.log(f"Starting inventory collection...", "INFO")
            self.log(f"Server: {server_url}", "INFO")
            
            # Create agent instance
            # Handle both development and PyInstaller bundled modes
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                base_path = Path(sys._MEIPASS)
                exe_dir = Path(sys.executable).parent
            else:
                # Running as script
                base_path = Path(__file__).parent.parent.resolve()
                exe_dir = base_path
            
            datadir = SETUP_CONFIG.get('datadir', str(base_path / 'share'))
            libdir = SETUP_CONFIG.get('libdir', str(base_path / 'lib'))
            vardir = SETUP_CONFIG.get('vardir', str(exe_dir / 'var'))
            
            # Ensure directories exist
            os.makedirs(vardir, exist_ok=True)
            
            # Capture agent logs
            import logging
            class GUILogHandler(logging.Handler):
                def __init__(self, gui_log_func):
                    super().__init__()
                    self.gui_log_func = gui_log_func
                
                def emit(self, record):
                    msg = self.format(record)
                    level = "INFO"
                    if record.levelno >= logging.ERROR:
                        level = "ERROR"
                    elif record.levelno >= logging.WARNING:
                        level = "WARNING"
                    self.gui_log_func(msg, level)
            
            # Add handler to root logger to capture agent logs
            handler = GUILogHandler(self.log)
            handler.setFormatter(logging.Formatter('%(message)s'))
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)
            root_logger.setLevel(logging.INFO)
            
            try:
                agent = GLPIAgent(
                    datadir=datadir,
                    libdir=libdir,
                    vardir=vardir
                )
                
                # Initialize with server option
                options = {
                    'server': [server_url],
                    'force': True,
                    'no-task': []
                }
                
                self.log("Initializing agent...", "INFO")
                agent.init(options=options)
                
                self.log("Collecting system inventory...", "INFO")
                self.update_status("Collecting inventory data...")
                
                # Run inventory task
                agent.run()
                
                self.log("✅ Inventory successfully sent to server!", "SUCCESS")
                self.update_status("Inventory sent successfully!")
                messagebox.showinfo("Success", f"Inventory successfully sent to:\n{server_url}")
            finally:
                # Remove handler
                root_logger.removeHandler(handler)
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            error_traceback = traceback.format_exc()
            self.log(f"❌ Error: {error_msg}", "ERROR")
            self.log(f"Traceback:\n{error_traceback}", "ERROR")
            self.update_status(f"Error: {error_msg}")
            messagebox.showerror("Error", f"Failed to send inventory:\n{error_msg}\n\nSee log for details.")
        
        finally:
            self.is_running = False
            self.send_button.config(state=tk.NORMAL)
            if not self.is_running:
                self.update_status("Ready")


def main():
    """Main entry point"""
    try:
        root = tk.Tk()
        app = GLPIAgentGUI(root)
        root.mainloop()
    except Exception as e:
        import traceback
        error_msg = f"Failed to start GUI: {e}\n\n{traceback.format_exc()}"
        print(error_msg, file=sys.stderr)
        # Try to show error in a message box if possible
        try:
            import tkinter.messagebox as mb
            mb.showerror("Fatal Error", f"Failed to start GLPI Agent GUI:\n\n{str(e)}\n\nSee console for details.")
        except:
            # If we can't show message box, at least print to console
            print("\n" + "="*60)
            print("GLPI Agent GUI - Fatal Error")
            print("="*60)
            print(error_msg)
            print("="*60)
            # Pause so user can read the error
            try:
                input("\nPress Enter to exit...")
            except:
                import time
                time.sleep(10)  # Wait 10 seconds if input doesn't work
        sys.exit(1)


if __name__ == "__main__":
    main()

