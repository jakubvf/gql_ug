"""
Microsoft Entra ID (Azure AD) Authentication Implementation

This module provides:
- Token validation using MSAL
- User information retrieval from Microsoft Graph API
- FastAPI middleware for authentication
- Just-in-time (JIT) user provisioning
"""

import os
import logging
import uuid
import datetime
from typing import Optional, Dict, Any
from functools import lru_cache

import msal
import requests
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from sqlalchemy.future import select

# Microsoft Graph API base URL
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"


@lru_cache()
def get_azure_config() -> Dict[str, Any]:
    """
    Get Azure AD configuration from environment variables.
    Cached to avoid repeated environment variable lookups.

    Returns:
        dict: Azure AD configuration
    """
    # Allow None for optional config when DEMO mode is enabled
    return {
        "client_id": os.getenv("AZURE_CLIENT_ID"),
        "client_secret": os.getenv("AZURE_CLIENT_SECRET"),
        "tenant_id": os.getenv("AZURE_TENANT_ID"),
        "redirect_uri": os.getenv("AZURE_REDIRECT_URI", "http://localhost:8000/auth/callback"),
        "scopes": os.getenv("AZURE_SCOPES", "User.Read,User.ReadBasic.All").split(","),
        "authority": f"https://login.microsoftonline.com/{os.getenv('AZURE_TENANT_ID', 'common')}",
    }


def get_msal_app() -> msal.ConfidentialClientApplication:
    """
    Create MSAL confidential client application for token validation.

    Returns:
        msal.ConfidentialClientApplication: MSAL app instance
    """
    config = get_azure_config()
    return msal.ConfidentialClientApplication(
        client_id=config["client_id"],
        client_credential=config["client_secret"],
        authority=config["authority"]
    )


def verify_azure_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify Azure AD access token.

    In production, this should validate the JWT signature using Microsoft's public keys.
    For MVP, we'll use a simpler approach: try to use the token with Graph API.

    Args:
        token: Bearer token from Authorization header

    Returns:
        dict: Token claims if valid, None otherwise
    """
    try:
        # Simple validation: try to get user info with the token
        # If it works, token is valid
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{GRAPH_API_BASE}/me",
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            user_info = response.json()
            # Return claims-like structure
            return {
                "oid": user_info.get("id"),  # Object ID in Azure AD
                "preferred_username": user_info.get("userPrincipalName"),
                "name": user_info.get("displayName"),
                "email": user_info.get("mail") or user_info.get("userPrincipalName"),
            }
        else:
            logging.warning(f"Token validation failed: {response.status_code}")
            return None

    except Exception as e:
        logging.error(f"Error validating token: {e}")
        return None


def get_user_info_from_graph(token: str) -> Optional[Dict[str, Any]]:
    """
    Get user information from Microsoft Graph API.

    Args:
        token: Valid Azure AD access token

    Returns:
        dict: User information from Graph API

    Sample return structure:
    {
        "id": "azure-ad-object-id",
        "displayName": "John Doe",
        "userPrincipalName": "john@example.com",
        "mail": "john@example.com",
        "givenName": "John",
        "surname": "Doe"
    }
    """
    try:
        headers = {"Authorization": f"Bearer {token}"}

        # Get user profile
        response = requests.get(
            f"{GRAPH_API_BASE}/me?$select=id,displayName,userPrincipalName,mail,givenName,surname",
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            logging.error(f"Failed to get user info from Graph API: {response.status_code}")
            return None

        user_info = response.json()

        # Optionally get user's group memberships (for future use)
        # This requires Group.Read.All or Directory.Read.All permissions
        try:
            groups_response = requests.get(
                f"{GRAPH_API_BASE}/me/memberOf?$select=id,displayName",
                headers=headers,
                timeout=10
            )
            if groups_response.status_code == 200:
                user_info["groups"] = groups_response.json().get("value", [])
        except Exception as e:
            logging.warning(f"Could not fetch user groups: {e}")
            user_info["groups"] = []

        return user_info

    except Exception as e:
        logging.error(f"Error getting user info from Graph API: {e}")
        return None


def map_azure_user_to_internal(azure_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map Azure AD user attributes to internal user model structure.

    This creates the user dict that will be stored in request.scope["user"]
    and retrieved by getUserFromInfo() in Dataloaders.py.

    Args:
        azure_user: User info from Microsoft Graph API

    Returns:
        dict: User info in internal format
    """
    # Extract names
    display_name = azure_user.get("displayName", "")
    given_name = azure_user.get("givenName", "")
    surname = azure_user.get("surname", "")

    # If no given_name/surname, try to split displayName
    if not given_name and not surname and display_name:
        parts = display_name.split(" ", 1)
        given_name = parts[0]
        surname = parts[1] if len(parts) > 1 else ""

    return {
        "id": azure_user["id"],  # Azure AD Object ID
        "externalId": azure_user["id"],  # Store Azure AD ID as external ID
        "name": given_name or display_name,
        "surname": surname,
        "email": azure_user.get("mail") or azure_user.get("userPrincipalName"),
        "userPrincipalName": azure_user.get("userPrincipalName"),
        "azure_groups": azure_user.get("groups", []),
        "source": "azure_ad"
    }


