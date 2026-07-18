# Implementation Plan: GemmaFin OS Platform

## Overview

This plan builds the GemmaFinOS backend into a
full FinOps operating system. Tasks are sequenced infrastructure-first (DB migrations, new tables,
shared models), then backend pipelines (invoices, transactions, vendors), then agent/extraction
improvements, then role-gated API surfaces, and finally the Next.js frontend pages.

All backend code is Python. All frontend code is TypeScript (Next.js App Router). LLM calls
use `get_llm_client()` / `get_llm_model()` from `app/core/gemma_client.py`.

---

## Tasks

- [x] 1. Database — migrate role constraint and create FinOps tables
  - [x] 1.1 Write Alembic migration `add_finops_user_roles`
    - In `app/db/migrations/versions/`, create a new revision file named
      `add_finops_user_roles.py`
    - `upgrade()`: single atomic ALTER TABLE — `DROP CONSTRAINT users_role_chk`,
      then `ADD CONSTRAINT users_role_chk CHECK (role IN ('lawyer','admin','paralegal',
      'client','finance_analyst','compliance_officer','auditor','cfo','viewer'))`
    - `downgrade()`: restore the original 4-role constraint
    - Before the ALTER, `SELECT COUNT(*) FROM users WHERE role IN ('lawyer','paralegal','client')`
      and emit a `log.warning` for each legacy role found
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 1.2 Update `app/db/models.py` — expand `User.role` check constraint
    - Change the `CheckConstraint` in `User.__table_args__` to accept all 9 roles
    - Ensure the constraint string matches exactly what the migration creates
    - _Requirements: 7.1, 7.3_

  - [x] 1.3 Add ORM models for FinOps workflow tables
    - Add `Invoice`, `TransactionBatch`, `VendorOnboardingCase`, `PolicyDocument`,
      `WorkflowRun`, and `AuditTrailEntry` SQLAlchemy models to `app/db/models.py`
    - Use the SQL DDL from Phase 4 of the design as the authoritative schema
    - Each model needs the correct `ForeignKey`, `CheckConstraint`, and `Index`
      declarations matching the design
    - _Requirements: 1.2, 1.3, 2.11, 4.5, 4.6_


- [x] 2. Backend — SAP mapper and shared transaction types
  - [x] 2.1 Create `app/connectors/sap_mapper.py`
    - Implement `map_sap_invoice_to_transaction(sap_invoice: dict) -> TransactionRecord`
    - Map all 8 fields per design: `SupplierInvoice→external_id`,
      `SupplierInvoiceIDByInvcgParty→invoice_number`, `Supplier→supplier`,
      `DocumentDate→transaction_date` (YYYY-MM-DD), `InvoiceGrossAmount→amount`
      (positive float), `DocumentCurrency→currency`, `PurchaseOrder→po_number`,
      `DocumentHeaderText→description`
    - Defaults for missing optional fields: `None` for optional strings,
      `""` for description, `datetime.now()` for missing date
    - `TransactionRecord` should be a Pydantic model (import from or define next to
      `app/api/v1/transactions.py`)
    - _Requirements: 8.1–8.9_

  - [x] 2.2 Write unit tests for `map_sap_invoice_to_transaction`
    - Test all 8 field mappings with a fully-populated input dict
    - Test each optional field individually absent (one at a time) — verify default value
    - Test `InvoiceGrossAmount` as string, int, and float (SAP OData returns strings)
    - _Requirements: 8.1–8.9_


