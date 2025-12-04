#!/usr/bin/env python3
"""
GLPI Agent HTTP Client - Python Implementation

Abstract HTTP client with SSL validation, authentication (Basic/OAuth2),
compression support, and proxy handling.
"""

import os
import sys
import time
import gzip
import zlib
import hashlib
import json
import ssl
import certifi
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import requests
from requests.auth import HTTPBasicAuth

try:
    from .logger import Logger
    from .tools import get_all_lines, trim_whitespace, empty
    from .protocol.message import ProtocolMessage
    from .version import AGENT_STRING
except ImportError:
    try:
        from glpi_agent.logger import Logger
        from glpi_agent.tools import get_all_lines, trim_whitespace, empty
        from glpi_agent.protocol.message import ProtocolMessage
        from glpi_agent.version import AGENT_STRING
    except ImportError:
        class Logger:
            def debug(self, msg): pass
            def debug2(self, msg): pass
            def info(self, msg): print(f"[INFO] {msg}")
            def error(self, msg): print(f"[ERROR] {msg}")
        
        def get_all_lines(**kwargs): return ""
        def trim_whitespace(s): return s.strip() if s else s
        def empty(s): return not s
        
        class ProtocolMessage:
            def __init__(self, **kwargs): pass
        
        AGENT_STRING = "GLPI-Agent"

LOG_PREFIX = "[http client] "

# Global OAuth2 token storage
_oauth2_tokens: Dict[str, Dict[str, Any]] = {}

# Global SSL certificate cache
_ssl_ca_cache: Optional[Dict[str, Any]] = None


