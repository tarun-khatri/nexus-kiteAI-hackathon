"""
Test configuration - disables the buggy web3 pytest_ethereum plugin
which has an import error with newer eth_typing versions.
"""
import sys
import pytest


def pytest_configure(config):
    # Block the broken web3 pytest plugin that ships with web3.py
    broken_modules = [
        "web3.tools",
        "web3.tools.pytest_ethereum",
        "web3.tools.pytest_ethereum.deployer",
    ]
    for mod in broken_modules:
        sys.modules[mod] = None  # type: ignore