- [ ] 3. Backend — invoice upload and processing pipeline
  - [x] 3.1 Create `app/api/v1/invoices.py` — core upload endpoint
    - Define `InvoiceExtraction` and `InvoiceUploadResponse` Pydantic models
    - Implement `POST /v1/invoices/upload` (multipart `UploadFile`):
      1. Reject non-pdf/png/jpg/jpeg with HTTP 422
      2. Route to `app/ingestion/ocr.py` for images, `app/ingestion/parse_pdf.py` for PDFs
      3. Call `redact_user_input()` before any LLM call
      4. If Gemma available: call `get_llm_client()` with `GEMMA_INVOICE_PROMPT`; parse JSON
      5. If Gemma unavailable: call regex fallback; set `extraction_confidence=0.0`
      6. Call `detect_duplicate_payments()` against 30-day window for same supplier
      7. If `po_number` provided: call `detect_invoice_po_mismatch()`
      8. Set `severity=critical` on any `exact_invoice_match` duplicate finding
      9. If critical finding or `risk_tier=critical`: create `ApprovalRequest`, set
         `requires_approval=True`
      10. Append `AuditTrailEntry` for every status transition
    - Write to `Invoice` table; return `InvoiceUploadResponse`
    - _Requirements: 2.1–2.11_

  - [x] 3.2 Add `POST /v1/invoices/batch` and `GET /v1/invoices` to `invoices.py`
    - `batch`: accept `List[UploadFile]`; run upload pipeline for each concurrently
      with `asyncio.gather`; return `List[InvoiceUploadResponse]`
    - `GET /v1/invoices`: return invoices filtered by authenticated user; support optional
      `status` and `risk_tier` query params; default `limit=50`
    - _Requirements: 2.12, 2.13_

  - [ ] 3.3 Register invoice router in `app/main.py`
    - `from app.api.v1 import invoices as invoices_router`
    - `app.include_router(invoices_router.router, prefix="/v1", tags=["invoices"])`
    - _Requirements: 2.1_

  - [ ] 3.4 Write integration test for invoice upload audit trail
    - Upload a sample PDF bytes fixture to `POST /v1/invoices/upload`
    - Assert `status_code == 200` and `invoice_id` is present
    - Query `audit_trail_entries` for the returned `invoice_id`
    - Assert all three actions appear: `document_uploaded`, `extraction_complete`,
      `risk_scored`
    - _Requirements: 2.11_


- [ ] 4. Backend — transaction ingestion and AML/CFT pipeline
  - [x] 4.1 Create `app/api/v1/transactions.py` — core ingest endpoint
    - Define `TransactionRecord`, `TransactionIngestRequest`, and
      `TransactionIngestResponse` Pydantic models
    - Implement `POST /v1/transactions/ingest`:
      1. Validate `source` is one of `manual|sap|excel|outlook|csv`; 422 otherwise
      2. Apply `redact_user_input()` to all `description` and `supplier` fields
      3. Call `DocumentAnomalies.scan_all()`
      4. Call `TransactionAgent.run()` with Gemma; capture `AgentOutput`
      5. Create `ApprovalRequest` when `risk_tier=critical`; set `requires_approval=True`
    - _Requirements: 3.1–3.5_

  - [x] 4.2 Add SAP and Excel ingestion sub-routes to `transactions.py`
    - `POST /v1/transactions/ingest/from-sap`: call
      `SAPODataConnector.fetch_supplier_invoices()`, map each via `sap_mapper`, then
      reuse core ingest logic; return HTTP 503 with error message if
      `connector.is_configured()` is `False`
    - `POST /v1/transactions/ingest/from-excel`: call Microsoft Graph connector to
      retrieve worksheet, map rows to `TransactionRecord`, then reuse core ingest logic
    - _Requirements: 3.6, 3.7, 3.8_

  - [ ] 4.3 Add `POST /v1/connectors/sap/import-and-scan` to `app/api/v1/connectors_api.py`
    - Fetch invoices via `SAPODataConnector.fetch_supplier_invoices(top, filter_expr)`
    - Map each to `TransactionRecord` via `sap_mapper.map_sap_invoice_to_transaction`
    - Pass batch to the transaction ingest scan pipeline
    - Return `TransactionIngestResponse`
    - _Requirements: 8.10_

  - [ ] 4.4 Register transaction router in `app/main.py`
    - Import and include `transactions_router` with prefix `/v1` and tag `transactions`
    - _Requirements: 3.1_