class HTTPClient:
    """
    Abstract HTTP client for GLPI Agent.
    
    Handles HTTP/HTTPS requests with:
    - SSL certificate validation
    - Basic and OAuth2 authentication
    - Proxy support
    - Compression (gzip/zlib)
    """
    
    def __init__(self, **params: Any):
        """
        Initialize HTTP client.
        
        Args:
            **params: Parameters including:
                - logger: Logger instance
                - config: Configuration dict
                - user: HTTP basic auth username
                - password: HTTP basic auth password
                - oauth_client: OAuth2 client ID
                - oauth_secret: OAuth2 client secret
                - ca_cert_file: CA certificate file path
                - ca_cert_dir: CA certificate directory path
                - ssl_cert_file: Client certificate file path
                - ssl_fingerprint: SSL fingerprint(s) to trust
                - ssl_keystore: SSL keystore specification
                - no_ssl_check: Disable SSL verification
                - no_compress: Disable compression
                - proxy: Proxy URL
                - timeout: Request timeout in seconds
        """
        config = params.get('config', {})
        
        self.logger: Logger = params.get('logger', Logger())
        self.user: Optional[str] = params.get('user') or config.get('user')
        self.password: Optional[str] = params.get('password') or config.get('password')
        self.oauth_client: Optional[str] = params.get('oauth_client') or config.get('oauth-client-id')
        self.oauth_secret: Optional[str] = params.get('oauth_secret') or config.get('oauth-client-secret')
        
        # SSL configuration
        self.no_ssl_check: bool = params.get('no_ssl_check') or config.get('no-ssl-check', False)
        self.ca_cert_file: Optional[str] = params.get('ca_cert_file') or config.get('ca-cert-file')
        self.ca_cert_dir: Optional[str] = params.get('ca_cert_dir') or config.get('ca-cert-dir')
        self.ssl_cert_file: Optional[str] = params.get('ssl_cert_file') or config.get('ssl-cert-file')
        self.ssl_fingerprint: Optional[List[str]] = params.get('ssl_fingerprint') or config.get('ssl-fingerprint')
        self.ssl_keystore: Optional[str] = params.get('ssl_keystore') or config.get('ssl-keystore')
        self.ssl_set: bool = False
        
        # Validate certificate files
        if self.ca_cert_file and not os.path.isfile(self.ca_cert_file):
            raise ValueError(f"non-existing certificate file {self.ca_cert_file}")
        
        if self.ca_cert_dir and not os.path.isdir(self.ca_cert_dir):
            raise ValueError(f"non-existing certificate directory {self.ca_cert_dir}")
        
        if self.ssl_cert_file and not os.path.isfile(self.ssl_cert_file):
            raise ValueError(f"non-existing client certificate file {self.ssl_cert_file}")
        
        # Compression configuration
        self.no_compress: bool = params.get('no_compress') or config.get('no-compression', False)
        self._setup_compression()
        
        # Create session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': AGENT_STRING,
            'Content-Type': self._get_content_type()
        })
        
        # Timeout
        self.timeout: int = params.get('timeout') or config.get('timeout', 180)
        
        # Proxy configuration
        proxy = params.get('proxy') or config.get('proxy')
        if proxy and proxy != 'none':
            self.session.proxies = {
                'http': proxy,
                'https': proxy
            }
        
        self._vardir: Optional[str] = config.get('vardir')
    
    def _setup_compression(self) -> None:
        """Setup compression method."""
        if self.no_compress:
            self.compression = 'none'
            self.logger.debug2(LOG_PREFIX + "Not using compression")
        else:
            # Python has built-in zlib support
            self.compression = 'zlib'
            self.logger.debug2(LOG_PREFIX + "Using zlib for compression")
    
    def _get_content_type(self) -> str:
        """Get content-type header based on compression."""
        if self.compression == 'zlib':
            return "application/x-compress-zlib"
        elif self.compression == 'gzip':
            return "application/x-compress-gzip"
        else:
            return "application/json"
    
    def request(self, request: requests.Request, 
                file_path: Optional[str] = None,
                no_proxy_host: Optional[str] = None,
                timeout: Optional[int] = None,
                **skip_errors) -> requests.Response:
        """
        Send HTTP request with authentication and SSL handling.
        
        Args:
            request: Prepared requests.Request object
            file_path: Optional file path to save response to
            no_proxy_host: Host to exclude from proxy
            timeout: Custom timeout for this request
            **skip_errors: HTTP status codes to skip error logging for
            
        Returns:
            requests.Response object
        """
        url = request.url
        parsed_url = urlparse(url)
        scheme = parsed_url.scheme
        
        # Setup SSL if HTTPS and not yet configured
        if scheme == 'https' and not self.ssl_set:
            self._set_ssl_options()
        
        # Handle proxy exclusion
        if no_proxy_host:
            self.session.proxies.update({
                'http': None,
                'https': None
            })
        
        # Log proxy usage
        if self.session.proxies.get(scheme):
            proxy_url = self.session.proxies[scheme]
            # Obfuscate password in proxy URL for logging
            if '@' in proxy_url:
                proxy_parts = proxy_url.split('@')
                if ':' in proxy_parts[0]:
                    user_pass = proxy_parts[0].split(':')
                    proxy_url = f"{user_pass[0]}:{'X' * len(user_pass[1])}@{proxy_parts[1]}"
            self.logger.debug(LOG_PREFIX + f"Using '{proxy_url}' as proxy for {scheme} protocol")
        
        # Add OAuth2 token if available
        self._add_oauth_token(request, url)
        
        # Execute request
        use_timeout = timeout if timeout is not None else self.timeout
        
        try:
            prepared = self.session.prepare_request(request)
            response = self.session.send(
                prepared,
                timeout=use_timeout,
                verify=not self.no_ssl_check,
                stream=bool(file_path)
            )
            
            # Check for valid status code
            status_code = getattr(response, 'status_code', None)
            if status_code is None:
                self.logger.error(LOG_PREFIX + "invalid response - no status code")
                error_response = requests.Response()
                error_response.status_code = 500
                error_response._content = b"Invalid response object"
                return error_response
            
            # Save to file if requested
            if file_path and 200 <= status_code < 300:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            # Log SSL info if no_ssl_check enabled
            if self.no_ssl_check and hasattr(response.raw, '_connection'):
                self._log_ssl_info(response)
            
            # Handle authentication
            if status_code == 401:
                response = self._handle_authentication(request, response, url)
            
            elif status_code == 407:
                self.logger.error(
                    LOG_PREFIX + "proxy authentication required, wrong or no proxy credentials"
                )
            
            elif not (200 <= status_code < 300) and status_code not in skip_errors:
                self._log_error(response, parsed_url)
            
            return response
            
        except requests.exceptions.RequestException as e:
            self.logger.error(LOG_PREFIX + f"communication error: {e}")
            # Return error response with proper status code
            error_response = requests.Response()
            error_response.status_code = 500
            error_response._content = str(e).encode()
            error_response.reason = str(e)
            return error_response
    
    def _add_oauth_token(self, request: requests.Request, url: str) -> None:
        """Add OAuth2 bearer token to request if available."""
        global _oauth2_tokens
        
        if url in _oauth2_tokens:
            token_info = _oauth2_tokens[url]
            
            # Refresh if expired
            if time.time() >= token_info['expires']:
                self._get_oauth_access_token(url)
                token_info = _oauth2_tokens.get(url)
            
            if token_info:
                request.headers['Authorization'] = f"Bearer {token_info['token']}"
                self.logger.debug(
                    LOG_PREFIX + "submitting request with access token authorization"
                )
    
    def _handle_authentication(self, request: requests.Request, 
                              response: requests.Response,
                              url: str) -> requests.Response:
        """Handle 401 authentication required response."""
        # Try OAuth2 first
        if self.oauth_client and self.oauth_secret:
            self._get_oauth_access_token(url)
            
            global _oauth2_tokens
            if url in _oauth2_tokens:
                request.headers['Authorization'] = f"Bearer {_oauth2_tokens[url]['token']}"
                self.logger.debug(
                    LOG_PREFIX + "authentication required, submitting request with access token authorization"
                )
                
                # Retry request
                prepared = self.session.prepare_request(request)
                response = self.session.send(prepared, timeout=self.timeout)
                
                if not response.ok:
                    error = "authentication required, wrong access token" if response.status_code == 401 else f"authentication required, error status: {response.status_line}"
                    
                    # Try to extract error message
                    try:
                        content = self.uncompress(response.content, response.headers.get('content-type'))
                        if content and content.startswith(b'{'):
                            msg = ProtocolMessage(message=content.decode())
                            if hasattr(msg, 'status') and msg.status == 'error':
                                error = msg.get('message') or error
                    except Exception:
                        pass
                    
                    self.logger.error(LOG_PREFIX + error)
        
        # Try basic auth
        elif self.user and self.password:
            self.logger.debug(LOG_PREFIX + "authentication required, submitting credentials")
            
            # Add basic auth and retry
            request.auth = HTTPBasicAuth(self.user, self.password)
            prepared = self.session.prepare_request(request)
            response = self.session.send(prepared, timeout=self.timeout)
            
            if not response.ok:
                self.logger.error(
                    LOG_PREFIX + 
                    ("authentication required, wrong credentials" if response.status_code == 401 
                     else f"authentication required, error status: {response.reason}")
                )
        
        else:
            error = "authentication required, no credentials available"
            
            # Try to extract error message
            try:
                if response.headers.get('content-length'):
                    content = self.uncompress(response.content, response.headers.get('content-type'))
                    if content:
                        if content.startswith(b'{'):
                            msg = ProtocolMessage(message=content.decode())
                            if hasattr(msg, 'status') and msg.status == 'error':
                                error = msg.get('message') or error
            except Exception:
                pass
            
            self.logger.error(LOG_PREFIX + error)
        
        return response
    
    def _get_oauth_access_token(self, url: str) -> None:
        """Request OAuth2 access token."""
        global _oauth2_tokens
        
        if empty(self.oauth_client) or empty(self.oauth_secret):
            self.logger.error(LOG_PREFIX + "oauth access token missing")
            return
        
        # Remove existing token
        _oauth2_tokens.pop(url, None)
        
        # Build token endpoint URL
        parsed = urlparse(url)
        path = parsed.path
        
        # Guess token path
        match = re.match(r'^(.*)/(marketplace|plugins).*$', path)
        if match:
            path = match.group(1)
        
        path = path.rstrip('/') + '/api.php/token'
        
        token_url = f"{parsed.scheme}://{parsed.netloc}{path}"
        
        self.logger.debug(
            LOG_PREFIX + f"authentication required, querying oauth access token on {token_url}"
        )
        
        # Prepare token request
        token_data = {
            'grant_type': 'client_credentials',
            'client_id': self.oauth_client,
            'client_secret': self.oauth_secret,
            'scope': 'inventory'
        }
        
        content = json.dumps(token_data).encode()
        content_hash = hashlib.sha256(content).hexdigest()
        
        # Log with secrets hidden
        log_data = content.decode()
        log_data = log_data.replace(self.oauth_client, 'CLIENT_ID')
        log_data = log_data.replace(self.oauth_secret, 'CLIENT_SECRET')
        self.logger.debug2(
            LOG_PREFIX + f"sending message: (real content sha256sum: {content_hash})\n{log_data}"
        )
        
        try:
            response = self.session.post(
                token_url,
                headers={'Content-Type': 'application/json'},
                data=content,
                timeout=self.timeout
            )
            
            content_type = response.headers.get('content-type', '')
            self.logger.debug2(
                LOG_PREFIX + f"received message: ({content_type})\n{response.text}"
            )
            
            if response.ok and 'application/json' in content_type:
                token_data = response.json()
                
                if (token_data.get('token_type') == 'Bearer' and 
                    not empty(token_data.get('access_token'))):
                    
                    expires_in = token_data.get('expires_in', 60)
                    if not isinstance(expires_in, int):
                        expires_in = 60
                    
                    _oauth2_tokens[url] = {
                        'token': token_data['access_token'],
                        'expires': time.time() + expires_in
                    }
                    
                    self.logger.debug(
                        LOG_PREFIX + f"Bearer oauth token received (expiration: {expires_in}s)"
                    )
                else:
                    self.logger.error(LOG_PREFIX + "Unsupported token returned from oauth server")
            else:
                self.logger.error(
                    LOG_PREFIX + f"Failed to request oauth access token: {response.reason}"
                )
        
        except Exception as e:
            self.logger.error(LOG_PREFIX + f"Failed to request oauth access token: {e}")
    
    def _set_ssl_options(self) -> None:
        """Configure SSL/TLS options."""
        if self.no_ssl_check:
            self.logger.debug(LOG_PREFIX + "SSL verification disabled")
            self.session.verify = False
            # Suppress InsecureRequestWarning
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        else:
            # Use certifi bundle by default
            self.session.verify = certifi.where()
            
            # Override with custom CA cert file/dir if provided
            if self.ca_cert_file:
                self.session.verify = self.ca_cert_file
            elif self.ca_cert_dir:
                self.session.verify = self.ca_cert_dir
            
            # Client certificate
            if self.ssl_cert_file:
                self.session.cert = self.ssl_cert_file
        
        self.ssl_set = True
    
    def _log_ssl_info(self, response: requests.Response) -> None:
        """Log SSL connection information."""
        try:
            # Try to get SSL info from underlying connection
            if hasattr(response.raw, '_connection') and hasattr(response.raw._connection, 'sock'):
                sock = response.raw._connection.sock
                if hasattr(sock, 'version'):
                    version = sock.version()
                    cipher = sock.cipher()
                    self.logger.info(
                        LOG_PREFIX + f"SSL info: Version: {version}, Cipher: {cipher[0]}"
                    )
        except Exception:
            pass
    
    def _log_error(self, response: requests.Response, parsed_url: Any) -> None:
        """Log HTTP error details."""
        messages = [response.reason]
        
        # Try to extract detailed error message
        try:
            content = self.uncompress(response.content, response.headers.get('content-type'))
            if content:
                if content.startswith(b'{'):
                    msg = ProtocolMessage(message=content.decode())
                    if hasattr(msg, 'status') and msg.status == 'error':
                        error_msg = msg.get('message')
                        if error_msg:
                            messages.append(error_msg)
        except Exception:
            pass
        
        error_type = "communication error"
        if 'proxy' in str(response.request.url).lower():
            error_type = "proxy error"
        
        self.logger.error(LOG_PREFIX + f"{error_type}: {', '.join(messages)}")
    
    def compress(self, data: bytes) -> bytes:
        """
        Compress data based on configured method.
        
        Args:
            data: Data to compress
            
        Returns:
            Compressed data
        """
        self.logger.debug2(LOG_PREFIX + f"compress() using method: {self.compression}")
        if self.compression == 'zlib':
            compressed = zlib.compress(data)
            self.logger.debug2(LOG_PREFIX + f"zlib compressed {len(data)} -> {len(compressed)}")
            return compressed
        elif self.compression == 'gzip':
            compressed = gzip.compress(data)
            self.logger.debug2(LOG_PREFIX + f"gzip compressed {len(data)} -> {len(compressed)}")
            return compressed
        else:
            self.logger.debug2(LOG_PREFIX + f"no compression, returning {len(data)} bytes as-is")
            return data
    
    def uncompress(self, data: bytes, content_type: Optional[str] = None) -> bytes:
        """
        Uncompress data based on content type.
        
        Args:
            data: Data to uncompress
            content_type: Content-Type header value
            
        Returns:
            Uncompressed data
        """
        if not content_type:
            content_type = "unspecified"
        
        content_type = content_type.replace('application/', '', 1)
        
        if 'x-compress-zlib' in content_type:
            self.logger.debug2("format: Zlib")
            return zlib.decompress(data)
        elif 'x-compress-gzip' in content_type:
            self.logger.debug2("format: Gzip")
            return gzip.decompress(data)
        elif 'json' in content_type:
            self.logger.debug2("format: JSON")
            return data
        elif 'xml' in content_type:
            self.logger.debug2("format: XML")
            return data
        elif data.strip().startswith(b'{'):
            self.logger.debug2("format: JSON detected")
            return data
        elif data.startswith(b'<?xml'):
            self.logger.debug2("format: XML detected")
            return data
        else:
            self.logger.debug2(f"unsupported format: {content_type}")
            return data


if __name__ == "__main__":
    # Basic test
    print("=== GLPI Agent HTTP Client ===\n")
    
    client = HTTPClient(
        logger=Logger(),
        timeout=30,
        no_ssl_check=False
    )
    
    print(f"Compression: {client.compression}")
    print(f"Timeout: {client.timeout}")
    print(f"SSL verification: {not client.no_ssl_check}")