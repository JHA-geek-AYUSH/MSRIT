# Requirements Document

## Introduction

GemmaFin OS Platform is a production-grade FinOps and financial compliance platform built as a greenfield platform. It provides a full operating system for financial compliance, with audit-first workflows, real agentic behavior, deterministic ML pipelines, role-specific dashboards, and reliable MCP/Composio integrations. The platform operates under Indian regulatory context: PMLA 2002, FEMA 1999, RBI KYC Master Direction 2016, and SEBI PIT Regulations.

---

## Glossary

- **Workflow_Router**: The unified `POST /v1/workflows` endpoint that replaces the dual `/triage` and `/assess` endpoints and routes to the correct pipeline based on workflow type.
- **Invoice_Processor**: The backend pipeline in `app/api/v1/invoices.py` that handles file upload, OCR, Gemma extraction, duplicate/mismatch detection, and approval gating for invoices.
- **Transaction_Ingestor**: The backend pipeline in `app/api/v1/transactions.py` that accepts transaction batches from manual, SAP, Excel, Outlook, and CSV sources and runs AML/CFT analysis.
- **Vendor_Onboarding_Workflow**: The backend pipeline that processes vendor KYC/KYB cases, identifies missing documents, flags PEP/sanctions matches, and routes through approval gating.
- **FinTriageAgent**: The 9-tool conversational compliance agent in `app/agents/fintriage_agent.py` that handles reassess, penalty_sim, threshold_sim, compare, explain_risk, rule_info, generate_report, external_action, and platform_help.
- **Gemma_Extractor**: The document extraction service in `app/api/v1/extract.py` that uses Gemma as the primary extractor for financial features from PDF, DOCX, and image files.
- **ML_Pipeline**: The 4-stage deterministic pipeline in `app/ml/pipeline.py` composed of Stage 0 (AnomalyScorer), Stage 1 (XGBoost), Stage 2 (ComplianceGapScorer), and Stage 3 (CosineSimilarityRanker).
- **Approval_Gate**: The `execute_composio_tool_gated()` function and `ApprovalRequest` table that stage all write actions as pending approvals before external execution.
- **Audit_Logger**: The append-only `audit_trail_entries` table and associated service that records every state transition in a workflow run.
- **SAP_Mapper**: The `app/connectors/sap_mapper.py` module that maps SAP OData `A_SupplierInvoice` fields to the platform's `Transaction` dataclass.
- **PII_Redactor**: The `redact_user_input()` function in `app/core/pii_redaction.py` that removes Aadhaar numbers, PAN, phone numbers, email addresses, bank account numbers, and GSTIN before any LLM call.
- **Dashboard_API**: The `GET /v1/dashboard` endpoint in `app/api/v1/dashboard.py` that assembles role-filtered section data for the frontend.
- **Role_Constraint**: The PostgreSQL `CHECK` constraint on `users.role` that defines the valid set of user roles.
- **WorkflowRun**: A record in the `workflow_runs` table that tracks the lifecycle of a single workflow execution from `pending` through `completed` or `awaiting_approval`.
- **AuditEntry**: A record in the `audit_trail_entries` table that records a single state transition, actor, and timestamp for a workflow run.
- **ApprovalRequest**: A record in the `approval_requests` table that stages a write action pending a decision from an authorized approver.
- **ComplianceFinding**: A structured result from the ML_Pipeline or DocumentAnomalies scanner that identifies a specific compliance gap, rule breach, or anomaly with a severity level and penalty exposure.
- **InvoiceExtraction**: The structured output of Gemma_Extractor containing vendor_name, vendor_gstin, invoice_number, invoice_date, amount_net, amount_gst, amount_total, po_number, line_items, and extraction_confidence.
- **TransactionRecord**: The canonical in-platform representation of a financial transaction with fields: external_id, supplier, amount, transaction_date, invoice_number, po_number, description, currency, and account_code.
- **AgentOutput**: The TypedDict from `app/agents/base.py` with keys: reasoning (str), sources (List[Dict]), confidence (float), which all backend agents must return from their `run()` methods.

---

## Requirements

