"""Explicitly gated, read-only app-server integration.

Imports and object construction are inert.  Only ``list_one_page`` may start
the operator-selected process.
"""

from .client import (
    IntegrationAuthorization,
    IntegrationError,
    ProjectListRunResult,
    ProjectListRunSummary,
    ReadOnlyProjectListClient,
)

__all__ = [
    "IntegrationAuthorization",
    "IntegrationError",
    "ProjectListRunResult",
    "ProjectListRunSummary",
    "ReadOnlyProjectListClient",
]
