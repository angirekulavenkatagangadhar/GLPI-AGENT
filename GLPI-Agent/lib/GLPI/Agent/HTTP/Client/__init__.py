"""
GLPI Agent HTTP Client Module

HTTP client implementations for different protocols (GLPI, OCS, Fusion).
"""

# Import base HTTPClient from parent module (Client.py file)
import sys
import os
import importlib.util

# Get the Client.py file path (sibling to Client/ directory)
client_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Client.py')
if os.path.exists(client_file):
    spec = importlib.util.spec_from_file_location("GLPI.Agent.HTTP.ClientModule", client_file)
    if spec and spec.loader:
        client_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(client_module)
        HTTPClient = client_module.HTTPClient
        __all__ = ['HTTPClient']
else:
    __all__ = []

