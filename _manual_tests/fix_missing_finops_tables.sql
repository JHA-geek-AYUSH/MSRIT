-- Creates ONLY the 3 tables missing from the partially-applied migration
-- 540d6b34a446. Does not touch entities / compliance_assessments /
-- compliance_findings, which already exist with your real data intact.

CREATE TABLE penalty_simulations (
    id UUID PRIMARY KEY,
    assessment_id UUID REFERENCES compliance_assessments(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    scenario_id VARCHAR NOT NULL,
    rule_code VARCHAR,
    days_since_breach INTEGER,
    aggravating_factors JSON,
    base_fine NUMERIC,
    per_day_fine NUMERIC,
    total_fine NUMERIC,
    imprisonment_risk BOOLEAN,
    verdict TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE audit_reports (
    id UUID PRIMARY KEY,
    assessment_id UUID REFERENCES compliance_assessments(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    report_json JSON,
    gemma_summary TEXT,
    total_penalty_exposure NUMERIC,
    urgency_tier VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE fintriage_chat_messages (
    id UUID PRIMARY KEY,
    assessment_id UUID REFERENCES compliance_assessments(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR NOT NULL,
    content TEXT NOT NULL,
    tool_used VARCHAR,
    tool_result JSON,
    confidence NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
CREATE INDEX idx_fintriage_chat_user ON fintriage_chat_messages(user_id);

-- entities/compliance_assessments/compliance_findings already have their data;
-- add the two indexes the migration expects, if they don't already exist
CREATE INDEX IF NOT EXISTS idx_assessments_entity ON compliance_assessments(entity_id);
CREATE INDEX IF NOT EXISTS idx_assessments_user ON compliance_assessments(user_id);
CREATE INDEX IF NOT EXISTS idx_findings_assessment ON compliance_findings(assessment_id);
