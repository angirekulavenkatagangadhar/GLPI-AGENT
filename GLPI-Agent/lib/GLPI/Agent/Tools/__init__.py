"""
GLPI Agent Tools Module

Utility tools and helpers for platform-specific operations.
"""

# Import common functions from parent Tools.py file
import sys
import os
import importlib.util

# Get the Tools.py file path (sibling to Tools/ directory)
tools_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Tools.py')
if os.path.exists(tools_file):
    spec = importlib.util.spec_from_file_location("GLPI.Agent.ToolsModule", tools_file)
    if spec and spec.loader:
        tools_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tools_module)
        empty = tools_module.empty
        trim_whitespace = tools_module.trim_whitespace
        run_function = tools_module.run_function
        any_func = tools_module.any_func
        __all__ = ['empty', 'trim_whitespace', 'run_function', 'any_func']
else:
    __all__ = []