- [ ] 5. Backend — vendor onboarding KYC/KYB workflow
  - [x] 5.1 Create `app/api/v1/vendors.py` — onboarding endpoint
    - Define `VendorOnboardRequest` and `VendorOnboardResponse` Pydantic models
    - Implement `POST /v1/vendors/onboard`:
      1. Accept `vendor_name`, `vendor_gstin`, `vendor_pan`, `sector`,
         `documents: List[UploadFile]`
      2. Create `VendorOnboardingCase` record in DB
      3. Call `OnboardingAgent.run()` to compute `missing_documents`
      4. If `pep_flags` non-empty: set `risk_tier=critical`, create `ApprovalRequest`
         unconditionally
      5. Set `kyc_status`: `in_review` (missing docs), `escalated` (PEP/UBO),
         `approved` (all pass)
      6. Append `AuditTrailEntry` on every status transition
      7. Persist all fields including `missing_documents`, `pep_flags`, `ubo_issues`,
         `risk_tier`, `kyc_status` to `vendor_onboarding_cases` table
    - _Requirements: 4.1–4.6_

  - [x] 5.2 Register vendor router in `app/main.py`
    - Import and include `vendors_router` with prefix `/v1` and tag `vendors`
    - _Requirements: 4.1_

  - [ ] 5.3 Write integration test for vendor PEP escalation
    - POST to `/v1/vendors/onboard` with a vendor payload containing a PEP flag
    - Assert `kyc_status == "escalated"`, `risk_tier == "critical"`,
      `requires_approval == True`, and `approval_id` is non-null
    - Assert an `AuditTrailEntry` exists for the PEP escalation transition
    - _Requirements: 4.3, 4.5_


- [ ] 6. Backend — Gemma-first document extraction (`app/api/v1/extract.py`)
  - [x] 6.1 Rewrite `POST /v1/compliance/extract` to accept file uploads
    - Add `file: Optional[UploadFile] = File(None)` and `text: Optional[str] = Form(None)`
      parameters; remove the old `ExtractRequest` body model
    - Return HTTP 422 if neither `file` nor `text` is provided
    - Route file to correct parser by extension: OCR for `.png/.jpg/.jpeg`, PDF parser
      for `.pdf`, DOCX parser for `.docx`
    - Call `redact_user_input()` on all extracted text before constructing Gemma prompt
    - _Requirements: 6.1, 6.2, 6.3, 6.7_

  - [ ] 6.2 Implement Gemma extraction path with per-field source and confidence
    - When `get_llm_client_or_none()` returns a client: construct the document-type-specific
      prompt (use `document_type` param: `general|bank_statement|gst_filing|onboarding|invoice`)
    - Parse Gemma's JSON response; populate `ExtractResponse.extraction_fields` with
      `source="gemma"` and `confidence` from the model
    - When Gemma unavailable: fall back to existing regex extraction; set
      `source="default"` and `confidence=0.0` for any field regex could not extract
    - Ensure `source` is strictly one of `"gemma"`, `"regex"`, or `"default"` and
      `confidence` is in `[0.0, 1.0]` for every field
    - _Requirements: 6.4, 6.5, 6.6, 6.8_

  - [ ] 6.3 Write property test for extraction source/confidence invariants
    - **Property P8 (partial): Extraction confidence bounded**
    - **Validates: Requirements 6.5**
    - Use Hypothesis to generate random text inputs and assert:
      - Every `extraction_fields` entry has `source in ("gemma","regex","default")`
      - Every `confidence` value satisfies `0.0 <= confidence <= 1.0`


