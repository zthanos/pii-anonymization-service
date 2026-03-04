"""
PolicyLoader: Load, validate, and manage YAML policy configurations.

This module provides the PolicyLoader class which handles loading policy
configurations from YAML files, validating them against Pydantic models,
and resolving encryption key references from environment variables or files.

Key Features:
- YAML policy file loading with safe parsing
- Pydantic-based validation
- Encryption key resolution (env: and file: references)
- Descriptive error messages for validation failures
- System configuration lookup by system_id
- Hot-reload support with thread-safe policy swapping

Security:
- Uses safe_load to prevent code execution
- Validates encryption key references before use
- Halts startup on any validation error
"""

import os
import signal
import threading
from typing import Dict

import yaml
from pydantic import ValidationError

from ..models.policy import Policy, SystemConfig


class PolicyValidationError(Exception):
    """Raised when policy file validation fails."""
    pass


class KeyResolutionError(Exception):
    """Raised when encryption key reference cannot be resolved."""
    pass


class SystemNotFoundError(Exception):
    """Raised when requested system_id is not found in policy."""
    pass


class PolicyLoader:
    """
    Manages policy configuration lifecycle.
    
    This class loads YAML policy files, validates them against Pydantic models,
    resolves encryption key references, and provides access to system configurations.
    Supports hot-reload with thread-safe policy swapping.
    
    Attributes:
        policy_path: Path to the YAML policy file
        policy: Loaded and validated Policy object
        _encryption_keys: Cache of resolved encryption keys by system_id
        _lock: RLock for thread-safe policy access and updates
    
    Example:
        >>> loader = PolicyLoader()
        >>> await loader.load_policy("policies/production.yaml")
        >>> config = loader.get_system_config("customer_db")
        >>> key = loader.resolve_encryption_key(config.encryption_key_ref)
        >>> await loader.reload_policy()  # Hot-reload from disk
    """

    def __init__(self):
        """Initialize the PolicyLoader."""
        self.policy_path: str = ""
        self.policy: Policy | None = None
        self._encryption_keys: Dict[str, bytes] = {}
        self._lock = threading.RLock()  # Reentrant lock for thread-safe access

    async def load_policy(self, path: str) -> Policy:
        """
        Load and validate policy from YAML file.
        
        Reads the YAML policy file, validates it against the Policy Pydantic model,
        and resolves all encryption key references to ensure they are accessible.
        This method should be called at startup and will halt the application if
        any validation errors occur.
        
        Args:
            path: File path to YAML policy file
            
        Returns:
            Validated Policy object
            
        Raises:
            PolicyValidationError: If YAML is invalid, file not found, or schema validation fails
            KeyResolutionError: If encryption key reference cannot be resolved
            
        Example:
            >>> loader = PolicyLoader()
            >>> policy = await loader.load_policy("policies/config.yaml")
            >>> print(f"Loaded policy version {policy.version}")
        """
        with self._lock:
            self.policy_path = path

            # Check if file exists
            if not os.path.exists(path):
                raise PolicyValidationError(
                    f"Policy file not found: {path}"
                )

            # Read and parse YAML file
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    yaml_data = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise PolicyValidationError(
                    f"Invalid YAML syntax in policy file {path}: {str(e)}"
                )
            except Exception as e:
                raise PolicyValidationError(
                    f"Failed to read policy file {path}: {str(e)}"
                )

            # Validate against Pydantic model
            try:
                policy = Policy(**yaml_data)
            except ValidationError as e:
                # Format validation errors for better readability
                error_messages = []
                for error in e.errors():
                    loc = " -> ".join(str(x) for x in error['loc'])
                    msg = error['msg']
                    error_messages.append(f"  - {loc}: {msg}")

                raise PolicyValidationError(
                    f"Policy validation failed for {path}:\n" + "\n".join(error_messages)
                )
            except Exception as e:
                raise PolicyValidationError(
                    f"Unexpected error validating policy {path}: {str(e)}"
                )

            # Validate that all encryption key references can be resolved
            for system in policy.systems:
                try:
                    key = self.resolve_encryption_key(system.encryption_key_ref)
                    # Cache the resolved key
                    self._encryption_keys[system.system_id] = key
                except KeyResolutionError as e:
                    raise PolicyValidationError(
                        f"Failed to resolve encryption key for system '{system.system_id}': {str(e)}"
                    )

            self.policy = policy
            return policy

    async def reload_policy(self) -> Policy:
        """
        Reload policy from disk with validation.
        
        Performs an atomic policy swap - validates the new policy completely
        before replacing the current policy. If validation fails, the current
        policy is retained and an error is raised. Requests continue to be
        processed using the current policy during the reload operation.
        
        This method is thread-safe and can be called while requests are being
        processed. The RLock ensures that policy reads are consistent.
        
        Returns:
            Newly loaded Policy object
            
        Raises:
            PolicyValidationError: If reload fails (current policy is retained)
            
        Example:
            >>> loader = PolicyLoader()
            >>> await loader.load_policy("policies/config.yaml")
            >>> # ... later, after policy file is updated ...
            >>> try:
            ...     new_policy = await loader.reload_policy()
            ...     print(f"Reloaded policy version {new_policy.version}")
            ... except PolicyValidationError as e:
            ...     print(f"Reload failed, keeping current policy: {e}")
        """
        if not self.policy_path:
            raise PolicyValidationError(
                "Cannot reload policy: no policy path set. Call load_policy() first."
            )

        # Save current policy and keys in case reload fails
        with self._lock:
            old_policy = self.policy
            old_keys = self._encryption_keys.copy()

        try:
            # Attempt to load new policy
            # This will update self.policy and self._encryption_keys if successful
            new_policy = await self.load_policy(self.policy_path)
            return new_policy
        except (PolicyValidationError, KeyResolutionError) as e:
            # Restore old policy and keys on failure
            with self._lock:
                self.policy = old_policy
                self._encryption_keys = old_keys

            # Re-raise the error with context
            raise PolicyValidationError(
                f"Policy reload failed, retaining current policy: {str(e)}"
            )

    def setup_signal_handler(self):
        """
        Set up SIGHUP signal handler for policy hot-reload.
        
        When the process receives a SIGHUP signal, it will automatically
        reload the policy from disk. This allows zero-downtime policy updates.
        
        Note: This should be called after load_policy() to ensure policy_path is set.
        Note: SIGHUP is not available on Windows.
        
        Example:
            >>> loader = PolicyLoader()
            >>> await loader.load_policy("policies/config.yaml")
            >>> loader.setup_signal_handler()
            >>> # Now send SIGHUP to reload: kill -HUP <pid>
        """
        # SIGHUP is not available on Windows
        if not hasattr(signal, 'SIGHUP'):
            return

        def handle_sighup(signum, frame):
            """Signal handler for SIGHUP."""
            import asyncio

            # Create a new event loop if needed (signal handlers run in main thread)
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            # Schedule the reload
            asyncio.create_task(self._reload_on_signal())

        signal.signal(signal.SIGHUP, handle_sighup)

    async def _reload_on_signal(self):
        """
        Internal method to handle policy reload triggered by signal.
        
        Logs the reload attempt and result. Errors are logged but not raised
        since this is triggered by a signal handler.
        """
        try:
            new_policy = await self.reload_policy()
            # Log success (in production, use proper logging)
            print(f"Policy reloaded successfully via SIGHUP. New version: {new_policy.version}")
        except PolicyValidationError as e:
            # Log error but don't crash (in production, use proper logging)
            print(f"Policy reload failed via SIGHUP: {str(e)}")


    def resolve_encryption_key(self, key_ref: str) -> bytes:
        """
        Resolve encryption key from env: or file: reference.
        
        Supports two reference formats:
        - env:VAR_NAME - Reads key from environment variable
        - file:/path/to/key - Reads key from file
        
        The resolved key must be exactly 32 bytes (256 bits) for AES-256.
        
        Args:
            key_ref: Reference string (env:VAR_NAME or file:/path)
            
        Returns:
            32-byte encryption key
            
        Raises:
            KeyResolutionError: If reference cannot be resolved or key is invalid
            
        Example:
            >>> loader = PolicyLoader()
            >>> key = loader.resolve_encryption_key("env:CUSTOMER_DB_KEY")
            >>> len(key)
            32
        """
        if key_ref.startswith("env:"):
            # Extract environment variable name
            var_name = key_ref[4:]  # Remove "env:" prefix

            if not var_name:
                raise KeyResolutionError(
                    f"Invalid encryption_key_ref format: '{key_ref}' - "
                    "expected 'env:VAR_NAME'"
                )

            # Check if environment variable exists
            if var_name not in os.environ:
                raise KeyResolutionError(
                    f"Environment variable '{var_name}' not found. "
                    f"Required by encryption_key_ref: '{key_ref}'"
                )

            key_str = os.environ[var_name]

            # Convert to bytes (assume hex-encoded or base64)
            try:
                # Try hex decoding first
                if len(key_str) == 64:  # 32 bytes = 64 hex chars
                    key_bytes = bytes.fromhex(key_str)
                else:
                    # Try base64 decoding
                    import base64
                    key_bytes = base64.b64decode(key_str)
            except Exception as e:
                raise KeyResolutionError(
                    f"Failed to decode encryption key from environment variable '{var_name}': {str(e)}. "
                    "Key must be hex-encoded (64 chars) or base64-encoded."
                )

            # Validate key length
            if len(key_bytes) != 32:
                raise KeyResolutionError(
                    f"Encryption key from environment variable '{var_name}' must be exactly 32 bytes, "
                    f"got {len(key_bytes)} bytes"
                )

            return key_bytes

        elif key_ref.startswith("file:"):
            # Extract file path
            file_path = key_ref[5:]  # Remove "file:" prefix

            if not file_path:
                raise KeyResolutionError(
                    f"Invalid encryption_key_ref format: '{key_ref}' - "
                    "expected 'file:/path/to/key'"
                )

            # Check if file exists
            if not os.path.exists(file_path):
                raise KeyResolutionError(
                    f"Encryption key file not found: '{file_path}'. "
                    f"Required by encryption_key_ref: '{key_ref}'"
                )

            # Read key from file
            try:
                with open(file_path, 'rb') as f:
                    key_bytes = f.read()
            except Exception as e:
                raise KeyResolutionError(
                    f"Failed to read encryption key from file '{file_path}': {str(e)}"
                )

            # If file contains text (hex or base64), decode it
            if len(key_bytes) > 32:
                try:
                    key_str = key_bytes.decode('utf-8').strip()
                    # Try hex decoding
                    if len(key_str) == 64:
                        key_bytes = bytes.fromhex(key_str)
                    else:
                        # Try base64 decoding
                        import base64
                        key_bytes = base64.b64decode(key_str)
                except Exception:
                    # If decoding fails, use raw bytes (truncate if needed)
                    pass

            # Validate key length
            if len(key_bytes) != 32:
                raise KeyResolutionError(
                    f"Encryption key from file '{file_path}' must be exactly 32 bytes, "
                    f"got {len(key_bytes)} bytes"
                )

            return key_bytes

        else:
            raise KeyResolutionError(
                f"Invalid encryption_key_ref format: '{key_ref}'. "
                "Must start with 'env:' or 'file:'"
            )

    def get_system_config(self, system_id: str) -> SystemConfig:
        """
        Get configuration for a specific system_id.
        
        Retrieves the SystemConfig for the given system_id from the loaded policy.
        If the policy has not been loaded, raises an error.
        
        This method is thread-safe and will return consistent results even during
        a policy reload operation.
        
        Args:
            system_id: System identifier
            
        Returns:
            SystemConfig for the system
            
        Raises:
            SystemNotFoundError: If system_id not found in policy
            PolicyValidationError: If policy has not been loaded
            
        Example:
            >>> loader = PolicyLoader()
            >>> await loader.load_policy("policies/config.yaml")
            >>> config = loader.get_system_config("customer_db")
            >>> print(config.structured.pii_fields)
        """
        with self._lock:
            if self.policy is None:
                raise PolicyValidationError(
                    "Policy has not been loaded. Call load_policy() first."
                )

            # Search for system_id in policy
            for system in self.policy.systems:
                if system.system_id == system_id:
                    return system

            # System not found
            available_systems = [s.system_id for s in self.policy.systems]
            raise SystemNotFoundError(
                f"System '{system_id}' not found in policy. "
                f"Available systems: {', '.join(available_systems)}"
            )

    def get_encryption_key(self, system_id: str) -> bytes:
        """
        Get the resolved encryption key for a system.
        
        Returns the cached encryption key that was resolved during load_policy().
        
        This method is thread-safe and will return consistent results even during
        a policy reload operation.
        
        Args:
            system_id: System identifier
            
        Returns:
            32-byte encryption key
            
        Raises:
            SystemNotFoundError: If system_id not found
            
        Example:
            >>> loader = PolicyLoader()
            >>> await loader.load_policy("policies/config.yaml")
            >>> key = loader.get_encryption_key("customer_db")
            >>> len(key)
            32
        """
        with self._lock:
            if system_id not in self._encryption_keys:
                raise SystemNotFoundError(
                    f"Encryption key not found for system '{system_id}'. "
                    "Ensure policy has been loaded."
                )

            return self._encryption_keys[system_id]

    def get_policy_version(self) -> str:
        """
        Get the current policy version.
        
        Returns:
            Policy version string, or "unknown" if policy not loaded
            
        Example:
            >>> loader = PolicyLoader()
            >>> await loader.load_policy("policies/config.yaml")
            >>> version = loader.get_policy_version()
        """
        with self._lock:
            if self.policy is None:
                return "unknown"
            return self.policy.version

    def get_policy_version(self) -> str:
        """
        Get the current policy version.

        Returns:
            Policy version string, or "unknown" if policy not loaded

        Example:
            >>> loader = PolicyLoader()
            >>> await loader.load_policy("policies/config.yaml")
            >>> version = loader.get_policy_version()
        """
        with self._lock:
            if self.policy is None:
                return "unknown"
            return self.policy.version

