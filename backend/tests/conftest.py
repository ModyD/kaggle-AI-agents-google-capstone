"""
Pytest configuration and shared fixtures.
"""

import os
import sys

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    # Ensure we use stub mode for tests
    os.environ["USE_STUB_LLM"] = "true"
    os.environ["DEBUG"] = "true"
    yield
