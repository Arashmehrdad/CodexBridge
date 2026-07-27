"""Additive project-identity authority for canonical task/run work."""

from .models import (
    PROJECT_SCOPE_MODEL_VERSION,
    PROJECT_SCOPE_SCHEMA_COMPONENT,
    PROJECT_SCOPE_SCHEMA_VERSION,
    ProjectScopeError,
    ProjectScopeMismatch,
    RepositoryBinding,
    ScopeProjection,
)
from .store import ProjectScopeStore

__all__ = [
    "PROJECT_SCOPE_MODEL_VERSION",
    "PROJECT_SCOPE_SCHEMA_COMPONENT",
    "PROJECT_SCOPE_SCHEMA_VERSION",
    "ProjectScopeError",
    "ProjectScopeMismatch",
    "ProjectScopeStore",
    "RepositoryBinding",
    "ScopeProjection",
]
