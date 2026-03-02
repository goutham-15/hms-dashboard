-- Medical Reports Database Schema (Single Table with Separate Columns)
-- Stores all medical reports with each field as a separate column
-- Based on MedicalReportData Pydantic model

CREATE TABLE medical_reports (
    id SERIAL PRIMARY KEY,
    
    -- Staff Details (StaffDetails model)
    staff_id VARCHAR(100) DEFAULT '',
    staff_name VARCHAR(255) DEFAULT '',
    staff_designation VARCHAR(255) DEFAULT '',
    staff_department VARCHAR(255) DEFAULT '',
    staff_contact VARCHAR(50) DEFAULT '',
    staff_email VARCHAR(255) DEFAULT '',
    
    -- Thyrocare Report Info (ThyrocareReportInfo model)
    thyrocare_report_id VARCHAR(255) DEFAULT '',
    thyrocare_report_version VARCHAR(50) DEFAULT '',
    thyrocare_date DATE,
    thyrocare_generated_at TIMESTAMP,
    thyrocare_lab_name VARCHAR(255) DEFAULT '',
    thyrocare_lab_code VARCHAR(100) DEFAULT '',
    thyrocare_status VARCHAR(20) CHECK (thyrocare_status IN ('PRELIMINARY', 'FINAL', 'CORRECTED')),
    thyrocare_source_system VARCHAR(100) DEFAULT '',
    
    -- Thyrocare Patient Details (ThyrocarePatientDetails model)
    thyrocare_patient_id VARCHAR(255) DEFAULT '',
    thyrocare_patient_name VARCHAR(255) DEFAULT '',
    thyrocare_patient_age INTEGER CHECK (thyrocare_patient_age >= 0 AND thyrocare_patient_age <= 130),
    thyrocare_patient_gender VARCHAR(10) CHECK (thyrocare_patient_gender IN ('MALE', 'FEMALE', 'OTHER')),
    thyrocare_referred_by VARCHAR(255) DEFAULT '',
    
    -- Thyrocare Test Results (stored as JSONB array - complex nested structure)
    thyrocare_test_results JSONB DEFAULT '[]'::jsonb,
    
    -- Thyrocare Summary (ThyrocareSummary model)
    thyrocare_total_tests_ready INTEGER DEFAULT 0 CHECK (thyrocare_total_tests_ready >= 0),
    thyrocare_out_of_range_count INTEGER DEFAULT 0 CHECK (thyrocare_out_of_range_count >= 0),
    
    -- Thyrocare Doctor Verification (DoctorVerification model)
    thyrocare_doctor_name VARCHAR(255) DEFAULT '',
    thyrocare_doctor_designation VARCHAR(255) DEFAULT '',
    thyrocare_doctor_license_number VARCHAR(100) DEFAULT '',
    thyrocare_doctor_signed_at TIMESTAMP,
    
    -- SecondMedic Report Info (SecondMedicReportInfo model)
    secondmedic_date DATE,
    secondmedic_institution VARCHAR(255) DEFAULT '',
    secondmedic_case_ids JSONB,
    
    -- SecondMedic Patient Details (SecondMedicPatientDetails model)
    secondmedic_patient_name VARCHAR(255) DEFAULT '',
    secondmedic_patient_age INTEGER CHECK (secondmedic_patient_age >= 0 AND secondmedic_patient_age <= 130),
    secondmedic_patient_gender VARCHAR(10) CHECK (secondmedic_patient_gender IN ('MALE', 'FEMALE', 'OTHER')),
    
    -- SecondMedic Diagnostics (stored as JSONB array - complex nested structure)
    secondmedic_diagnostics JSONB DEFAULT '[]'::jsonb,
    
    -- SecondMedic Summary Findings
    secondmedic_summary_findings JSONB,
    
    -- Overall medical inference/conclusion
    inference TEXT NOT NULL DEFAULT '',
    
    -- Cost information (stored as JSONB for flexible structure)
    cost JSONB,
    
    -- Year tracking (automatically extracted from report dates)
    report_year INTEGER,
    
    -- Audit fields
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_medical_reports_report_year ON medical_reports(report_year);
CREATE INDEX idx_medical_reports_created_at ON medical_reports(created_at);

-- Staff indexes
CREATE INDEX idx_medical_reports_staff_id ON medical_reports(staff_id);
CREATE INDEX idx_medical_reports_staff_name ON medical_reports(staff_name);
CREATE INDEX idx_medical_reports_staff_department ON medical_reports(staff_department);

-- Thyrocare indexes
CREATE INDEX idx_medical_reports_thyrocare_report_id ON medical_reports(thyrocare_report_id);
CREATE INDEX idx_medical_reports_thyrocare_date ON medical_reports(thyrocare_date);
CREATE INDEX idx_medical_reports_thyrocare_patient_id ON medical_reports(thyrocare_patient_id);
CREATE INDEX idx_medical_reports_thyrocare_patient_name ON medical_reports(thyrocare_patient_name);
CREATE INDEX idx_medical_reports_thyrocare_lab_name ON medical_reports(thyrocare_lab_name);

-- SecondMedic indexes
CREATE INDEX idx_medical_reports_secondmedic_date ON medical_reports(secondmedic_date);
CREATE INDEX idx_medical_reports_secondmedic_institution ON medical_reports(secondmedic_institution);
CREATE INDEX idx_medical_reports_secondmedic_patient_name ON medical_reports(secondmedic_patient_name);

-- GIN indexes for JSONB columns (test_results, diagnostics, case_ids, summary_findings, cost)
CREATE INDEX idx_medical_reports_thyrocare_test_results ON medical_reports USING GIN (thyrocare_test_results);
CREATE INDEX idx_medical_reports_secondmedic_diagnostics ON medical_reports USING GIN (secondmedic_diagnostics);
CREATE INDEX idx_medical_reports_secondmedic_case_ids ON medical_reports USING GIN (secondmedic_case_ids);
CREATE INDEX idx_medical_reports_cost ON medical_reports USING GIN (cost);

-- Full text search index on inference
CREATE INDEX idx_medical_reports_inference ON medical_reports USING GIN (to_tsvector('english', inference));

-- Trigger to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_medical_reports_updated_at 
    BEFORE UPDATE ON medical_reports 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger to automatically extract report_year from date columns
CREATE OR REPLACE FUNCTION extract_report_year()
RETURNS TRIGGER AS $$
BEGIN
    -- Extract year from thyrocare_date if available
    IF NEW.thyrocare_date IS NOT NULL THEN
        NEW.report_year = EXTRACT(YEAR FROM NEW.thyrocare_date);
    -- Otherwise try secondmedic_date
    ELSIF NEW.secondmedic_date IS NOT NULL THEN
        NEW.report_year = EXTRACT(YEAR FROM NEW.secondmedic_date);
    END IF;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER set_medical_report_year 
    BEFORE INSERT OR UPDATE ON medical_reports 
    FOR EACH ROW 
    EXECUTE FUNCTION extract_report_year();

-- Example queries based on separate column structure:

-- 1. Query all reports by year
-- SELECT * FROM medical_reports WHERE report_year = 2024;

-- 2. Query Thyrocare reports with patient details
-- SELECT 
--     id,
--     staff_name,
--     thyrocare_report_id,
--     thyrocare_date,
--     thyrocare_patient_name,
--     thyrocare_patient_age,
--     thyrocare_total_tests_ready,
--     inference
-- FROM medical_reports 
-- WHERE thyrocare_report_id != '';

-- 3. Query SecondMedic reports with institution
-- SELECT 
--     id,
--     staff_name,
--     secondmedic_institution,
--     secondmedic_patient_name,
--     jsonb_array_length(secondmedic_diagnostics) AS diagnostic_count,
--     inference
-- FROM medical_reports 
-- WHERE secondmedic_institution != '';

-- 4. Find high/critical test results in Thyrocare data
-- SELECT 
--     id,
--     thyrocare_patient_name,
--     test->>'test_name' AS test_name,
--     (test->>'value')::float AS value,
--     test->>'units' AS units,
--     test->>'result_flag' AS flag,
--     inference
-- FROM medical_reports,
--     jsonb_array_elements(thyrocare_test_results) AS test
-- WHERE test->>'result_flag' IN ('HIGH', 'CRITICAL')
-- AND report_year = 2024;

-- 5. Query SecondMedic diagnostics by category
-- SELECT 
--     id,
--     secondmedic_patient_name,
--     diag->>'test_category' AS category,
--     diag->>'test_name' AS test_name,
--     diag->>'impression' AS impression,
--     inference
-- FROM medical_reports,
--     jsonb_array_elements(secondmedic_diagnostics) AS diag
-- WHERE diag->>'test_category' = 'Radiology'
-- AND report_year = 2024;

-- 6. Search in inference text (full-text search)
-- SELECT * FROM medical_reports 
-- WHERE to_tsvector('english', inference) @@ to_tsquery('english', 'diabetes & cholesterol');

-- 7. Query by staff member
-- SELECT * FROM medical_reports 
-- WHERE staff_name = 'Dr. John Smith'
-- ORDER BY created_at DESC;

-- 8. Query by staff department
-- SELECT * FROM medical_reports 
-- WHERE staff_department = 'Pathology';

-- 9. Count reports by year and type
-- SELECT 
--     report_year,
--     CASE 
--         WHEN thyrocare_report_id != '' THEN 'Thyrocare'
--         WHEN secondmedic_institution != '' THEN 'SecondMedic'
--         ELSE 'Unknown'
--     END AS report_type,
--     COUNT(*) AS count
-- FROM medical_reports 
-- GROUP BY report_year, report_type
-- ORDER BY report_year DESC, report_type;

-- 10. Get all test results for a specific patient
-- SELECT 
--     thyrocare_date AS report_date,
--     test->>'test_name' AS test_name,
--     (test->>'value')::float AS value,
--     test->>'units' AS units,
--     test->>'result_flag' AS flag
-- FROM medical_reports,
--     jsonb_array_elements(thyrocare_test_results) AS test
-- WHERE thyrocare_patient_id = 'P123456'
-- ORDER BY thyrocare_date DESC;

-- 11. Get diagnostic metrics from SecondMedic reports
-- SELECT 
--     id,
--     secondmedic_patient_name,
--     diag->>'test_name' AS test_name,
--     metric->>'parameter' AS parameter,
--     (metric->>'value')::float AS value,
--     metric->>'units' AS units
-- FROM medical_reports,
--     jsonb_array_elements(secondmedic_diagnostics) AS diag,
--     jsonb_array_elements(diag->'metrics') AS metric
-- WHERE secondmedic_diagnostics != '[]'::jsonb;

-- 12. Query reports with Thyrocare doctor verification
-- SELECT 
--     id,
--     thyrocare_patient_name,
--     thyrocare_doctor_name,
--     thyrocare_doctor_signed_at,
--     inference
-- FROM medical_reports 
-- WHERE thyrocare_doctor_name != '';

-- 13. Query by patient across both report types
-- SELECT 
--     id,
--     COALESCE(thyrocare_patient_name, secondmedic_patient_name) AS patient_name,
--     COALESCE(thyrocare_date, secondmedic_date) AS report_date,
--     report_year,
--     inference
-- FROM medical_reports 
-- WHERE thyrocare_patient_name = 'Jane Doe' OR secondmedic_patient_name = 'Jane Doe'
-- ORDER BY COALESCE(thyrocare_date, secondmedic_date) DESC;

-- 14. Get summary statistics by staff
-- SELECT 
--     staff_name,
--     staff_department,
--     COUNT(*) AS total_reports,
--     COUNT(CASE WHEN thyrocare_report_id != '' THEN 1 END) AS thyrocare_count,
--     COUNT(CASE WHEN secondmedic_institution != '' THEN 1 END) AS secondmedic_count
-- FROM medical_reports 
-- GROUP BY staff_name, staff_department
-- ORDER BY total_reports DESC;
