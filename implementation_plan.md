# Fix GemmaFin OS — UI, Business Logic & Composio Integration

The project has accumulated inconsistencies from heavy AI-driven iterations. This plan addresses three critical areas: **broken UI styling**, **non-functional business logic**, and **Composio integration that doesn't actually automate anything**.

## User Review Required

> [!IMPORTANT]
> The Composio SDK API (`composio` + `composio-openai`) has changed significantly. The current code uses a session-based approach (`client.sessions.create()`, `session.authorize()`, `session.execute()`) that doesn't match any known Composio SDK version. We need to rewrite the integration using the actual Composio SDK patterns. **Please confirm your Composio SDK version** — run `pip show composio-core` in your backend venv.

> [!WARNING]
> The compliance page (`/compliance`) uses entirely different colors (blue gradients, zinc backgrounds, dark mode variants) than the rest of the app (brown/cream/gold design system). This will be a significant visual rewrite to bring consistency.

> [!IMPORTANT]
> Several landing page components (`ProblemSection`, `PricingSection`, `TrustSection`) return `null` — just empty stubs. Should I build real content for these, or remove them entirely from the landing page?

## Open Questions

1. **Landing page empty sections**: `ProblemSection`, `PricingSection`, `TrustSection` all return `null`. Remove from `page.tsx`, or implement them?
2. **FlowingMenu on landing page**: There's a random `FlowingMenu` component with `picsum.photos` placeholder images. Remove or replace?
3. **Two footer components**: There are `Footer.tsx`, `new-footer.tsx`, and a hardcoded footer in `page.tsx`. Which should be the canonical one?
4. **Database**: Are you running against NeonDB (PostgreSQL) or local SQLite? Some business logic depends on async Postgres queries that silently fail on SQLite.

---

## Proposed Changes

### 1. UI Consistency — Design System Alignment

The core issue: the compliance page (`/compliance/page.tsx`) uses a completely different color system (blue gradients, zinc, dark mode) vs the project's design system (brown/cream/gold). Buttons, inputs, badges, and backgrounds all need alignment.

---

#### [MODIFY] [compliance/page.tsx](file:///Z:/Hackathons/gemmaFin_os/frontend/app/compliance/page.tsx)

**The biggest offender.** This 654-line page uses:
- `bg-gradient-to-r from-blue-600 to-blue-700` on all action buttons
- `text-blue-500`, `border-blue-200` everywhere
- `bg-zinc-*`, `dark:bg-zinc-*` backgrounds (no dark mode support exists in the app)
- `focus:ring-blue-500/30` on inputs

**Changes:**
- Replace blue buttons → `bg-brown-900 hover:bg-brown-800 text-cream-50` (matches Header/Dashboard)
- Replace zinc backgrounds → `bg-white`, `bg-stone-50`, `bg-cream-100/60`
- Replace blue accents → `text-gold-600`, `border-gold-500/30`
- Remove all `dark:` classes (the app has no dark mode toggle)
- Fix the "Load example cases" button from `text-blue-500` → `text-gold-600`
- Fix chat bubble colors from blue gradient → brown/gold scheme
- Fix agent progress cards from `bg-blue-50` → `bg-gold-500/10`

---

#### [MODIFY] [dashboard/page.tsx](file:///Z:/Hackathons/gemmaFin_os/frontend/app/dashboard/page.tsx)

Minor fixes:
- "New Assessment" button uses `bg-brown-900` (correct) — no changes needed
- Approval approve/reject buttons use `bg-emerald-50` and `bg-red-50` — these are fine (semantically correct)
- Only issue: the Refresh button border color is inconsistent

---

#### [MODIFY] [integrations/page.tsx](file:///Z:/Hackathons/gemmaFin_os/frontend/app/integrations/page.tsx)

- "Connect" button uses `bg-brown-900` — correct, no changes needed

---

#### [MODIFY] [page.tsx (landing)](file:///Z:/Hackathons/gemmaFin_os/frontend/app/page.tsx)

