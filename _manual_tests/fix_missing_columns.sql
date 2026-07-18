-- Adds the columns the current code expects but the pre-existing tables
-- (created before these fields were added to the schema) are missing.
-- Purely additive -- does not touch your existing 9 entities / 3 assessments /
-- 15 findings.

ALTER TABLE compliance_assessments ADD COLUMN IF NOT EXISTS feature_importance JSON;
ALTER TABLE compliance_assessments ADD COLUMN IF NOT EXISTS detected_flags JSON;
ALTER TABLE compliance_assessments ADD COLUMN IF NOT EXISTS total_penalty_exposure_inr NUMERIC;
ALTER TABLE compliance_assessments ADD COLUMN IF NOT EXISTS raw_features JSON;

ALTER TABLE compliance_findings ADD COLUMN IF NOT EXISTS cosine_similarity NUMERIC;
ALTER TABLE compliance_findings ADD COLUMN IF NOT EXISTS combined_score NUMERIC;
ALTER TABLE compliance_findings ADD COLUMN IF NOT EXISTS warning_flags JSON;
ALTER TABLE compliance_findings ADD COLUMN IF NOT EXISTS remediation_steps JSON;
