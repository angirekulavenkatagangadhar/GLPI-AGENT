#!/usr/bin/env python3
"""
GLPI HTTP Client - Python Implementation

HTTP client specifically for GLPI server protocol.
Handles JSON message exchange with GLPI servers.
"""

import re
import time
import random
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse
import requests

try:
    from GLPI.Agent.HTTP.Client import HTTPClient
    from GLPI.Agent.Protocol.Message import ProtocolMessage
    from GLPI.Agent.Tools.UUID import is_uuid_string, uuid_to_string
except ImportError:
    try:
        # Try alternative import paths
        from ..Client import HTTPClient
        from ...Protocol.Message import ProtocolMessage
        from ...Tools.UUID import is_uuid_string, uuid_to_string
    except ImportError:
        # Fallback implementations
        class HTTPClient:
            def __init__(self, **kwargs):
                self.logger = kwargs.get('logger')
                self.session = requests.Session()
            
            def compress(self, data): return data
            def uncompress(self, data, content_type): return data
            def request(self, request): return requests.Response()
        
        class ProtocolMessage:
            def __init__(self, **kwargs): pass
            def getContent(self): return "{}"
            def set(self, content): pass
            def is_valid_message(self): return True
            def status(self): return "ok"
            def get(self, key): return None
            def expiration(self): return 0
        
        def is_uuid_string(s): return bool(s)
        def uuid_to_string(s): return str(s)


# Global request ID for debugging
_request_id: Optional[str] = None


def _log_prefix() -> str:
    """Get log prefix with request ID if available."""
    return f"[http client] {_request_id}: " if _request_id else "[http client] "


