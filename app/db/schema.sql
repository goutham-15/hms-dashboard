-- SQL Server Schema

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'hms_health_records')
BEGIN
    CREATE TABLE hms_health_records (
        -- 1. STAFF DETAILS
        id NVARCHAR(50) PRIMARY KEY,
        employee_id NVARCHAR(50) NOT NULL,
        year INT NOT NULL,
        name NVARCHAR(100) NOT NULL,
        age INT NOT NULL,
        gender NVARCHAR(10) NOT NULL,
        department NVARCHAR(50) NOT NULL,
        screening_date DATE NOT NULL,
        
        -- 2. DASHBOARD ANALYTICS
        health_score INT DEFAULT 0,
        status NVARCHAR(20) NOT NULL, -- 'Critical', 'High Risk', 'Moderate Risk', 'Healthy'
        active_flags NVARCHAR(MAX), -- JSON string
        
        -- 3. THYROCARE DATA
        thyrocare_results NVARCHAR(MAX), -- JSON string
        
        -- 4. SECONDMEDIC DATA
        secondmedic_results NVARCHAR(MAX), -- JSON string
        
        -- 5. REPORT CONTENT
        inference NVARCHAR(MAX),
        suggestion NVARCHAR(MAX), -- JSON string
        
        -- 6. SYSTEM METADATA
        cost NVARCHAR(MAX), -- JSON string
        created_at DATETIME2 DEFAULT GETUTCDATE(),

        -- Unique constraint
        CONSTRAINT UC_Employee_Year UNIQUE (employee_id, year)
    );

    -- Indexing
    CREATE INDEX idx_dept ON hms_health_records(department);
    CREATE INDEX idx_status ON hms_health_records(status);
    CREATE INDEX idx_employee_year ON hms_health_records(employee_id, year);
END
GO