### Requirement 1: Unified Workflow Router

**User Story:** As a developer integrating with the platform, I want a single workflow endpoint that routes to the correct pipeline based on document type, so that I do not need to know which of the two legacy endpoints (`/triage` vs `/assess`) to call for a given use case.

#### Acceptance Criteria

1. THE Workflow_Router SHALL accept `POST /v1/workflows` requests with a `WorkflowType` field set to one of: `invoice`, `transaction_batch`, `vendor_onboarding`, `policy_review`, `entity_assessment`, or `full_triage`.
2. WHEN a `POST /v1/workflows` request is received, THE Workflow_Router SHALL return a `WorkflowResponse` containing a non-null `workflow_id`, the matching `workflow_type`, and a `status` of `pending` or `running`.
3. THE Workflow_Router SHALL return the `WorkflowResponse.status` field as one of: `pending`, `running`, `completed`, `failed`, or `awaiting_approval` in every response.
4. WHEN a `GET /v1/workflows/{workflow_id}` request is received, THE Workflow_Router SHALL return the current `WorkflowResponse` for that workflow or a 404 error if the ID is not found.
5. WHEN a `GET /v1/workflows` request is received, THE Workflow_Router SHALL return a paginated list of workflow runs filtered by the authenticated user's identity, with optional filtering by `workflow_type` and a default `limit` of 50.
6. WHEN `run_llm_agents` is `false` in the `WorkflowRequest`, THE Workflow_Router SHALL skip all Gemma LLM agent calls and run only deterministic ML pipeline stages.
7. IF a `WorkflowRequest` is received with an invalid `workflow_type`, THEN THE Workflow_Router SHALL return HTTP 422 with a descriptive validation error.

---

### Requirement 2: Invoice Upload and Processing Pipeline

**User Story:** As a finance analyst, I want to upload invoice PDFs or images and have the platform automatically extract fields, detect duplicate payments and PO mismatches, and route critical findings for approval, so that I can process invoices without manual data entry.

#### Acceptance Criteria

1. WHEN an invoice file is uploaded to `POST /v1/invoices/upload`, THE Invoice_Processor SHALL accept files with extensions `.pdf`, `.png`, `.jpg`, and `.jpeg` and reject all other file types with HTTP 422.
2. WHEN a `.png`, `.jpg`, or `.jpeg` file is uploaded, THE Invoice_Processor SHALL run OCR via `app/ingestion/ocr.py` to extract text before passing it to the Gemma_Extractor.
3. WHEN a `.pdf` file is uploaded, THE Invoice_Processor SHALL run PDF text extraction via `app/ingestion/parse_pdf.py` before passing the text to the Gemma_Extractor.
4. WHEN invoice text is available, THE Invoice_Processor SHALL call PII_Redactor on the text before passing it to any LLM call.
5. WHEN Gemma is available, THE Invoice_Processor SHALL call Gemma_Extractor to produce an `InvoiceExtraction` with all fields populated and `extraction_confidence` in `[0.0, 1.0]`.
6. IF Gemma is unavailable, THEN THE Invoice_Processor SHALL fall back to regex-based extraction and set `extraction_confidence` to `0.0` for all defaulted fields.
7. WHEN extraction is complete, THE Invoice_Processor SHALL run `detect_duplicate_payments()` against transactions from the same supplier in the prior 30 days.
8. WHEN a `po_number` is provided, THE Invoice_Processor SHALL run `detect_invoice_po_mismatch()` against the referenced purchase order.
9. WHEN `detect_duplicate_payments()` returns a finding with `match_kind` of `exact_invoice_match`, THE Invoice_Processor SHALL set that finding's `severity` to `critical`.
10. WHEN any ComplianceFinding has `severity` of `critical` or the ML_Pipeline returns `risk_tier` of `critical`, THE Invoice_Processor SHALL create an `ApprovalRequest` with `status` of `pending` and set `requires_approval` to `true` on the invoice record before returning the response.
11. WHEN an invoice transitions from one status to another, THE Audit_Logger SHALL append an `AuditEntry` recording the action, actor, invoice ID, and timestamp.
12. THE Invoice_Processor SHALL support `POST /v1/invoices/batch` for uploading multiple invoice files in a single request, returning a list of `InvoiceUploadResponse` objects.
13. WHEN a `GET /v1/invoices` request is received, THE Invoice_Processor SHALL return invoices filtered by the authenticated user, with optional filtering by `status` and `risk_tier`.