class GLPIHTTPClient(HTTPClient):
    """
    HTTP client for GLPI server protocol.
    
    Extends base HTTP client with GLPI-specific headers and
    JSON protocol message handling.
    """
    
    def __init__(self, **params: Any):
        """
        Initialize GLPI HTTP client.
        
        Args:
            **params: Parameters including:
                - agentid: Agent UUID
                - proxyid: Proxy agent ID (optional)
                - All HTTPClient parameters
        """
        super().__init__(**params)
        
        # Add GLPI-specific headers
        self.session.headers.update({'Pragma': 'no-cache'})
        
        # Set request ID for debugging
        global _request_id
        if self.logger and hasattr(self.logger, 'debug_level') and self.logger.debug_level():
            _request_id = ''.join(f'{random.randint(0, 255):02X}' for _ in range(4))
        else:
            _request_id = None
        
        # Set agent ID header
        agentid = params.get('agentid')
        if agentid:
            agent_id_str = (
                agentid if is_uuid_string(agentid) 
                else uuid_to_string(agentid)
            )
            self.session.headers.update({'GLPI-Agent-ID': agent_id_str})
        
        # Set proxy ID header if provided
        proxyid = params.get('proxyid')
        if proxyid:
            self.session.headers.update({'GLPI-Proxy-ID': proxyid})
        
        # Set request ID header if debugging
        if _request_id:
            self.session.headers.update({'GLPI-Request-ID': _request_id})
    
    def send(self, **params: Any) -> Optional[ProtocolMessage]:
        """
        Send JSON message to GLPI server.
        
        Args:
            **params: Parameters including:
                - url: Target URL (str or URI object)
                - message: Message to send (dict or ProtocolMessage)
                - pending: How to handle pending status ("pass" to not retry)
                
        Returns:
            ProtocolMessage response or None on error
        """
        logger = self.logger
        
        # Validate agent ID
        agentid = self.session.headers.get('GLPI-Agent-ID')
        if not is_uuid_string(agentid):
            logger.error(_log_prefix() + 'no valid agentid set on HTTP client')
            return None
        
        # Parse URL
        url = params['url']
        if not isinstance(url, str):
            url = str(url)
        
        # Convert message to ProtocolMessage if needed
        message = params['message']
        if isinstance(message, dict):
            message = ProtocolMessage(message=message)
        
        # Get message content
        request_content = message.getContent()
        logger.debug2(_log_prefix() + f"sending message:\n{request_content}")
        
        # Compress content
        logger.debug2(_log_prefix() + f"compressing {len(request_content)} bytes")
        request_content_bytes = self.compress(request_content.encode('utf-8'))
        if not request_content_bytes:
            logger.error(_log_prefix() + 'inflating problem')
            return None
        logger.debug2(_log_prefix() + f"compressed to {len(request_content_bytes)} bytes")
        
        # Create HTTP request
        request = requests.Request(
            method='POST',
            url=url,
            data=request_content_bytes,
            headers=self.session.headers
        )
        logger.debug2(_log_prefix() + f"created POST request to {url}")
        
        # Send with retry logic for pending status
        answer = None
        try_count = 1
        
        while answer is None:
            # Initialize new answer message
            answer = ProtocolMessage()
            
            # Send request
            response = self.request(request)
            
            # Check if response is valid (use 'is None' to avoid triggering __bool__)
            if response is None:
                logger.error(_log_prefix() + "no response from server")
                return None
            
            # Check if response has required attributes
            status_code = getattr(response, 'status_code', None)
            logger.debug2(_log_prefix() + f"received response with status: {status_code}")
            
            if status_code is None:
                logger.error(_log_prefix() + f"invalid response object: {type(response)}, has status_code: {hasattr(response, 'status_code')}")
                return None
            
            # Check for success
            is_success = (200 <= response.status_code < 300)
            
            # Check for timeout
            reason = getattr(response, 'reason', '') or ''
            if not is_success and 'read timeout' not in str(reason).lower():
                # Try to get error message from response
                try:
                    error_content = response.content
                    if error_content:
                        # Try to decompress if needed
                        content_type = response.headers.get('Content-Type', '')
                        if 'compress' in content_type or 'gzip' in content_type:
                            error_content = self.uncompress(error_content, content_type)
                        error_msg = error_content.decode('utf-8', errors='ignore') if error_content else ''
                        logger.error(_log_prefix() + f"server returned {response.status_code}: {reason}")
                        if error_msg:
                            logger.error(_log_prefix() + f"server error message: {error_msg[:500]}")
                except:
                    logger.error(_log_prefix() + f"server returned {response.status_code}: {reason}")
                return None
            
            # Update request ID from response
            global _request_id
            response_request_id = response.headers.get('GLPI-Request-ID')
            if response_request_id and re.match(r'^[0-9A-F]{8}$', response_request_id):
                _request_id = response_request_id
            else:
                _request_id = None
            
            # Check response content
            content = response.content if hasattr(response, 'content') else None
            if not content:
                if is_success:
                    logger.error(_log_prefix() + "answer without content")
                return None
            
            # Uncompress if needed
            content_type = response.headers.get('Content-type', '')
            if content_type.startswith('application/x-'):
                uncompressed = self.uncompress(content, content_type)
                if not uncompressed:
                    if not len(content):
                        if is_success:
                            logger.error(_log_prefix() + "Got empty answer")
                        return None
                    logger.error(
                        _log_prefix() + 
                        f"failed to uncompress content starting with: {content[:256]}"
                    )
                    return None
                content = uncompressed
            
            # Decode content
            if isinstance(content, bytes):
                content = content.decode('utf-8', errors='replace')
            
            logger.debug2(_log_prefix() + f"received message:\n{content}")
            
            # Parse response
            try:
                answer.set(content)
            except Exception as e:
                if 'Inventory is disabled' in content:
                    logger.warning(
                        _log_prefix() + "Inventory support is disabled server-side"
                    )
                else:
                    lines = content.split('\n')[:2]
                    first_line = lines[0]
                    second_line = '\n' + lines[1] if len(lines) > 1 else ''
                    logger.error(
                        _log_prefix() + 
                        f"unexpected content, starting with: {first_line[:256]}{second_line}"
                    )
                return None
            
            # Validate message
            if not answer.is_valid_message():
                logger.error(_log_prefix() + "not a valid answer")
                return None
            
            # Check for errors
            if answer.status() == 'error' or not is_success:
                message = answer.get('message')
                if message:
                    # Handle JSON validation errors specially
                    match = re.match(
                        r'^(JSON does not validate\. Violations):.*"(.+)" does not match to .*->properties:(.+)$',
                        message,
                        re.DOTALL
                    )
                    if match:
                        logger.debug(_log_prefix() + f"server error: {message}")
                        logger.error(
                            _log_prefix() + 
                            f"server error: {match.group(1)}: unsupported '{match.group(2)}' value as '{match.group(3)}' field value"
                        )
                    else:
                        logger.error(_log_prefix() + f"server error: {message}")
                return None
            
            # Handle pending status
            if answer.status() == 'pending':
                # Check if caller wants to handle pending themselves
                if params.get('pending') == 'pass':
                    break
                
                # Check retry limit
                if try_count > 12:
                    logger.error(_log_prefix() + "got too much pending status")
                    return None
                
                try_count += 1
                
                # Wait before retry
                sleep_time = answer.expiration()
                time.sleep(sleep_time)
                
                logger.debug2(_log_prefix() + "retry request after pending status")
                
                # Reset answer for next iteration
                answer = None
                
                # Next request should be GET with no content
                request = requests.Request(
                    method='GET',
                    url=url,
                    headers=self.session.headers
                )
                
                # Update request ID header if we have one
                if _request_id:
                    request.headers['GLPI-Request-ID'] = _request_id
        
        return answer


if __name__ == "__main__":
    # Basic test
    print("=== GLPI HTTP Client ===\n")
    
    # This would need actual GLPI server to test
    # Just show initialization
    
    class MockLogger:
        def debug(self, msg): print(f"[DEBUG] {msg}")
        def debug2(self, msg): print(f"[DEBUG2] {msg}")
        def debug_level(self): return 1
        def error(self, msg): print(f"[ERROR] {msg}")
        def warning(self, msg): print(f"[WARNING] {msg}")
    
    client = GLPIHTTPClient(
        logger=MockLogger(),
        agentid='12345678-1234-1234-1234-123456789abc',
        timeout=30
    )
    
    print(f"Agent ID header: {client.session.headers.get('GLPI-Agent-ID')}")
    print(f"Request ID: {_request_id}")
    print("\nClient ready to send messages to GLPI server")