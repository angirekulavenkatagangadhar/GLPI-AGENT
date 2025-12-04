"""
GLPI Agent Target Module

Target implementations for different output destinations (Server, Local, Listener).
"""

# Import base Target class from parent Target.py file  
import sys
import os
import importlib.util

# Get the Target.py file path (sibling to Target/ directory)
target_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Target.py')
if os.path.exists(target_file):
    spec = importlib.util.spec_from_file_location("GLPI.Agent.TargetModule", target_file)
    if spec and spec.loader:
        target_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(target_module)
        Target = target_module.Target
        __all__ = ['Target']
else:
    __all__ = []

