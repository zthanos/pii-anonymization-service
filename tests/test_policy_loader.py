"""Tests for PolicyLoader class."""

import os
import tempfile
from pathlib import Path

import pytest

from src.pii_service.core.policy_loader import (
    KeyResolutionError,
    PolicyLoader,
    PolicyValidationError,
    SystemNotFoundError,
)
from src.pii_service.models.policy import Policy


class TestPolicyLoader:
    """Test suite for PolicyLoader class."""
    
    @pytest.fixture
    def valid_policy_yaml(self):
        """Valid policy YAML content."""
        return """
systems:
  - system_id: "test_system"
    encryption_key_ref: "env:TEST_KEY"
    structured:
      pii_fields:
        - name: "email"
          deterministic: true
          token_format: "uuid"
          nullable: false
        - name: "address.street"
          deterministic: false
          token_format: "prefixed"
          token_prefix: "ADDR_"
          nullable: true
      token_ttl_seconds: 86400
    unstructured:
      llm_model: "claude-3-haiku-20240307"
      entity_types: ["PERSON", "EMAIL", "PHONE"]
      rate_limit_per_minute: 100
      max_text_length: 50000

  - system_id: "analytics_db"
    encryption_key_ref: "file:/tmp/test_key.bin"
    structured:
      pii_fields:
        - name: "user_id"
          deterministic: true
          token_format: "deterministic"
          nullable: false
      token_ttl_seconds: 0

default_system: "test_system"
"""
    
    @pytest.fixture
    def invalid_yaml(self):
        """Invalid YAML syntax."""
        return """
systems:
  - system_id: "test"
    encryption_key_ref: "env:KEY"
    structured:
      pii_fields:
        - name: "email"
          invalid_indent
"""
    
    @pytest.fixture
    def missing_required_field_yaml(self):
        """YAML missing required fields."""
        return """
systems:
  - system_id: "test"
    structured:
      pii_fields:
        - name: "email"
"""
    
    @pytest.fixture
    def invalid_key_ref_yaml(self):
        """YAML with invalid encryption_key_ref format."""
        return """
systems:
  - system_id: "test"
    encryption_key_ref: "invalid_format"
    structured:
      pii_fields:
        - name: "email"
"""
    
    @pytest.fixture
    def duplicate_system_ids_yaml(self):
        """YAML with duplicate system_ids."""
        return """
systems:
  - system_id: "test"
    encryption_key_ref: "env:KEY1"
    structured:
      pii_fields:
        - name: "email"
  - system_id: "test"
    encryption_key_ref: "env:KEY2"
    structured:
      pii_fields:
        - name: "phone"
"""
    
    @pytest.fixture
    def test_key_hex(self):
        """32-byte key as hex string."""
        return "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    
    @pytest.fixture
    def test_key_bytes(self, test_key_hex):
        """32-byte key as bytes."""
        return bytes.fromhex(test_key_hex)
    
    @pytest.fixture
    def setup_env_key(self, test_key_hex):
        """Set up environment variable with test key."""
        os.environ["TEST_KEY"] = test_key_hex
        yield
        # Cleanup
        if "TEST_KEY" in os.environ:
            del os.environ["TEST_KEY"]
    
    @pytest.fixture
    def setup_file_key(self, test_key_bytes):
        """Set up file with test key."""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(test_key_bytes)
            temp_path = f.name
        
        yield temp_path
        
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_load_valid_policy(self, valid_policy_yaml, setup_env_key, setup_file_key):
        """Test loading a valid policy file."""
        # Create temporary policy file
        # Escape backslashes for Windows paths in YAML
        escaped_path = setup_file_key.replace('\\', '\\\\')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(valid_policy_yaml.replace("/tmp/test_key.bin", escaped_path))
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            policy = await loader.load_policy(temp_path)
            
            # Verify policy loaded correctly
            assert isinstance(policy, Policy)
            assert len(policy.systems) == 2
            assert policy.default_system == "test_system"
            
            # Verify first system
            system1 = policy.systems[0]
            assert system1.system_id == "test_system"
            assert system1.structured is not None
            assert len(system1.structured.pii_fields) == 2
            assert system1.structured.token_ttl_seconds == 86400
            assert system1.unstructured is not None
            
            # Verify second system
            system2 = policy.systems[1]
            assert system2.system_id == "analytics_db"
            assert system2.structured is not None
            assert len(system2.structured.pii_fields) == 1
            assert system2.structured.token_ttl_seconds == 0
            
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_load_policy_file_not_found(self):
        """Test loading policy from non-existent file."""
        loader = PolicyLoader()
        
        with pytest.raises(PolicyValidationError) as exc_info:
            await loader.load_policy("/nonexistent/policy.yaml")
        
        assert "Policy file not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_load_policy_invalid_yaml(self, invalid_yaml):
        """Test loading policy with invalid YAML syntax."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(invalid_yaml)
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            
            with pytest.raises(PolicyValidationError) as exc_info:
                await loader.load_policy(temp_path)
            
            assert "Invalid YAML syntax" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_load_policy_missing_required_field(self, missing_required_field_yaml):
        """Test loading policy with missing required fields."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(missing_required_field_yaml)
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            
            with pytest.raises(PolicyValidationError) as exc_info:
                await loader.load_policy(temp_path)
            
            assert "Policy validation failed" in str(exc_info.value)
            assert "encryption_key_ref" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_load_policy_invalid_key_ref_format(self, invalid_key_ref_yaml):
        """Test loading policy with invalid encryption_key_ref format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(invalid_key_ref_yaml)
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            
            with pytest.raises(PolicyValidationError) as exc_info:
                await loader.load_policy(temp_path)
            
            assert "encryption_key_ref must start with 'env:' or 'file:'" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_load_policy_duplicate_system_ids(self, duplicate_system_ids_yaml, setup_env_key):
        """Test loading policy with duplicate system_ids."""
        # Set up both keys
        os.environ["KEY1"] = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        os.environ["KEY2"] = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(duplicate_system_ids_yaml)
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            
            with pytest.raises(PolicyValidationError) as exc_info:
                await loader.load_policy(temp_path)
            
            assert "Duplicate system_id values found" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
            if "KEY1" in os.environ:
                del os.environ["KEY1"]
            if "KEY2" in os.environ:
                del os.environ["KEY2"]
    
    def test_resolve_encryption_key_env_hex(self, test_key_hex, test_key_bytes):
        """Test resolving encryption key from environment variable (hex format)."""
        os.environ["TEST_KEY"] = test_key_hex
        
        try:
            loader = PolicyLoader()
            key = loader.resolve_encryption_key("env:TEST_KEY")
            
            assert key == test_key_bytes
            assert len(key) == 32
        finally:
            del os.environ["TEST_KEY"]
    
    def test_resolve_encryption_key_env_base64(self):
        """Test resolving encryption key from environment variable (base64 format)."""
        import base64
        key_bytes = os.urandom(32)
        key_b64 = base64.b64encode(key_bytes).decode('utf-8')
        
        os.environ["TEST_KEY_B64"] = key_b64
        
        try:
            loader = PolicyLoader()
            key = loader.resolve_encryption_key("env:TEST_KEY_B64")
            
            assert key == key_bytes
            assert len(key) == 32
        finally:
            del os.environ["TEST_KEY_B64"]
    
    def test_resolve_encryption_key_env_missing(self):
        """Test resolving encryption key from missing environment variable."""
        loader = PolicyLoader()
        
        with pytest.raises(KeyResolutionError) as exc_info:
            loader.resolve_encryption_key("env:NONEXISTENT_KEY")
        
        assert "Environment variable 'NONEXISTENT_KEY' not found" in str(exc_info.value)
    
    def test_resolve_encryption_key_env_invalid_length(self):
        """Test resolving encryption key with invalid length."""
        os.environ["SHORT_KEY"] = "0123456789abcdef"  # Only 16 bytes
        
        try:
            loader = PolicyLoader()
            
            with pytest.raises(KeyResolutionError) as exc_info:
                loader.resolve_encryption_key("env:SHORT_KEY")
            
            assert "must be exactly 32 bytes" in str(exc_info.value)
        finally:
            del os.environ["SHORT_KEY"]
    
    def test_resolve_encryption_key_file_binary(self, test_key_bytes):
        """Test resolving encryption key from binary file."""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(test_key_bytes)
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            key = loader.resolve_encryption_key(f"file:{temp_path}")
            
            assert key == test_key_bytes
            assert len(key) == 32
        finally:
            os.unlink(temp_path)
    
    def test_resolve_encryption_key_file_hex(self, test_key_hex, test_key_bytes):
        """Test resolving encryption key from hex-encoded file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(test_key_hex)
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            key = loader.resolve_encryption_key(f"file:{temp_path}")
            
            assert key == test_key_bytes
            assert len(key) == 32
        finally:
            os.unlink(temp_path)
    
    def test_resolve_encryption_key_file_not_found(self):
        """Test resolving encryption key from non-existent file."""
        loader = PolicyLoader()
        
        with pytest.raises(KeyResolutionError) as exc_info:
            loader.resolve_encryption_key("file:/nonexistent/key.bin")
        
        assert "Encryption key file not found" in str(exc_info.value)
    
    def test_resolve_encryption_key_invalid_format(self):
        """Test resolving encryption key with invalid reference format."""
        loader = PolicyLoader()
        
        with pytest.raises(KeyResolutionError) as exc_info:
            loader.resolve_encryption_key("invalid:format")
        
        assert "Must start with 'env:' or 'file:'" in str(exc_info.value)
    
    def test_resolve_encryption_key_empty_env_name(self):
        """Test resolving encryption key with empty env variable name."""
        loader = PolicyLoader()
        
        with pytest.raises(KeyResolutionError) as exc_info:
            loader.resolve_encryption_key("env:")
        
        assert "expected 'env:VAR_NAME'" in str(exc_info.value)
    
    def test_resolve_encryption_key_empty_file_path(self):
        """Test resolving encryption key with empty file path."""
        loader = PolicyLoader()
        
        with pytest.raises(KeyResolutionError) as exc_info:
            loader.resolve_encryption_key("file:")
        
        assert "expected 'file:/path/to/key'" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_system_config_success(self, valid_policy_yaml, setup_env_key, setup_file_key):
        """Test getting system configuration successfully."""
        escaped_path = setup_file_key.replace('\\', '\\\\')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(valid_policy_yaml.replace("/tmp/test_key.bin", escaped_path))
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            await loader.load_policy(temp_path)
            
            config = loader.get_system_config("test_system")
            
            assert config.system_id == "test_system"
            assert config.structured is not None
            assert len(config.structured.pii_fields) == 2
            assert config.unstructured is not None
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_get_system_config_not_found(self, valid_policy_yaml, setup_env_key, setup_file_key):
        """Test getting non-existent system configuration."""
        escaped_path = setup_file_key.replace('\\', '\\\\')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(valid_policy_yaml.replace("/tmp/test_key.bin", escaped_path))
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            await loader.load_policy(temp_path)
            
            with pytest.raises(SystemNotFoundError) as exc_info:
                loader.get_system_config("nonexistent_system")
            
            assert "System 'nonexistent_system' not found" in str(exc_info.value)
            assert "Available systems:" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
    
    def test_get_system_config_policy_not_loaded(self):
        """Test getting system config before loading policy."""
        loader = PolicyLoader()
        
        with pytest.raises(PolicyValidationError) as exc_info:
            loader.get_system_config("test_system")
        
        assert "Policy has not been loaded" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_encryption_key_success(self, valid_policy_yaml, setup_env_key, setup_file_key, test_key_bytes):
        """Test getting cached encryption key."""
        escaped_path = setup_file_key.replace('\\', '\\\\')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(valid_policy_yaml.replace("/tmp/test_key.bin", escaped_path))
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            await loader.load_policy(temp_path)
            
            key = loader.get_encryption_key("test_system")
            
            assert key == test_key_bytes
            assert len(key) == 32
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_get_encryption_key_not_found(self, valid_policy_yaml, setup_env_key, setup_file_key):
        """Test getting encryption key for non-existent system."""
        escaped_path = setup_file_key.replace('\\', '\\\\')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(valid_policy_yaml.replace("/tmp/test_key.bin", escaped_path))
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            await loader.load_policy(temp_path)
            
            with pytest.raises(SystemNotFoundError) as exc_info:
                loader.get_encryption_key("nonexistent_system")
            
            assert "Encryption key not found for system 'nonexistent_system'" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_reload_policy_success(self, valid_policy_yaml, setup_env_key, setup_file_key):
        """Test successful policy reload."""
        escaped_path = setup_file_key.replace('\\', '\\\\')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(valid_policy_yaml.replace("/tmp/test_key.bin", escaped_path))
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            await loader.load_policy(temp_path)
            
            # Get initial system count
            initial_system_count = len(loader.policy.systems)
            assert initial_system_count == 2
            
            # Modify the policy file (add a new system)
            # Note: Must maintain proper YAML structure
            updated_yaml = """
systems:
  - system_id: "test_system"
    encryption_key_ref: "env:TEST_KEY"
    structured:
      pii_fields:
        - name: "email"
          deterministic: true
          token_format: "uuid"
          nullable: false
      token_ttl_seconds: 86400

  - system_id: "analytics_db"
    encryption_key_ref: "file:{}"
    structured:
      pii_fields:
        - name: "user_id"
          deterministic: true
          token_format: "deterministic"
          nullable: false
      token_ttl_seconds: 0

  - system_id: "new_system"
    encryption_key_ref: "env:TEST_KEY"
    structured:
      pii_fields:
        - name: "phone"
          deterministic: false
          token_format: "uuid"
          nullable: false
      token_ttl_seconds: 3600

default_system: "test_system"
""".format(escaped_path)
            
            with open(temp_path, 'w') as f:
                f.write(updated_yaml)
            
            # Reload policy
            new_policy = await loader.reload_policy()
            
            # Verify policy was reloaded
            assert new_policy is not None
            assert len(new_policy.systems) == 3  # Original 2 + new 1
            
            # Verify new system is accessible
            new_system_config = loader.get_system_config("new_system")
            assert new_system_config.system_id == "new_system"
            assert new_system_config.structured.pii_fields[0].name == "phone"
            
            # Verify encryption key was cached for new system
            new_key = loader.get_encryption_key("new_system")
            assert len(new_key) == 32
            
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_reload_policy_validation_failure_retains_current(self, valid_policy_yaml, setup_env_key, setup_file_key):
        """Test that reload retains current policy when validation fails."""
        escaped_path = setup_file_key.replace('\\', '\\\\')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(valid_policy_yaml.replace("/tmp/test_key.bin", escaped_path))
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            await loader.load_policy(temp_path)
            
            # Get initial policy
            initial_policy = loader.policy
            initial_systems = [s.system_id for s in initial_policy.systems]
            
            # Write invalid YAML to the file
            with open(temp_path, 'w') as f:
                f.write("invalid: yaml: syntax: [")
            
            # Attempt reload - should fail
            with pytest.raises(PolicyValidationError) as exc_info:
                await loader.reload_policy()
            
            assert "Policy reload failed, retaining current policy" in str(exc_info.value)
            
            # Verify current policy is still intact
            assert loader.policy is not None
            current_systems = [s.system_id for s in loader.policy.systems]
            assert current_systems == initial_systems
            
            # Verify we can still get system configs
            config = loader.get_system_config("test_system")
            assert config.system_id == "test_system"
            
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_reload_policy_missing_env_var_retains_current(self, valid_policy_yaml, setup_env_key, setup_file_key):
        """Test that reload retains current policy when encryption key resolution fails."""
        escaped_path = setup_file_key.replace('\\', '\\\\')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(valid_policy_yaml.replace("/tmp/test_key.bin", escaped_path))
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            await loader.load_policy(temp_path)
            
            # Get initial policy
            initial_policy = loader.policy
            
            # Write policy with missing environment variable
            invalid_policy = """
systems:
  - system_id: "test"
    encryption_key_ref: "env:MISSING_KEY"
    structured:
      pii_fields:
        - name: "email"
"""
            with open(temp_path, 'w') as f:
                f.write(invalid_policy)
            
            # Attempt reload - should fail
            with pytest.raises(PolicyValidationError) as exc_info:
                await loader.reload_policy()
            
            assert "Policy reload failed, retaining current policy" in str(exc_info.value)
            
            # Verify current policy is still intact
            assert loader.policy is not None
            assert loader.policy == initial_policy
            
            # Verify we can still get encryption keys
            key = loader.get_encryption_key("test_system")
            assert len(key) == 32
            
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_reload_policy_without_initial_load(self):
        """Test that reload fails if no policy was loaded initially."""
        loader = PolicyLoader()
        
        with pytest.raises(PolicyValidationError) as exc_info:
            await loader.reload_policy()
        
        assert "Cannot reload policy: no policy path set" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_reload_policy_file_deleted(self, valid_policy_yaml, setup_env_key, setup_file_key):
        """Test reload when policy file is deleted."""
        escaped_path = setup_file_key.replace('\\', '\\\\')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(valid_policy_yaml.replace("/tmp/test_key.bin", escaped_path))
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            await loader.load_policy(temp_path)
            
            # Delete the policy file
            os.unlink(temp_path)
            
            # Attempt reload - should fail
            with pytest.raises(PolicyValidationError) as exc_info:
                await loader.reload_policy()
            
            assert "Policy reload failed, retaining current policy" in str(exc_info.value)
            assert "Policy file not found" in str(exc_info.value)
            
            # Verify current policy is still accessible
            assert loader.policy is not None
            config = loader.get_system_config("test_system")
            assert config.system_id == "test_system"
            
        except:
            # Cleanup in case test fails before deletion
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
    
    @pytest.mark.asyncio
    async def test_thread_safe_policy_access_during_reload(self, valid_policy_yaml, setup_env_key, setup_file_key):
        """Test that policy access is thread-safe during reload."""
        import threading
        import time
        
        escaped_path = setup_file_key.replace('\\', '\\\\')
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(valid_policy_yaml.replace("/tmp/test_key.bin", escaped_path))
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            await loader.load_policy(temp_path)
            
            errors = []
            access_count = [0]
            
            def access_policy():
                """Thread function that accesses policy repeatedly."""
                for _ in range(10):
                    try:
                        config = loader.get_system_config("test_system")
                        assert config.system_id == "test_system"
                        access_count[0] += 1
                        time.sleep(0.01)
                    except Exception as e:
                        errors.append(str(e))
            
            # Start threads that access policy
            threads = [threading.Thread(target=access_policy) for _ in range(3)]
            for t in threads:
                t.start()
            
            # Perform reload while threads are accessing policy
            time.sleep(0.02)
            await loader.reload_policy()
            
            # Wait for threads to complete
            for t in threads:
                t.join()
            
            # Verify no errors occurred
            assert len(errors) == 0, f"Errors during concurrent access: {errors}"
            assert access_count[0] == 30  # 3 threads * 10 accesses each
            
        finally:
            os.unlink(temp_path)
    
    def test_setup_signal_handler_on_windows(self):
        """Test that setup_signal_handler handles Windows gracefully."""
        loader = PolicyLoader()
        
        # Should not raise an error even if SIGHUP is not available
        loader.setup_signal_handler()
    
    @pytest.mark.asyncio
    async def test_load_policy_missing_env_variable(self):
        """Test loading policy when referenced environment variable doesn't exist."""
        policy_yaml = """
systems:
  - system_id: "test"
    encryption_key_ref: "env:MISSING_KEY"
    structured:
      pii_fields:
        - name: "email"
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(policy_yaml)
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            
            with pytest.raises(PolicyValidationError) as exc_info:
                await loader.load_policy(temp_path)
            
            assert "Failed to resolve encryption key" in str(exc_info.value)
            assert "Environment variable 'MISSING_KEY' not found" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_load_policy_missing_file(self):
        """Test loading policy when referenced file doesn't exist."""
        policy_yaml = """
systems:
  - system_id: "test"
    encryption_key_ref: "file:/nonexistent/key.bin"
    structured:
      pii_fields:
        - name: "email"
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(policy_yaml)
            temp_path = f.name
        
        try:
            loader = PolicyLoader()
            
            with pytest.raises(PolicyValidationError) as exc_info:
                await loader.load_policy(temp_path)
            
            assert "Failed to resolve encryption key" in str(exc_info.value)
            assert "Encryption key file not found" in str(exc_info.value)
        finally:
            os.unlink(temp_path)