---

### Requirement 3: Transaction Ingestion and AML/CFT Analysis

**User Story:** As a compliance officer, I want to ingest transaction batches from multiple sources (manual entry, SAP, Excel, Outlook) and have the platform run AML/CFT analysis and flag suspicious patterns, so that I can detect structuring, round-tripping, and other financial crimes before they escalate.

#### Acceptance Criteria

1. WHEN a `POST /v1/transactions/ingest` request is received, THE Transaction_Ingestor SHALL accept batches where `source` is one of: `manual`, `sap`, `excel`, `outlook`, or `csv`.
2. WHEN a transaction batch is received, THE Transaction_Ingestor SHALL apply PII_Redactor to all transaction `description` and `supplier` fields before passing them to any LLM call.
3. WHEN a transaction batch is ingested, THE Transaction_Ingestor SHALL run `DocumentAnomalies.scan_all()` to detect duplicate payments, invoice mismatches, and unusual transaction patterns.
4. WHEN `DocumentAnomalies.scan_all()` completes, THE Transaction_Ingestor SHALL run `TransactionAgent.run()` with Gemma to perform AML/CFT analysis and return an `AgentOutput` with `reasoning`, `sources`, and `confidence`.
5. WHEN the ML_Pipeline assigns `risk_tier` of `critical` to a transaction batch, THE Transaction_Ingestor SHALL create an `ApprovalRequest` with `status` of `pending` and set `requires_approval` to `true` in the `TransactionIngestResponse`.
6. WHEN `POST /v1/transactions/ingest/from-sap` is called, THE Transaction_Ingestor SHALL invoke `SAPODataConnector.fetch_supplier_invoices()` and map the raw OData results to `TransactionRecord` objects using SAP_Mapper before running the scan pipeline.
7. WHEN `POST /v1/transactions/ingest/from-excel` is called, THE Transaction_Ingestor SHALL connect to Microsoft Graph to retrieve the specified worksheet and map rows to `TransactionRecord` objects before running the scan pipeline.
8. IF the SAP connector is not configured (`is_configured()` returns `false`), THEN THE Transaction_Ingestor SHALL return HTTP 503 with an error message indicating the SAP connector is not set up.

---

### Requirement 4: Vendor Onboarding and KYC/KYB Workflow

**User Story:** As a compliance officer, I want to onboard new vendors through a structured KYC/KYB workflow that identifies document gaps and PEP/sanctions matches, so that the firm's vendor relationships are compliant with RBI KYC Master Direction 2016 and PMLA 2002.

#### Acceptance Criteria

1. WHEN a `POST /v1/vendors/onboard` request is received, THE Vendor_Onboarding_Workflow SHALL accept `vendor_name`, `vendor_gstin`, `vendor_pan`, `sector`, and a list of document uploads as input.
2. WHEN a vendor onboarding case is created, THE Vendor_Onboarding_Workflow SHALL invoke `OnboardingAgent.run()` to identify missing KYC/KYB documents and populate `missing_documents` in the case record.
3. WHEN `OnboardingAgent.run()` detects PEP flags (`pep_flags` non-empty), THE Vendor_Onboarding_Workflow SHALL set `risk_tier` to `critical` and create an `ApprovalRequest` with `status` of `pending` regardless of other feature values.
4. WHEN `OnboardingAgent.run()` completes, THE Vendor_Onboarding_Workflow SHALL set `kyc_status` to `in_review` if documents are missing, `approved` if all documents pass, or `escalated` if PEP or UBO issues are found.
5. WHEN a vendor onboarding case transitions status, THE Audit_Logger SHALL append an `AuditEntry` recording the transition, actor, and timestamp.
6. THE Vendor_Onboarding_Workflow SHALL store the onboarding case in the `vendor_onboarding_cases` table with all provided fields and the computed `missing_documents`, `pep_flags`, `ubo_issues`, `risk_tier`, and `kyc_status`.

