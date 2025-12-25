"""
Session Validation Middleware for gql_ug

This middleware validates sessions created by the frontendui auth service.
It retrieves session data from Redis and populates request.scope["user"].
"""

import os
import logging
import json
from typing import Optional, Dict, Any

import redis
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Initialize Redis client (lazy initialization)
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """
    Get Redis client instance (lazy initialization).

    Returns:
        redis.Redis: Redis client instance
    """
    global _redis_client

    if _redis_client is None:
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))

        _redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
        )

        # Test connection
        try:
            _redis_client.ping()
            logger.info(f"Connected to Redis at {redis_host}:{redis_port}")
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    return _redis_client


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve session data from Redis.

    Args:
        session_id: Session identifier

    Returns:
        dict: Session data including user and token, or None if not found/expired
    """
    try:
        redis_client = get_redis_client()
        session_json = redis_client.get(f"session:{session_id}")

        if not session_json:
            return None

        session_data = json.loads(session_json)
        logger.info(f"Retrieved session: {session_id[:8]}...")
        return session_data
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        return None


def get_demo_user() -> Dict[str, Any]:
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


class SessionValidationMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for session validation.

    This middleware:
    1. Checks if DEMO mode is enabled (bypasses auth)
    2. Extracts session_id from cookie
    3. Retrieves session data from Redis
    4. Stores user in request.scope["user"] for downstream use
    """

    def __init__(self, app, demo_mode: bool = False, session_maker_factory=None):
        super().__init__(app)
        self.demo_mode = demo_mode
        self.session_maker_factory = session_maker_factory
        self.demo_user = get_demo_user()

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process each request through the session validation pipeline.
        """
        # Skip authentication for health check, metrics, and docs endpoints
        if request.url.path in ["/health", "/metrics", "/voyager", "/doc"]:
            return await call_next(request)

        # DEMO mode: bypass authentication
        if self.demo_mode:
            logger.info("DEMO mode enabled - using demo user")
            request.scope["user"] = self.demo_user
            return await call_next(request)

        # Get session_id from cookie
        session_id = request.cookies.get("session_id")

        if not session_id:
            logger.warning("No session_id cookie found")
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing session cookie. Please login at /auth/login"}
            )

        # Retrieve session from Redis
        try:
            session_data = get_session(session_id)

            if not session_data:
                logger.warning(f"Session not found or expired: {session_id[:8]}...")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Session expired or invalid. Please login again."}
                )

            # Extract user data from session
            user_data = session_data.get("user")

            if not user_data:
                logger.error(f"Session missing user data: {session_id[:8]}...")
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Invalid session data"}
                )

            # JIT user provisioning: sync user from session to database
            if self.session_maker_factory and user_data.get("source") == "azure_ad":
                try:
                    from src.auth.azure_ad import get_or_create_user

                    # Map session user data to azure_user format expected by get_or_create_user
                    azure_user = {
                        "id": user_data.get("id"),
                        "displayName": f"{user_data.get('name', '')} {user_data.get('surname', '')}".strip(),
                        "givenName": user_data.get("name"),
                        "surname": user_data.get("surname"),
                        "mail": user_data.get("email"),
                        "userPrincipalName": user_data.get("userPrincipalName", user_data.get("email"))
                    }

                    # Get the session maker (cached by singleCall decorator)
                    session_maker = await self.session_maker_factory()

                    # Get or create user in database and get their DB user ID
                    db_user = await get_or_create_user(session_maker, azure_user)

                    # Replace session user data with database user data
                    user_data = db_user

                    logger.info(f"Synced user to database: {user_data.get('email')} (DB ID: {user_data.get('id')})")
                except Exception as e:
                    logger.error(f"Error in JIT user provisioning: {e}", exc_info=True)
                    # Continue with session user data even if DB sync fails
                    logger.warning("Continuing with session user data (DB sync failed)")

            # Store user in request scope for downstream use
            request.scope["user"] = user_data

            logger.info(f"Authenticated user: {user_data.get('email')} (session: {session_id[:8]}...)")

            # Proceed with request
            return await call_next(request)

        except Exception as e:
            logger.error(f"Error validating session: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )
