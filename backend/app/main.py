from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.logging import init_observability
from app.core.security import current_user, extract_bearer, verify_jwt

from app.api.v1 import analytics as analytics_router
from app.api.v1 import chat as chat_router
from app.api.v1 import documents as documents_router
from app.api.v1 import exports as exports_router
from app.api.v1 import health as health_router
from app.api.v1 import matters as matters_router
from app.api.v1 import notarization as notarization_router
from app.api.v1 import subnet_notarization as subnet_notarization_router
from app.api.v1 import privacy as privacy_router
from app.api.v1 import runs as runs_router
from app.api.v1 import subscriptions as subscriptions_router
from app.api.v1 import search as search_router
from app.api.v1 import metadata as metadata_router
from app.api.v1 import users as users_router
from app.api.v1 import compliance as compliance_router
from app.api.v1 import simulator as simulator_router
from app.api.v1 import financial as financial_router
from app.api.v1 import test as test_router
from app.api.v1 import rules_api as rules_router
from app.api.v1 import extract as extract_router
from app.api.v1 import assess as assess_router
from app.api.v1 import report as report_router
from app.api.v1 import agent as agent_router
from app.api.v1 import approvals as approvals_router
from app.api.v1 import connectors_api as connectors_router
from app.api.v1 import dashboard as dashboard_router
from app.api.v1 import knowledge as knowledge_router
from app.api.v1 import system as system_router
from app.api.v1 import invoices as invoices_router
from app.api.v1 import transactions as transactions_router
from app.api.v1 import vendors as vendors_router
from app.api.v1 import workflows as workflows_router
from app.api.v1 import policies as policies_router
from app.api.v1 import audit as audit_router


settings = get_settings()
init_observability("gemmaFin-backend")

app = FastAPI(title="GemmaFin OS Backend", version="0.1")

# Define all middleware functions
async def rls_context(request: Request, call_next):
    """Set current user context for Row Level Security"""
    if request.url.path.startswith(("/health", "/v1/health", "/metrics")):
        return await call_next(request)
    user = getattr(request.state, "user", None)
    if not user:
        return await call_next(request)
    from app.db.session import set_current_user
    try:
        set_current_user(user["id"])
        response = await call_next(request)
        return response
    except Exception as e:
        import structlog
        log = structlog.get_logger()
        log.error("rls_context.error", error=str(e), user_id=user.get("id"))
        raise

async def clerk_auth(request: Request, call_next):
    if request.url.path.startswith(("/health", "/v1/health", "/metrics")):
        return await call_next(request)
    try:
        token = extract_bearer(request)
        claims = verify_jwt(token)
        clerk_id = claims.get("sub", "")
        email = claims.get("email") or claims.get("primary_email_address") or f"{clerk_id}@clerk.local"
        request.state.user = {"id": clerk_id, "email": email}
    except Exception as e:
        import structlog
        log = structlog.get_logger()
        log.warning("auth.middleware_bypass", path=request.url.path, error=str(e))
        request.state.user = None
    return await call_next(request)

# Add middlewares in reverse order (Last added is the OUTERMOST layer)
# Inner -> Outer order:
# 1. RLS Context
# 2. Clerk Auth
# 3. Rate Limiter
# 4. Metrics
# 5. CORS (Outermost, ensuring 429s from rate limiter get CORS headers)

app.add_middleware(BaseHTTPMiddleware, dispatch=rls_context)
app.add_middleware(BaseHTTPMiddleware, dispatch=clerk_auth)

from app.core.rate_limit import rate_limiter
app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limiter(max_per_day=1000))

from app.core.monitoring import MetricsMiddleware
app.add_middleware(MetricsMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"ok": True}

app.include_router(health_router.router, prefix="/v1/health", tags=["health"])
app.include_router(users_router.router, prefix="/v1/users", tags=["users"])
app.include_router(matters_router.router, prefix="/v1", tags=["matters"])
app.include_router(documents_router.router, prefix="/v1", tags=["documents"])
app.include_router(chat_router.router, prefix="/v1", tags=["chat"])
app.include_router(runs_router.router, prefix="/v1", tags=["runs"])
app.include_router(notarization_router.router, prefix="/v1", tags=["notarization"])
app.include_router(subnet_notarization_router.router, prefix="/v1", tags=["subnet-notarization"])
app.include_router(exports_router.router, prefix="/v1", tags=["exports"])
app.include_router(privacy_router.router, prefix="/v1/privacy", tags=["privacy"])
app.include_router(subscriptions_router.router, prefix="/v1/subscriptions", tags=["subscriptions"])
app.include_router(analytics_router.router, prefix="/v1/analytics", tags=["analytics"])
app.include_router(search_router.router, prefix="/v1", tags=["search"])
app.include_router(metadata_router.router, prefix="/v1", tags=["metadata"])
app.include_router(compliance_router.router, prefix="/v1", tags=["compliance"])
app.include_router(simulator_router.router, prefix="/v1", tags=["simulator"])
app.include_router(financial_router.router, prefix="/v1", tags=["financial"])
app.include_router(test_router.router, prefix="/v1", tags=["test"])
app.include_router(rules_router.router, prefix="/v1", tags=["compliance-rules"])
app.include_router(extract_router.router, prefix="/v1", tags=["extract"])
app.include_router(assess_router.router, prefix="/v1", tags=["assess"])
app.include_router(report_router.router, prefix="/v1", tags=["report"])
app.include_router(agent_router.router, prefix="/v1", tags=["agent"])
app.include_router(approvals_router.router, prefix="/v1", tags=["approvals"])
app.include_router(connectors_router.router, prefix="/v1", tags=["connectors"])
app.include_router(dashboard_router.router, prefix="/v1", tags=["dashboard"])
app.include_router(knowledge_router.router, prefix="/v1", tags=["knowledge"])
app.include_router(system_router.router, prefix="/v1", tags=["system"])
app.include_router(invoices_router.router, prefix="/v1", tags=["invoices"])
app.include_router(transactions_router.router, prefix="/v1", tags=["transactions"])
app.include_router(vendors_router.router, prefix="/v1", tags=["vendors"])
app.include_router(workflows_router.router, prefix="/v1", tags=["workflows"])
app.include_router(policies_router.router, prefix="/v1", tags=["policies"])
app.include_router(audit_router.router, prefix="/v1", tags=["audit"])

from app.retrieval.qdrant_client import ensure_collection  # noqa: E402
from app.core.error_handling import GlobalExceptionHandler, GemmaFinOSError

@app.exception_handler(GemmaFinOSError)
async def gemmaFin_exception_handler(request: Request, exc: GemmaFinOSError):
    return await GlobalExceptionHandler.handle_gemmaFin_exception(request, exc)

@app.exception_handler(ValueError)
async def validation_exception_handler(request: Request, exc: ValueError):
    return await GlobalExceptionHandler.handle_validation_exception(request, exc)

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return await GlobalExceptionHandler.handle_generic_exception(request, exc)

@app.on_event("startup")
async def on_startup():
    try:
        ensure_collection()
    except Exception:
        pass