---

### Requirement 5: FinTriageAgent Extended to 9 Tools

**User Story:** As a compliance analyst, I want a conversational agent that can perform what-if analysis, simulate penalties, compare entities, look up rules, generate reports, and trigger approval-gated external actions from a single chat interface, so that I have a single intelligent assistant for all compliance reasoning tasks.

#### Acceptance Criteria

1. THE FinTriageAgent SHALL support exactly the following 9 tools: `reassess`, `penalty_sim`, `threshold_sim`, `compare`, `explain_risk`, `rule_info`, `generate_report`, `external_action`, and `platform_help`.
2. WHEN a user message matches a regex pattern in `_INTENT_PATTERNS`, THE FinTriageAgent SHALL classify intent using that regex match without making any LLM call.
3. IF a user message does not match any regex pattern in `_INTENT_PATTERNS`, THEN THE FinTriageAgent SHALL classify intent by calling Gemma via `get_llm_client()`.
4. WHEN the `compare` tool is invoked and `session_context['entities']` contains fewer than 2 entries, THE FinTriageAgent SHALL call `_load_recent_entities()` to load recent assessment data from the database before attempting the comparison.
5. WHEN a user message contains patterns matching multiple distinct intents, THE FinTriageAgent SHALL execute all matched tools in the order: `reassess` → `penalty_sim` → `threshold_sim` → `compare` → `explain_risk` → `rule_info` → `generate_report` → `external_action`, and combine their outputs into a single coherent reply.
6. WHEN the `reassess` tool executes before another tool in a multi-intent chain, THE FinTriageAgent SHALL update `session_context['last_result']` and `session_context['last_features']` with the simulated result before running subsequent tools.
7. WHEN `external_action` is invoked, THE FinTriageAgent SHALL route the action through `execute_composio_tool_gated()` and return `status: pending_approval` in the reply without executing the external call directly.
8. IF Composio is not configured, THEN THE FinTriageAgent SHALL return a reply indicating Composio is not connected and describe which deterministic tools remain available.
9. IF Gemma's runtime does not support tool-calling during `external_action`, THEN THE FinTriageAgent SHALL fall back to text-based action classification and stage the action as an `ApprovalRequest` without using function-calling.
10. WHEN any tool in FinTriageAgent raises an unhandled exception, THE FinTriageAgent SHALL catch it, log the error, and return a user-facing error reply without propagating the exception.
11. ALL FinTriageAgent tool handler methods SHALL be `async` and callable with `asyncio.gather`.

---

### Requirement 6: Gemma-First Document Extraction

**User Story:** As a developer, I want the document extraction endpoint to accept file uploads and use Gemma as the primary extractor for all supported financial document types, so that extraction accuracy is higher than regex-only extraction and the endpoint supports real financial documents.

#### Acceptance Criteria

1. THE Gemma_Extractor SHALL accept requests to `POST /v1/compliance/extract` with either a file upload (PDF, DOCX, PNG, JPG, JPEG) or a `text` form field, or both.
2. IF neither `file` nor `text` is provided in the request, THEN THE Gemma_Extractor SHALL return HTTP 422 with a descriptive validation error.
3. WHEN a file is provided, THE Gemma_Extractor SHALL extract text from the file using the appropriate ingestion method (OCR for images, PDF parser for PDFs, DOCX parser for DOCX) before calling Gemma.
4. WHEN Gemma is available, THE Gemma_Extractor SHALL call `get_llm_client()` and `get_llm_model()` to extract all 9 financial features: `monthly_txn_volume`, `avg_ticket_size`, `cash_ratio`, `cross_border_ratio`, `late_payment_rate`, `business_age_years`, `sector_risk_score`, `director_count`, and `anomaly_risk_score`.
5. WHEN Gemma extraction completes, THE Gemma_Extractor SHALL return an `ExtractResponse` where every field in `extraction_fields` contains a `source` value from the set: `gemma`, `regex`, or `default`, and a `confidence` value in `[0.0, 1.0]`.
6. IF Gemma is unavailable, THEN THE Gemma_Extractor SHALL fall back to regex-based extraction and populate all 9 features with `source: "default"` and `confidence: 0.0` for any feature that could not be extracted by regex.
7. THE Gemma_Extractor SHALL apply PII_Redactor to all document text before constructing any Gemma prompt.
8. THE Gemma_Extractor SHALL accept `document_type` values of: `general`, `bank_statement`, `gst_filing`, `onboarding`, and `invoice`, and use a document-type-specific Gemma prompt for each.

