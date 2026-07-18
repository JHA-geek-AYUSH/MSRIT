SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('entities', 'compliance_assessments', 'compliance_findings')
ORDER BY table_name, ordinal_position;