- [ ] 7. Backend — FinTriageAgent extended to 9 tools
  - [x] 7.1 Fix `_tool_compare` to load entities from DB when session context is sparse
    - Add `async def _load_recent_entities(self, user_id: str) -> Dict[str, Dict]` method
      that queries `compliance_assessments` for the most recent 3 assessments for
      `user_id`, keyed by `entity.business_name`
    - In `_tool_compare`: when `len(entities) < 2`, call `_load_recent_entities`; if
      still fewer than 2 entities, return the existing "need at least 2" reply
    - _Requirements: 5.4_

  - [x] 7.2 Implement multi-intent execution ordering
    - Refactor `FinTriageAgent.handle()` to detect all matching regex intents from
      `_INTENT_PATTERNS` in a single pass (do not stop at first match)
    - Sort detected intents by `_TOOL_EXECUTION_ORDER`:
      `reassess → penalty_sim → threshold_sim → compare → explain_risk →
      rule_info → generate_report → external_action`
    - After each tool runs, if intent was `reassess`, update `accumulated_context`
      with `last_result` and `last_features` from the simulated output
    - Combine multiple tool replies via Gemma (or plain join if Gemma unavailable)
    - _Requirements: 5.5, 5.6_

  - [ ] 7.3 Add Gemma tool-calling fallback for `external_action`
    - When `client.chat.completions.create()` with `tools=` raises (e.g. model does not
      support function-calling), catch the exception, log it, and fall back to
      text-based action type classification
    - Stage a bare `ApprovalRequest` with the raw message as `reason` and return
      `status: pending_approval` without invoking Composio directly
    - _Requirements: 5.9_

  - [ ] 7.4 Audit all tool handler methods for async and exception safety
    - Verify every `_tool_*` method is declared `async def`
    - Ensure the `try/except` in `handle()` catches all exceptions from tool handlers,
      logs via `log.error`, and returns a user-facing error dict
    - _Requirements: 5.10, 5.11_

  - [ ] 7.5 Write property test for ML pipeline determinism
    - **Property: Same inputs always produce the same risk tier (determinism)**
    - **Validates: Requirements 5.4 (pipeline consistency)**
    - Use Hypothesis `@given` with random valid feature dicts
    - Call `run_full_assessment(features)` twice with the same input
    - Assert both calls return identical `risk_tier`, `confidence`, and
      `total_penalty_exposure_inr`


- [ ] 8. Checkpoint — backend pipelines wired and testable
  - Ensure all tests pass, ask the user if questions arise.
  - Smoke-test: `POST /v1/invoices/upload` with a PDF, `POST /v1/transactions/ingest`
    with a manual batch, `POST /v1/vendors/onboard` with a minimal vendor payload.
  - Verify `AuditTrailEntry` rows appear in the DB for each workflow.

- [ ] 9. Backend — unified workflow router
  - [ ] 9.1 Create `app/api/v1/workflows.py`
    - Define `WorkflowType` (str Enum), `WorkflowRequest`, `WorkflowContext`,
      `WorkflowStatus`, `WorkflowResponse`, and `WorkflowListResponse` Pydantic models
    - Implement `POST /v1/workflows`: validate `workflow_type`, create a `WorkflowRun`
      record with `status=pending`, dispatch to the correct pipeline handler based on
      type, update status to `running`→`completed`/`awaiting_approval`/`failed`
    - When `run_llm_agents=false`: skip all `get_llm_client()` calls; run ML pipeline
      stages only
    - Return HTTP 422 for invalid `workflow_type` values
    - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7_

  - [ ] 9.2 Add `GET /v1/workflows/{workflow_id}` and `GET /v1/workflows` to `workflows.py`
    - `GET /{id}`: query `WorkflowRun` by PK; return 404 if not found
    - `GET /`: return paginated list filtered by `user.id`; support optional
      `workflow_type` filter; default `limit=50`
    - _Requirements: 1.4, 1.5_

  - [ ] 9.3 Register workflow router in `app/main.py`
    - Import and include `workflows_router` with prefix `/v1` and tag `workflows`
    - _Requirements: 1.1_