---

### Requirement 7: Database Role Constraint Migration

**User Story:** As a system administrator, I want the database user role constraint to include FinOps roles, so that compliance officers, auditors, CFOs, finance analysts, and viewers can be assigned valid roles and the approval workflow functions correctly.

#### Acceptance Criteria

1. THE Role_Constraint on `users.role` SHALL accept all of the following values after migration: `lawyer`, `admin`, `paralegal`, `client`, `finance_analyst`, `compliance_officer`, `auditor`, `cfo`, and `viewer`.
2. WHEN the Alembic migration `add_finops_user_roles` is applied, THE Role_Constraint SHALL be updated in a single atomic `ALTER TABLE` statement that drops the old constraint and adds the new one.
3. WHEN the migration is applied, THE Role_Constraint SHALL continue to accept all four legacy role values (`lawyer`, `admin`, `paralegal`, `client`) so that existing user records remain valid.
4. THE migration `downgrade()` function SHALL restore the original constraint accepting only the four legacy role values.
5. WHEN the migration completes, every role listed in `APPROVER_ROLES` in `app/api/v1/approvals.py` (`compliance_officer`, `cfo`, `auditor`, `admin`) SHALL be a member of the updated Role_Constraint's accepted values.
6. THE migration SHALL log a warning for each existing user whose role is a legacy value, stating that those records remain valid under the new constraint.

---

### Requirement 8: SAP to Transaction Mapper

**User Story:** As a finance analyst, I want SAP OData supplier invoice records to be automatically mapped to the platform's transaction format and scanned for anomalies, so that I can run duplicate payment and invoice mismatch detection directly on SAP data without manual transformation.

#### Acceptance Criteria

1. THE SAP_Mapper SHALL map SAP OData field `SupplierInvoice` to `TransactionRecord.external_id`.
2. THE SAP_Mapper SHALL map SAP OData field `SupplierInvoiceIDByInvcgParty` to `TransactionRecord.invoice_number`.
3. THE SAP_Mapper SHALL map SAP OData field `Supplier` to `TransactionRecord.supplier`.
4. THE SAP_Mapper SHALL map SAP OData field `DocumentDate` to `TransactionRecord.transaction_date` parsed as `YYYY-MM-DD`.
5. THE SAP_Mapper SHALL map SAP OData field `InvoiceGrossAmount` to `TransactionRecord.amount` as a positive float.
6. THE SAP_Mapper SHALL map SAP OData field `DocumentCurrency` to `TransactionRecord.currency`.
7. THE SAP_Mapper SHALL map SAP OData field `PurchaseOrder` to `TransactionRecord.po_number`.
8. THE SAP_Mapper SHALL map SAP OData field `DocumentHeaderText` to `TransactionRecord.description`.
9. IF any optional SAP field is absent from the input dict, THEN THE SAP_Mapper SHALL populate the corresponding `TransactionRecord` field with an appropriate default (`None` for optional string fields, `""` for description, `datetime.now()` for missing date).
10. WHEN `POST /v1/connectors/sap/import-and-scan` is called, THE SAP_Mapper SHALL fetch invoices via `SAPODataConnector.fetch_supplier_invoices()`, map each to a `TransactionRecord`, and then pass the batch to the Transaction_Ingestor scan pipeline.

---

### Requirement 9: Role-Based Dashboards

**User Story:** As a platform user, I want a dashboard that shows only the information relevant to my role (finance analyst, compliance officer, auditor, CFO, or administrator), so that each team member gets a focused view without being overwhelmed by irrelevant data.

