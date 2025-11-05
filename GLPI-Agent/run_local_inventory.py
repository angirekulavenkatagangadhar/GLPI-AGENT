import sys, importlib.util, pathlib

# Resolve paths relative to this script file so it works from any CWD
script_dir = pathlib.Path(__file__).parent.resolve()

# Point directly to the module file
agent_py = (script_dir / "lib/GLPI/Agent.py").resolve()
spec = importlib.util.spec_from_file_location("GLPI_Agent_File", str(agent_py))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

GLPIAgent = mod.GLPIAgent
LocalTarget = mod.LocalTarget  # defined in Agent.py

agent = GLPIAgent(datadir=str(script_dir / "share"), libdir=str(script_dir / "lib"), vardir=str(script_dir / "var"))

# Output directory and exhaustive options
out_dir = str((script_dir / "var" / "inventory").resolve())

required_categories = [
    'os','battery','controller','cpu','database','drive','environment','input',
    'licenseinfo','local_group','local_user','lvm','memory','modem','monitor',
    'network','port','psu','printer','process','slot','software','sound',
    'storage','video','usb','user','virtualmachine','provider'
]

agent.init(options={
    "local": out_dir,
    "json": True,
    "debug": True,
    "force": True,
    "scan-homedirs": 1,
    "scan-profiles": 1,
    "full-inventory-postpone": 0,
    "required-category": ','.join(required_categories),
})

target = LocalTarget(id="local_0", path=out_dir)
agent.run_task(target, "Inventory", None)

print(f"Saved full inventory (JSON) to {out_dir}")