- [ ] 10. Backend — role-based dashboards (`app/api/v1/dashboard.py`)
  - [ ] 10.1 Expand `ROLE_SECTIONS` and role-specific data assemblers
    - Update `ROLE_SECTIONS` dict to match requirements exactly:
      - `finance_analyst`: `["recent_assessments","invoice_queue","transaction_feed",
        "penalty_exposure_summary"]`
      - `compliance_officer`: `["critical_findings","pending_approvals","str_queue",
        "policy_gaps"]`
      - `auditor`: `["audit_log","report_archive","pending_reviews","critical_findings"]`
      - `cfo`: `["penalty_exposure_summary","trend_charts","risk_heatmap",
        "top_critical_rules"]`
      - `admin`: all the above plus `["user_management","connector_status","system_health"]`
    - Return HTTP 403 for any role not in `ROLE_SECTIONS`
    - _Requirements: 9.1–9.6, 9.10_

  - [ ] 10.2 Implement pending approvals scoping and penalty exposure shape
    - `pending_approvals` for `compliance_officer|auditor|cfo|admin`: query all `pending`
      `ApprovalRequest` rows in the org (`scope="org"`)
    - `pending_approvals` for `finance_analyst|viewer`: query only rows where
      `requested_by_user_id = user.id` (`scope="user"`)
    - `penalty_exposure_summary` object must contain `total`, `count`, `critical_count`,
      `trend_7d`, and `by_framework` fields
    - _Requirements: 9.7, 9.8, 9.9_

  - [ ] 10.3 Write unit tests for dashboard role scoping
    - For each of the 5 defined roles, call `GET /v1/dashboard` with a mock user of
      that role and assert only the expected section keys are present in the response
    - Assert `403` is returned for a user with role `"unknown_role"`
    - Assert `pending_approvals` for a `finance_analyst` contains only that user's
      own approvals (not others' in the org)
    - _Requirements: 9.1–9.10_


- [ ] 11. Property-based tests for cross-cutting correctness properties
  - [ ] 11.1 Write property test for PII redaction completeness
    - **Property P4: PII redaction before LLM**
    - **Validates: Requirements 2.4, 3.2, 6.7**
    - Use Hypothesis to generate strings containing Aadhaar-format numbers
      (`\d{4}\s\d{4}\s\d{4}`), PAN-format strings (`[A-Z]{5}\d{4}[A-Z]`), and
      email addresses
    - Call `redact_user_input(generated_string, user_id="test")` and assert the
      returned `redacted_text` contains no match for any of those patterns
    - Assert `redaction_count > 0` when the input contained PII patterns

  - [ ] 11.2 Write property test for approval gate coverage
    - **Property P3: Approval gate never skipped for write actions**
    - **Validates: Requirements 2.10, 3.5, 4.3, 5.7**
    - Use Hypothesis to generate random `InvoiceExtraction` objects where
      `risk_tier` is forced to `"critical"`
    - Run `process_invoice` with a mocked DB and assert that:
      - `ApprovalRequest` is created with `status="pending"`
      - `requires_approval=True` in the response
      - No Composio `execute_tool()` is called directly (assert mock not called)

  - [ ] 11.3 Write property test for audit log append-only immutability
    - **Property P6: Audit trail completeness**
    - **Validates: Requirements 2.11, 4.5**
    - For each invoice status transition sequence (uploaded→extracted, extracted→
      risk_scored, risk_scored→approval_requested): assert that an `AuditTrailEntry`
      row exists for each transition with the correct `action` and non-null `actor`
    - Assert no DELETE or UPDATE path exists for `audit_trail_entries` in the API
      route handlers (grep test: no `db.delete` or `db.execute(update(...))` targeting
      that table)

  - [ ] 11.4 Write property test for risk tier validity
    - **Property P2: Auto-escalation irreversibility**
    - **Validates: Requirements 2.9, 5.4**
    - Use Hypothesis `@given` with random feature dicts
    - For the PEP flag variant: force `detected_flags=["director_pep_match"]`
    - Assert `run_full_assessment(features, detected_flags=["director_pep_match"])
      ["risk_tier"] == "critical"` for all feature combinations

  - [ ] 11.5 Write property test for duplicate detection symmetry
    - **Property P5: Duplicate detection symmetry**
    - **Validates: Requirements 2.7, 2.9**
    - Use Hypothesis to generate pairs of `Transaction` objects
    - Assert `len(detect_duplicate_payments([t1, t2])) ==
      len(detect_duplicate_payments([t2, t1]))` for all generated pairs
    - Assert a single transaction never duplicates itself


- [ ] 12. Checkpoint — all backend routes and property tests
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest backend/tests/ -x` and confirm zero failures.
  - Run `alembic upgrade head` against the test DB and confirm the role constraint
    migration applies cleanly.

- [ ] 13. Frontend — shared design system tokens and base components
  - [ ] 13.1 Add shared risk-theme tokens and base compliance components
    - Create `frontend/components/compliance/RiskTheme.ts` exporting `RISK_THEME`
      (critical/high/medium/low with bg, text, badge Tailwind classes from the
      design's `cream/brown/gold/olive/error` palette)
    - Create `frontend/components/compliance/SeverityBadge.tsx` — accepts
      `severity: "critical"|"high"|"medium"|"low"` and renders a styled pill
    - Create `frontend/components/compliance/WorkflowStatusCard.tsx` — renders
      a workflow status timeline with audit trail entries and colour-coded statuses
    - All components use `font-body` / `font-display` tokens from `tailwind.config.ts`
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ] 13.2 Create `frontend/lib/finops-api.ts` — typed API client for all FinOps endpoints
    - Export typed fetch helpers: `uploadInvoice`, `listInvoices`, `ingestTransactions`,
      `onboardVendor`, `extractDocument`, `getDashboard`, `runWorkflow`, `getWorkflow`,
      `listWorkflows`
    - All functions use the project's existing `apiPost`/`apiGet` patterns and return
      typed response interfaces
    - _Requirements: 10.1–10.10_


- [ ] 14. Frontend — invoice workflow page
  - [ ] 14.1 Create `frontend/app/compliance/invoices/page.tsx`
    - Render invoice management queue: fetch from `GET /v1/invoices` on mount
    - File upload zone (react-dropzone) that calls `POST /v1/invoices/upload`;
      show upload progress and transition to extracted → risk_scored state
    - For each invoice card: display status badge, risk tier badge (`SeverityBadge`),
      and any duplicate/mismatch finding chips
    - Show "Pending Approval" banner with Approve/Reject actions when
      `requires_approval=true` and user has an approver role
    - _Requirements: 10.1_

  - [ ] 14.2 Create `frontend/components/compliance/InvoiceCard.tsx`
    - Props: `invoice: InvoiceRecord`, `onApprove`, `onReject`, `onViewDetails`
    - Render: vendor name, invoice number, amount, date, status and risk tier badges,
      duplicate/mismatch finding badges
    - Conditionally show approval action buttons based on `requires_approval` and user
      role
    - _Requirements: 10.1_


- [ ] 15. Frontend — transaction monitoring page
  - [ ] 15.1 Create `frontend/app/compliance/transactions/page.tsx`
    - Paginated transaction feed: severity filter (critical/high/medium/low) and
      date range filter controls
    - Flagged transactions highlighted with `SeverityBadge` for each finding type
      (duplicate, mismatch, unusual)
    - Calls `POST /v1/transactions/ingest` on form submit for manual entry
    - _Requirements: 10.2_

  - [ ] 15.2 Create `frontend/components/compliance/TransactionFeed.tsx`
    - Props: `transactions: TransactionRecord[]`, `findings: Finding[]`,
      `onInvestigate?: (id: string) => void`
    - Groups findings per transaction and renders inline; supports client-side
      filtering by severity
    - _Requirements: 10.2_

- [ ] 16. Frontend — vendor onboarding page
  - [ ] 16.1 Create `frontend/app/compliance/vendors/page.tsx`
    - Render list of `VendorOnboardingCase` records from the API
    - Each case shows KYC status badge (`in_review|approved|escalated`) and a
      document gap indicator listing `missing_documents`
    - Onboarding form that submits to `POST /v1/vendors/onboard`
    - _Requirements: 10.3_

- [ ] 17. Frontend — policy document library page
  - [ ] 17.1 Create `frontend/app/compliance/policies/page.tsx`
    - Render list of policy documents from `GET /v1/policies` (or equivalent endpoint)
    - Upload button with react-dropzone; show version and effective date per policy
    - Compliance gap indicators sourced from `compliance_gaps` field on each policy
    - _Requirements: 10.4_


- [ ] 18. Frontend — 5-step entity assessment form (`/assess`)
  - [ ] 18.1 Create `frontend/app/assess/page.tsx` — stepper shell
    - Implement a single-page stepper with 5 steps matching design:
      Step 1 Business Identity, Step 2 Transaction Profile, Step 3 Document Upload,
      Step 4 Privacy Review, Step 5 Flags Review
    - Navigation: Next/Back buttons; Step 4 is only accessible after Step 3 document
      upload completes
    - Persist step state in React state (no page reload between steps)
    - _Requirements: 10.5_

  - [ ] 18.2 Implement Step 3 document upload and Step 4 confidence indicators
    - Step 3: each file upload immediately calls `POST /v1/compliance/extract`;
      display a spinner while extraction is in progress
    - Step 4: render all 9 extracted fields as editable inputs; show confidence
      indicator next to each field: green chip for `source="gemma"`, amber for
      `source="regex"`, grey for `source="default"`
    - User must click "Confirm values" before advancing to Step 5
    - _Requirements: 10.6_

  - [ ] 18.3 Implement Step 5 flags review and "Run Full Assessment"
    - Render pre-populated flag toggles from document analysis
    - "Run Full Assessment" button calls `POST /v1/compliance/assess` with confirmed
      feature values and toggled flags
    - Show loading state; on success redirect to the assessment result page
    - _Requirements: 10.7_


- [ ] 19. Frontend — audit log viewer and integrations pages
  - [ ] 19.1 Create `frontend/app/compliance/audit/page.tsx`
    - Render `audit_trail_entries` in a table: columns — action, actor, timestamp,
      workflow reference (linked to the relevant workflow or invoice detail page)
    - Fetch from the audit trail API endpoint; support pagination
    - _Requirements: 10.8_

  - [ ] 19.2 Create (or rewrite) `frontend/app/integrations/page.tsx`
    - Connector status cards for Composio, SAP OData, and Microsoft Graph
    - Each card shows connected/disconnected status and a "Connect" button
    - "Connect" button for Composio toolkits: calls
      `POST /v1/connectors/composio/connect/{toolkit}` and opens `redirect_url`
      in a `window.open` popup
    - _Requirements: 10.9, 10.10_

- [ ] 20. Checkpoint — frontend pages complete and connected to live API
  - Ensure all tests pass, ask the user if questions arise.
  - Verify each new page renders without console errors when the backend is running.
  - Confirm file upload on `/compliance/invoices` shows risk tier badge after
    processing, confidence indicators appear on `/assess` Step 4, and the Composio
    OAuth popup opens from `/integrations`.


- [ ] 21. Integration and wiring — end-to-end workflow tests
  - [ ] 21.1 Write end-to-end integration test for the invoice workflow
    - Upload a multi-page PDF invoice to `POST /v1/invoices/upload`
    - Assert extraction fields are populated (`vendor_name`, `amount_total` non-null)
    - Upload the same invoice a second time (same supplier, same invoice number)
    - Assert the second upload response contains a duplicate finding with
      `severity="critical"` and `requires_approval=True`
    - Approve via `POST /v1/approvals/{id}/review`; assert invoice status transitions
      to `approved` and a final `AuditTrailEntry` is appended
    - _Requirements: 2.7, 2.9, 2.10, 2.11_

  - [ ] 21.2 Write end-to-end integration test for the transaction AML workflow
    - Ingest a batch of 5 transactions via `POST /v1/transactions/ingest` with
      `source="manual"`, including two transactions with the same `invoice_number`
    - Assert `duplicate_payments` list is non-empty in the response
    - Assert `TransactionAgent` `AgentOutput` fields (`reasoning`, `confidence`) are
      present in the response
    - Ingest a batch with a known structuring pattern (many small transactions just
      below the CTR threshold); assert `risk_tier="critical"` and
      `requires_approval=True`
    - _Requirements: 3.3, 3.4, 3.5_

  - [ ] 21.3 Write end-to-end integration test for the SAP import-and-scan flow
    - Mock `SAPODataConnector.fetch_supplier_invoices()` to return 3 SAP invoice dicts
    - Call `POST /v1/connectors/sap/import-and-scan`
    - Assert all 3 records appear as `TransactionRecord` objects in the pipeline
    - Assert `TransactionIngestResponse` fields are fully populated
    - Call `POST /v1/transactions/ingest/from-sap` when `is_configured()=False`
      and assert HTTP 503
    - _Requirements: 3.6, 3.8, 8.10_


- [ ] 22. Final checkpoint — full system integration
  - Ensure all tests pass, ask the user if questions arise.
  - Run `pytest backend/tests/ -v` — all unit, property, and integration tests pass.
  - Run `alembic upgrade head` on a clean test DB — migration applies without errors.
  - Confirm `GET /v1/dashboard` returns role-correct sections for each of the 5 roles.
  - Confirm `POST /v1/workflows` with `run_llm_agents=false` skips Gemma calls and
    returns a completed `WorkflowResponse` with ML-only results.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Backend implementation language: Python (FastAPI, SQLAlchemy, Pydantic, Hypothesis)
- Frontend implementation language: TypeScript (Next.js App Router)
- All LLM calls must go through `get_llm_client()` / `get_llm_model()` from
  `app/core/gemma_client.py`; never call any LLM provider SDK directly
- All user-facing text must pass through `redact_user_input()` before reaching Gemma
- Every new agent `run()` method must be `async` and return `AgentOutput` TypedDict
- Checkpoints exist to validate incremental correctness — do not skip them
- Property tests require `hypothesis` to be installed:
  `pip install hypothesis` / add to `requirements.txt`
- Frontend dropzone requires `react-dropzone`: `npm install react-dropzone`
- CFO dashboard trend charts require `recharts`: `npm install recharts`
- Transaction monitoring data grid requires `@tanstack/react-table`:
  `npm install @tanstack/react-table`

---


## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": 0,
      "tasks": ["1.1", "1.2"]
    },
    {
      "id": 1,
      "tasks": ["1.3", "2.1"]
    },
    {
      "id": 2,
      "tasks": ["2.2", "3.1", "4.1", "5.1", "6.1", "7.1"]
    },
    {
      "id": 3,
      "tasks": ["3.2", "4.2", "5.2", "6.2", "7.2", "7.3", "7.4"]
    },
    {
      "id": 4,
      "tasks": ["3.3", "3.4", "4.3", "4.4", "5.3", "6.3", "7.5"]
    },
    {
      "id": 5,
      "tasks": ["9.1", "10.1", "11.1", "11.2", "11.3", "11.4", "11.5"]
    },
    {
      "id": 6,
      "tasks": ["9.2", "10.2", "10.3"]
    },
    {
      "id": 7,
      "tasks": ["9.3", "13.1", "13.2"]
    },
    {
      "id": 8,
      "tasks": ["14.1", "14.2", "15.1", "15.2", "16.1", "17.1"]
    },
    {
      "id": 9,
      "tasks": ["18.1", "19.1", "19.2"]
    },
    {
      "id": 10,
      "tasks": ["18.2", "21.1", "21.2", "21.3"]
    },
    {
      "id": 11,
      "tasks": ["18.3"]
    }
  ]
}
```