#### Acceptance Criteria

1. WHEN `GET /v1/dashboard` is called by a `finance_analyst`, THE Dashboard_API SHALL return sections: `recent_assessments`, `invoice_queue`, `transaction_feed`, and `penalty_exposure_summary`.
2. WHEN `GET /v1/dashboard` is called by a `compliance_officer`, THE Dashboard_API SHALL return sections: `critical_findings`, `pending_approvals`, `str_queue`, and `policy_gaps`.
3. WHEN `GET /v1/dashboard` is called by an `auditor`, THE Dashboard_API SHALL return sections: `audit_log`, `report_archive`, `pending_reviews`, and `critical_findings`.
4. WHEN `GET /v1/dashboard` is called by a `cfo`, THE Dashboard_API SHALL return sections: `penalty_exposure_summary`, `trend_charts`, `risk_heatmap`, and `top_critical_rules`.
5. WHEN `GET /v1/dashboard` is called by an `admin`, THE Dashboard_API SHALL return all sections available to all roles plus `user_management`, `connector_status`, and `system_health`.
6. THE Dashboard_API SHALL NOT return sections that are not defined for the requesting user's role.
7. WHEN the `pending_approvals` section is assembled for a `compliance_officer`, `auditor`, `cfo`, or `admin` user, THE Dashboard_API SHALL query all `ApprovalRequest` records in the user's organisation (`scope: "org"`).
8. WHEN the `pending_approvals` section is assembled for a `finance_analyst` or `viewer` user, THE Dashboard_API SHALL query only `ApprovalRequest` records created by that user (`scope: "user"`).
9. THE Dashboard_API SHALL include a `penalty_exposure_summary` object with `total`, `count`, `critical_count`, `trend_7d`, and `by_framework` fields whenever `penalty_exposure_summary` is in the role's section list.
10. IF a user's role is not one of the defined FinOps roles, THEN THE Dashboard_API SHALL return HTTP 403.

---

### Requirement 10: Frontend Workflow Pages

**User Story:** As a platform user, I want dedicated frontend pages for invoices, transactions, vendors, policies, assessment intake, audit logs, and integrations, so that each FinOps workflow has a purpose-built UI rather than being buried in a generic chat interface.

#### Acceptance Criteria

1. THE frontend SHALL provide a `/compliance/invoices` page that renders an invoice management queue with file upload capability and displays each invoice's status, risk tier, and any duplicate or mismatch findings.
2. THE frontend SHALL provide a `/compliance/transactions` page that renders a paginated transaction monitoring feed with filtering by severity and date range, and highlights flagged transactions with severity badges.
3. THE frontend SHALL provide a `/compliance/vendors` page that renders vendor onboarding cases with KYC status badges and document gap indicators.
4. THE frontend SHALL provide a `/compliance/policies` page that renders the policy document library with upload, version, and compliance gap indicators.
5. THE frontend SHALL provide an `/assess` page that implements a 5-step entity intake form with steps: (1) Business Identity, (2) Transaction Profile, (3) Document Upload, (4) Privacy Review, and (5) Flags Review.
6. WHEN a document is uploaded on Step 3 of the `/assess` form, THE frontend SHALL call `POST /v1/compliance/extract` and display extracted field values with confidence indicators (green for `gemma`, amber for `regex`, grey for `default`) on Step 4.
7. WHEN the user completes Step 5 of the `/assess` form and clicks "Run Full Assessment", THE frontend SHALL call `POST /v1/compliance/assess` with the confirmed feature values and toggled flags.
8. THE frontend SHALL provide a `/compliance/audit` page that renders the audit log viewer displaying `audit_trail_entries` with action, actor, timestamp, and workflow reference.
9. THE frontend SHALL provide an `/integrations` page that displays connector status for Composio, SAP, and Microsoft Graph, and supports initiating OAuth connection flows for each Composio toolkit.
10. WHEN a Composio OAuth connection is initiated from the `/integrations` page, THE frontend SHALL call `POST /v1/connectors/composio/connect/{toolkit}` and open the returned `redirect_url` in a popup window.
