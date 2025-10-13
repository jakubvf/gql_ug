"""
Azure AD Authentication Module
Provides Microsoft Entra ID (Azure AD) authentication for the GraphQL API
"""

from .azure_ad import (
    AzureADAuthMiddleware,
    get_azure_config,
    verify_azure_token,
    get_user_info_from_graph,
)

__all__ = [
    "AzureADAuthMiddleware",
    "get_azure_config",
    "verify_azure_token",
    "get_user_info_from_graph",
]
