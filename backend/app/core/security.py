from __future__ import annotations

import time
from typing import Any, Dict, Optional
import uuid

import httpx
from fastapi import Depends, HTTPException, Request, status
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db


_JWKS_CACHE: dict[str, Any] = {}
_JWKS_TS: float | None = None
_JWKS_TTL_SECONDS = 15 * 60


def _get_jwks(jwks_url: str) -> Dict[str, Any]:
    global _JWKS_TS
    if _JWKS_TS and (time.time() - _JWKS_TS) < _JWKS_TTL_SECONDS and _JWKS_CACHE:
        return _JWKS_CACHE
    resp = httpx.get(jwks_url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    _JWKS_TS = time.time()
    _JWKS_CACHE.clear()
    _JWKS_CACHE.update(data)
    return data


def extract_bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return auth.split(" ", 1)[1]


def verify_jwt(token: str) -> Dict[str, Any]:
    settings = get_settings()
    if not (settings.CLERK_JWKS_URL and settings.CLERK_ISSUER):
        raise HTTPException(status_code=500, detail="Auth is not configured")
    jwks = _get_jwks(settings.CLERK_JWKS_URL)
    has_audience = bool(settings.CLERK_AUDIENCE)
    try:
        claims = jwt.decode(
            token,
            jwks,
            options={"verify_aud": has_audience, "verify_iss": True},
            audience=settings.CLERK_AUDIENCE if has_audience else None,
            issuer=settings.CLERK_ISSUER,
            algorithms=["RS256"],
        )
        return claims
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


async def current_user(request: Request) -> Dict[str, Any]:
    """
    Return authenticated user, or a dev-mode fallback user when Clerk
    is not configured (ENVIRONMENT=development).
    """
    # 1. If middleware already resolved user, return it
    if hasattr(request.state, "user") and request.state.user:
        return request.state.user

    settings = get_settings()

    # 2. Dev mode: return a default test user so endpoints work without Clerk
    #    (When a valid Bearer token IS provided, it still gets verified as Clerk below)
    if settings.ENVIRONMENT == "development":
        # Check if there's a valid Bearer token first
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and len(auth_header) > 20:
            # Try Clerk JWT verification — if it works, use real user
            try:
                token = auth_header.split(" ", 1)[1]
                claims = verify_jwt(token)
                clerk_id = claims.get("sub", "")
                email = claims.get("email") or claims.get("primary_email_address") or f"{clerk_id}@clerk.local"
                user_data = {"id": clerk_id, "email": email}
                request.state.user = user_data
                return user_data
            except Exception:
                pass  # Invalid token — fall through to dev user

        import structlog
        log = structlog.get_logger()
        log.info("auth.dev_mode_user", path=request.url.path)
        dev_user = {
            "id": "dev-user-001",
            "email": "dev@gemmaFin.local",
            "role": "admin",
        }
        request.state.user = dev_user
        return dev_user

    # 3. Production: validate Clerk JWT
    try:
        token = extract_bearer(request)
        claims = verify_jwt(token)
        clerk_id = claims.get("sub", "")
        email = claims.get("email") or claims.get("primary_email_address") or f"{clerk_id}@clerk.local"
        user_data = {"id": clerk_id, "email": email}
        request.state.user = user_data
        return user_data
    except HTTPException:
        raise
    except Exception as exc:
        import structlog
        log = structlog.get_logger()
        log.warning("auth.no_token", path=request.url.path, error=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


async def get_db_user(
    request: Request,
    user: Dict[str, Any] = Depends(current_user),
    db: AsyncSession = Depends(get_db),  # resolved at call site
) -> Dict[str, Any]:
    """
    Resolve Clerk ID → DB user row, auto-creating on first login.
    Returns dict with 'db_id' (UUID str) alongside 'id' (Clerk string) and 'email'.
    """
    from app.db import crud
    clerk_id: str = user["id"]

    db_user = await crud.get_user_by_clerk_id(db, clerk_id)
    if not db_user:
        email = user.get("email")
        if not email:
            email = "unknown@example.com"
            
        # Default new users to finance_analyst (FinOps context).
        # Preserve admin role when explicitly set in dev mode.
        requested_role = user.get("role")
        db_role = "admin" if requested_role == "admin" else "finance_analyst"
        db_user = await crud.create_user(
            db,
            clerk_id=clerk_id,
            email=email,
            role=db_role,
        )
        await crud.get_or_create_billing_account(db, db_user.id)

    return {
        "id": clerk_id,           # Clerk string — kept for backward compat
        "db_id": str(db_user.id), # Postgres UUID — use this for all SQL
        "email": db_user.email,
        "role": db_user.role,
    }


