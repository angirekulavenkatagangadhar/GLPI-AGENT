# GLPI Agent - Python Implementation

A production-ready Python implementation of the GLPI Agent for automated IT asset inventory and management.

## Features

- **Complete Windows Inventory**: BIOS, CPU, Memory, Drives, Network Cards, Batteries, Graphics Cards, Sound Cards, Controllers, Monitors, Printers
- **Full GLPI Protocol Support**: Proper schema validation and data formatting
- **WMI & PowerShell Integration**: Comprehensive hardware detection on Windows
- **Battery Health Reporting**: Detailed battery information including health percentage
- **Network Detection**: Network ports, internet speed, and adapter information
- **PCI Database Lookup**: Automatic controller identification
- **Production-Ready**: Robust error handling and logging

## Requirements

- Python 3.8 or higher
- Windows (primary support)
- Administrator privileges (for full hardware inventory)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/angirekulavenkatagangadhar/GLPI-AGENT.git
   cd GLPI-AGENT/GLPI-Agent
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv .venv
   
   # Activate on Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   
   # Activate on Windows (CMD):
   .venv\Scripts\activate.bat
   
   # Activate on Linux/Mac:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Basic Inventory

Run a local inventory:
```bash
python bin/glpi-agent.py --local
```

### Connect to GLPI Server

```bash
python bin/glpi-agent.py --server http://your-glpi-server.com/glpi/front/inventory.php
```

### With Authentication

```bash
python bin/glpi-agent.py --server http://your-glpi-server.com/glpi/front/inventory.php --user username --password password
```

### Configuration File

Edit `etc/agent.cfg` to set default server and other options.

## Project Structure

```
GLPI-Agent/
├── bin/              # Executable scripts
├── lib/              # Core Python modules
│   └── GLPI/         # Main GLPI Agent package
├── etc/              # Configuration files
├── share/            # Shared resources (PCI IDs, USB IDs, etc.)
├── resources/        # Test resources and samples
└── requirements.txt  # Python dependencies
```

## Development

### Running Tests

```bash
python -m pytest t/
```

### Code Structure

- `lib/GLPI/Agent.py` - Main agent class
- `lib/GLPI/Agent/Task/` - Task implementations (Inventory, etc.)
- `lib/GLPI/Agent/Tools/` - Utility functions (WMI, PowerShell, etc.)

## License

This project is licensed under the GNU General Public License v2.0 - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please ensure your code follows the existing style and includes appropriate tests.

## Support

For issues and questions, please open an issue on GitHub.