async def get_or_create_user(session_maker, azure_user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get existing user from database or create new user (JIT provisioning).

    Args:
        session_maker: SQLAlchemy async session maker
        azure_user: User info from Microsoft Graph API

    Returns:
        dict: User info in internal format with database ID
    """
    from src.DBDefinitions import UserModel

    azure_id = azure_user["id"]

    # Try to find user by Azure AD Object ID
    # We'll use email as the unique identifier since we don't have an externalId field
    email = azure_user.get("mail") or azure_user.get("userPrincipalName")

    async with session_maker() as session:
        # Look for existing user by email
        stmt = select(UserModel).where(UserModel.email == email)
        result = await session.execute(stmt)
        db_user = result.scalar_one_or_none()

        if db_user:
            # User exists, return their info
            logging.info(f"Found existing user: {email} (ID: {db_user.id})")
            return {
                "id": str(db_user.id),
                "name": db_user.name or "",
                "surname": db_user.surname or "",
                "email": db_user.email,
                "valid": db_user.valid,
                "source": "azure_ad",
                "azure_id": azure_id
            }

        # User doesn't exist, create new user (JIT provisioning)
        display_name = azure_user.get("displayName", "")
        given_name = azure_user.get("givenName", "")
        surname = azure_user.get("surname", "")

        # If no given_name/surname, try to split displayName
        if not given_name and not surname and display_name:
            parts = display_name.split(" ", 1)
            given_name = parts[0]
            surname = parts[1] if len(parts) > 1 else ""

        new_user = UserModel(
            id=uuid.uuid4(),  # Generate new UUID for internal DB
            name=given_name or display_name,
            givenname=given_name,
            surname=surname,
            email=email,
            valid=True,
            startdate=datetime.datetime.now()
        )

        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)

        logging.info(f"Created new user via JIT provisioning: {email} (ID: {new_user.id})")

        return {
            "id": str(new_user.id),
            "name": new_user.name or "",
            "surname": new_user.surname or "",
            "email": new_user.email,
            "valid": new_user.valid,
            "source": "azure_ad",
            "azure_id": azure_id
        }


class AzureADAuthMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for Azure AD authentication.

    This middleware:
    1. Checks if DEMO mode is enabled (bypasses auth)
    2. Extracts Bearer token from Authorization header
    3. Validates token with Azure AD
    4. Retrieves user info from Microsoft Graph API
    5. Creates/updates user in database (JIT provisioning)
    6. Stores user in request.scope["user"] for downstream use
    """

    def __init__(self, app, demo_mode: bool = False, session_maker_factory=None):
        super().__init__(app)
        self.demo_mode = demo_mode
        self.session_maker_factory = session_maker_factory
        self.demo_user = self._create_demo_user()

    def _create_demo_user(self) -> Dict[str, Any]:
        """Create a demo user for development mode"""
        return {
            "id": "2d9dc5ca-a4a2-11ed-b9df-0242ac120003",
            "externalId": "demo-user-azure-id",
            "name": "John",
            "surname": "Newbie",
            "email": "john.newbie@world.com",
            "userPrincipalName": "john.newbie@world.com",
            "source": "demo",
            "roles": [
                {
                    "valid": True,
                    "group": {
                        "id": "2d9dcd22-a4a2-11ed-b9df-0242ac120003",
                        "name": "Uni"
                    },
                    "roletype": {
                        "id": "ced46aa4-3217-4fc1-b79d-f6be7d21c6b6",
                        "name": "administrátor"
                    }
                }
            ]
        }

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process each request through the authentication pipeline.
        """
        # Skip authentication for health check, metrics, docs, and auth endpoints
        if request.url.path in ["/health", "/metrics", "/voyager", "/doc", "/auth/login", "/auth/callback"]:
            return await call_next(request)

        # DEMO mode: bypass authentication
        if self.demo_mode:
            logging.info("DEMO mode enabled - using demo user")
            request.scope["user"] = self.demo_user
            return await call_next(request)

        # Extract Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            logging.warning("No Authorization header found")
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header"}
            )

        # Extract Bearer token
        try:
            scheme, token = auth_header.split()
            if scheme.lower() != "bearer":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid authentication scheme. Expected Bearer."}
                )
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid Authorization header format"}
            )

        # Validate token and get user info
        token_claims = verify_azure_token(token)
        if not token_claims:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"}
            )

        # Get full user info from Graph API
        azure_user = get_user_info_from_graph(token)
        if not azure_user:
            return JSONResponse(
                status_code=500,
                content={"detail": "Failed to retrieve user information"}
            )

        # JIT provisioning: get or create user in database
        if self.session_maker_factory:
            try:
                # Get the session maker (it's cached by the singleCall decorator)
                session_maker = await self.session_maker_factory()
                internal_user = await get_or_create_user(session_maker, azure_user)
            except Exception as e:
                logging.error(f"Error in JIT user provisioning: {e}", exc_info=True)
                # Fallback to mapping without DB persistence
                internal_user = map_azure_user_to_internal(azure_user)
        else:
            # No session maker provided, just map without DB persistence
            internal_user = map_azure_user_to_internal(azure_user)

        # Store user in request scope for downstream use
        request.scope["user"] = internal_user

        logging.info(f"Authenticated user: {internal_user['email']} ({internal_user['id']})")

        # Proceed with request
        return await call_next(request)
