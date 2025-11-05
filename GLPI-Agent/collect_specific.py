"""
Collect specific inventory categories from Windows system.

Usage:
    python collect_specific.py [category1,category2,...] [--output file.json]
    
Examples:
    python collect_specific.py                    # Collect everything
    python collect_specific.py storage              # Collect only storage
    python collect_specific.py cpu,memory          # Collect CPU and memory
    python collect_specific.py all                 # Collect everything
    python collect_specific.py storage --output storage.json  # Save to file

Available categories:
    os, hardware, cpu, memory, storage, video, audio, network,
    printers, software, updates, drivers, services, accounts,
    security, shares, power
"""

import sys, importlib.util, pathlib, json, os, argparse

# Resolve paths relative to this script file
script_dir = pathlib.Path(__file__).parent.resolve()
agent_py = (script_dir / "lib/GLPI/Agent.py").resolve()
spec = importlib.util.spec_from_file_location("GLPI_Agent_File", str(agent_py))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

InventoryTask = mod.InventoryTask

# Valid categories
VALID_CATEGORIES = [
    'os', 'hardware', 'cpu', 'memory', 'storage', 'video', 'audio', 'network',
    'printers', 'software', 'updates', 'drivers', 'services', 'accounts',
    'security', 'shares', 'power'
]

def print_help():
    """Print usage help."""
    print(__doc__)
    print("\nValid categories:")
    for cat in VALID_CATEGORIES:
        print(f"  - {cat}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Collect specific inventory categories from Windows system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python collect_specific.py                    # Collect everything
  python collect_specific.py storage            # Collect only storage
  python collect_specific.py cpu,memory         # Collect CPU and memory
  python collect_specific.py all                # Collect everything
  python collect_specific.py storage -o storage.json  # Save to file

Available categories: {', '.join(VALID_CATEGORIES)}
        """
    )
    parser.add_argument('categories', nargs='?', default='all',
                       help='Comma-separated list of categories to collect (default: all)')
    parser.add_argument('-o', '--output', dest='output_file',
                       help='Output JSON file path (default: print to console)')
    parser.add_argument('--list', action='store_true',
                       help='List available categories and exit')
    
    args = parser.parse_args()
    
    if args.list:
        print("Available categories:")
        for cat in VALID_CATEGORIES:
            print(f"  - {cat}")
        sys.exit(0)
    
    # Create task instance
    task = InventoryTask(
        config=None,
        datadir=str(script_dir / "share"),
        logger=None,
        target=None,
        deviceid="collector"
    )
    
    # Parse categories
    if args.categories.lower() == 'all':
        categories = None  # Collect everything
        print("Collecting full inventory...")
    else:
        categories = [c.strip().lower() for c in args.categories.split(',')]
        # Validate categories
        invalid = [c for c in categories if c not in VALID_CATEGORIES]
        if invalid:
            print(f"Error: Invalid categories: {', '.join(invalid)}")
            print(f"Valid categories: {', '.join(VALID_CATEGORIES)}")
            sys.exit(1)
        print(f"Collecting categories: {', '.join(categories)}")
    
    # Collect data
    try:
        result = task._collect_windows_enriched(categories=categories)
        
        if not result:
            print("No data collected.")
            sys.exit(1)
        
        # Output results
        if args.output_file:
            # Save to file
            output_path = pathlib.Path(args.output_file)
            if not output_path.is_absolute():
                output_path = script_dir / output_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"✓ Data saved to: {output_path}")
        else:
            # Print to console
            print(json.dumps(result, indent=2))
            
    except Exception as e:
        print(f"Error collecting data: {e}", file=sys.stderr)
        sys.exit(1)
