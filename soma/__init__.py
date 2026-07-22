"""Soma local MCP bridge."""

from .knowledge_tools_integration import install_knowledge_tools
from .repo_discovery_integration import install_repo_discovery


__version__ = "0.1.0"

install_repo_discovery()
install_knowledge_tools()
