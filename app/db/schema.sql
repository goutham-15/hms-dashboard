CREATE TYPE risk_status_enum AS ENUM ('Critical', 'High Risk', 'Moderate Risk', 'Healthy');

CREATE TABLE hms_health_records (
    -- 1. STAFF DETAILS (Direct columns for fast filtering/sorting)
    id VARCHAR(50) PRIMARY KEY,
    employee_id VARCHAR(50) NOT NULL,
    year INT NOT NULL, -- e.g., 2024, 2025
    name VARCHAR(100) NOT NULL,
    age INT NOT NULL,
    gender VARCHAR(10) NOT NULL,
    department VARCHAR(50) NOT NULL, -- e.g., 'IT Department', 'Mechanical Engg'
    screening_date DATE NOT NULL,
    
    -- 2. DASHBOARD ANALYTICS (Direct columns for the UI widgets)
    health_score INT DEFAULT 0, -- 0 to 100
    status risk_status_enum NOT NULL,
    active_flags JSONB, -- Array of strings: ["HbA1c Diabetic", "Low Vitamin B12"]
    
    -- 3. THYROCARE DATA (Deep biochemical results)
    -- Stored as JSONB for flexibility across different test packages
    thyrocare_results JSONB, 
    
    -- 4. SECONDMEDIC DATA (Textual impressions and measurements)
    -- Stores USG, ECG, X-Ray, and Echo findings
    secondmedic_results JSONB, 
    
    -- 5. REPORT CONTENT
    inference TEXT,
    suggestion JSONB, -- Array of strings for the "Recommendations" section
    
    -- 6. SYSTEM METADATA
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint to allow one record per staff per year
    UNIQUE (employee_id, year)
);

-- Indexing for Dashboard Performance
CREATE INDEX idx_dept ON hms_health_records(department);
CREATE INDEX idx_status ON hms_health_records(status);
CREATE INDEX idx_flags ON hms_health_records USING GIN (active_flags);
CREATE INDEX idx_employee_year ON hms_health_records(employee_id, year);