- Remove `ProblemSection`, `PricingSection`, `TrustSection` (all return `null`)
- Remove `FlowingMenu` with placeholder images from random URL
- Remove duplicate footer structure at bottom (keep one canonical footer)
- Fix hardcoded "GemmaFinOS" branding in the bottom footer — should say "GemmaFin OS"
- Remove `font-calendas` reference (class doesn't exist)

---

#### [MODIFY] [globals.css](file:///Z:/Hackathons/gemmaFin_os/frontend/app/globals.css)

- Duplicate `@font-face` declarations for `neu` font (lines 5-8 and 55-70) — consolidate
- The `body` rule references `@apply bg-cream-50 text-brown-900 font-body` which conflicts with the layout's `bg-background text-foreground font-sans` — standardize to use the cream/brown tokens

---

#### [MODIFY] [layout.tsx](file:///Z:/Hackathons/gemmaFin_os/frontend/app/layout.tsx)

- Change `bg-background text-foreground font-sans` → `bg-cream-50 text-brown-900 font-body` to match globals.css and the rest of the app

---

### 2. Backend Business Logic Fixes

The main issue: routes are registered in `main.py` but many have **broken internal logic** — async/sync mismatches, incorrect imports, stub implementations, and missing DB integration.

---

#### [MODIFY] [security.py](file:///Z:/Hackathons/gemmaFin_os/backend/app/core/security.py)

- `get_db_user()` creates new users with role `"lawyer"` (line 141) — should default to `"finance_analyst"` for FinOps context. The `"lawyer"` role is a legacy from the original legal-tech codebase
- The dev user fallback has role `"admin"` which is correct for testing

---

#### [MODIFY] [dashboard.py](file:///Z:/Hackathons/gemmaFin_os/backend/app/api/v1/dashboard.py)

- `ROLE_SECTIONS` is incomplete — missing `admin` and `viewer` roles per requirements
- Missing `invoice_queue`, `transaction_feed`, `str_queue`, `policy_gaps`, `trend_charts`, `risk_heatmap`, `top_critical_rules`, `user_management`, `connector_status`, `system_health` sections
- Dashboard returns empty `pending_approvals` because there's no data seeded — need to also handle the case where the ApprovalRequest model isn't in the DB (SQLite)
- Add `admin` role that includes all sections
- Add `viewer` role with limited sections
- Return HTTP 403 for unknown roles

---

#### [MODIFY] [connectors_api.py](file:///Z:/Hackathons/gemmaFin_os/backend/app/api/v1/connectors_api.py)

- Uses `AsyncSession` type hint from SQLAlchemy async, but the route handlers and `scan_all` use synchronous calls — need to ensure consistency
- Add the missing `POST /v1/connectors/sap/import-and-scan` endpoint (task 4.3)

---

#### [MODIFY] [workflows.py](file:///Z:/Hackathons/gemmaFin_os/backend/app/api/v1/workflows.py)

- `user_id = uuid.UUID(str(user.get("db_id") or user["id"]))` will fail for Clerk IDs (strings like `"user_abc123"`, not UUIDs) — need to handle this gracefully
- The `WorkflowRun` model reference may not have all required columns — verify against `models.py`

---

#### [MODIFY] [invoices.py](file:///Z:/Hackathons/gemmaFin_os/backend/app/api/v1/invoices.py)

- At 40KB this is the largest file — verify the upload pipeline actually works end-to-end:
  - OCR/PDF parsing → Gemma extraction → duplicate detection → risk scoring → approval creation → audit trail
- Verify `GET /v1/invoices` returns correct data for the frontend's `listInvoices()` call

---

#### [MODIFY] [transactions.py](file:///Z:/Hackathons/gemmaFin_os/backend/app/api/v1/transactions.py)

- Verify `POST /v1/transactions/ingest` actually runs the AML scan pipeline
- Check that `TransactionAgent.run()` is called correctly
- Verify `GET /v1/transactions/batches` endpoint exists for the frontend

---

#### [MODIFY] [vendors.py](file:///Z:/Hackathons/gemmaFin_os/backend/app/api/v1/vendors.py)

- Verify `POST /v1/vendors/onboard` creates DB records and runs the onboarding agent
- Check `GET /v1/vendors` works for the frontend list

---

### 3. Composio Integration — Make It Actually Work

The current Composio integration is architecturally sound but uses **incorrect SDK API calls** that will fail at runtime.

---

#### [MODIFY] [composio_client.py](file:///Z:/Hackathons/gemmaFin_os/backend/app/connectors/composio_client.py)

The current code uses:
```python
from composio import Composio
client = Composio(api_key=self.api_key)
session = client.sessions.create(user_id=user_id)
session.execute(tool_slug, arguments)
session.authorize(toolkit, **kwargs)
```

This is not the actual Composio SDK API. The real Composio SDK uses:
```python
from composio import ComposioToolSet
toolset = ComposioToolSet(api_key=api_key)
# For entity-level management:
entity = toolset.get_entity(id=user_id)
connection = entity.initiate_connection(app_name=toolkit)
# For tool execution:
toolset.execute_action(action=Action.GMAIL_SEND_EMAIL, params={...}, entity_id=user_id)
```

**Changes:**
- Rewrite `ComposioConnector` to use `ComposioToolSet` and `Entity` patterns
- Fix `start_connection()` to use `entity.initiate_connection()`
- Fix `execute_tool()` to use `toolset.execute_action()`
- Fix `get_openai_tools()` to use `toolset.get_tools()`
- Fix `test_connection()` to use `toolset.get_connected_accounts()`
- Add proper error handling for when `composio-core` isn't installed

---

#### [MODIFY] [connectors_api.py](file:///Z:/Hackathons/gemmaFin_os/backend/app/api/v1/connectors_api.py)

- Update `composio_connect` to work with the new SDK
- Update `connector_status` to properly test Composio connection
- Add the missing SAP import-and-scan endpoint

---

### 4. Frontend-Backend Connectivity Fixes

---

#### [MODIFY] [compliance-api.ts](file:///Z:/Hackathons/gemmaFin_os/frontend/lib/compliance-api.ts)

- `getAuditTrail()` calls `/v1/audit-trail` but the backend route is `/v1/audit/trail` — fix URL
- `listTransactionBatches()` calls `/v1/transactions/batches` — verify this endpoint exists
- Add proper error state handling in all API calls (currently throws generic errors)

---

#### [MODIFY] Multiple frontend pages

- Add error boundaries around API calls that may 500 when backend isn't running
- Show meaningful "Backend not running" states instead of cryptic error messages
- Fix the invoice upload flow to show proper loading/error/success states

---

## Verification Plan

### Automated Tests
```bash
# Backend: verify the server starts without import errors
cd backend && python -c "from app.main import app; print('OK')"

# Backend: verify all route registration
cd backend && python -c "from app.main import app; print([r.path for r in app.routes])"

# Frontend: verify build succeeds
cd frontend && npx next build
```

### Manual Verification
- Start the backend with `python run.py` and verify `/health` returns `{"ok": true}`
- Verify `/v1/dashboard` returns role-shaped data
- Verify `/v1/connectors/status` returns configured status for Composio
- Open frontend at `localhost:3000` and verify:
  - All buttons use consistent brown/cream/gold colors
  - Landing page has no empty sections
  - Compliance page form inputs match the design system
  - Integrations page shows correct Composio connection status
