-- ============================================================
-- NIMS Hospital Voice Assistant  –  Database Schema & Seed Data
-- Database: Nims_hospital_db
-- ============================================================
-- Run:
--   1. CREATE DATABASE "Nims_hospital_db";
--   2. psql -U postgres -d Nims_hospital_db -f db_schema.sql
--
-- Tables (6):
--   departments    – hospital departments
--   doctors        – physicians linked to departments
--   nurses         – nursing staff linked to departments & wards
--   wards          – hospital wards with bed capacity
--   appointments   – patient bookings (duplicate-safe, availability-aware)
--   hospital_info  – key-value pairs for general hospital data
-- ============================================================

-- =========================
-- 0. Clean slate (dev only)
-- =========================
DROP TABLE IF EXISTS appointments CASCADE;
DROP TABLE IF EXISTS nurses       CASCADE;
DROP TABLE IF EXISTS doctors       CASCADE;
DROP TABLE IF EXISTS wards         CASCADE;
DROP TABLE IF EXISTS departments   CASCADE;
DROP TABLE IF EXISTS hospital_info CASCADE;

-- =========================
-- 1. Departments
-- =========================
CREATE TABLE departments (
    department_id   SERIAL        PRIMARY KEY,
    name            VARCHAR(100)  NOT NULL UNIQUE,
    description     TEXT          NOT NULL DEFAULT '',
    floor           INTEGER       NOT NULL,
    room_no         VARCHAR(20)   NOT NULL,
    phone_ext       VARCHAR(20)   NOT NULL DEFAULT '',
    is_active       BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_departments_name  ON departments (LOWER(name));
CREATE INDEX idx_departments_floor ON departments (floor);

-- =========================
-- 2. Doctors
-- =========================
CREATE TABLE doctors (
    doctor_id           SERIAL        PRIMARY KEY,
    name                VARCHAR(100)  NOT NULL,
    specialization      VARCHAR(100)  NOT NULL,
    qualification       TEXT          NOT NULL DEFAULT '',
    department_id       INTEGER       NOT NULL REFERENCES departments(department_id) ON DELETE CASCADE,
    registration_number VARCHAR(50)   NOT NULL DEFAULT '',
    floor               INTEGER       NOT NULL,
    room_no             VARCHAR(20)   NOT NULL,
    availability        VARCHAR(30)   NOT NULL DEFAULT 'Available',
    available_days      VARCHAR(100)  NOT NULL DEFAULT 'Mon-Sat',
    available_time      VARCHAR(50)   NOT NULL DEFAULT '09:00-17:00',
    consultation_fee    INTEGER       NOT NULL DEFAULT 500,
    phone_ext           VARCHAR(20)   NOT NULL DEFAULT '',
    is_active           BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_doctors_name           ON doctors (LOWER(name));
CREATE INDEX idx_doctors_specialization ON doctors (LOWER(specialization));
CREATE INDEX idx_doctors_department     ON doctors (department_id);
CREATE INDEX idx_doctors_availability   ON doctors (LOWER(availability));

-- =========================
-- 3. Wards
-- =========================
CREATE TABLE wards (
    ward_id         SERIAL        PRIMARY KEY,
    name            VARCHAR(100)  NOT NULL UNIQUE,
    ward_type       VARCHAR(50)   NOT NULL DEFAULT 'General',
    department_id   INTEGER       NOT NULL REFERENCES departments(department_id) ON DELETE CASCADE,
    floor           INTEGER       NOT NULL,
    total_beds      INTEGER       NOT NULL DEFAULT 10,
    available_beds  INTEGER       NOT NULL DEFAULT 10,
    phone_ext       VARCHAR(20)   NOT NULL DEFAULT '',
    is_active       BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_beds CHECK (available_beds >= 0 AND available_beds <= total_beds)
);

CREATE INDEX idx_wards_department ON wards (department_id);
CREATE INDEX idx_wards_type       ON wards (LOWER(ward_type));

-- =========================
-- 4. Nurses
-- =========================
CREATE TABLE nurses (
    nurse_id        SERIAL        PRIMARY KEY,
    name            VARCHAR(100)  NOT NULL,
    qualification   VARCHAR(100)  NOT NULL DEFAULT '',
    department_id   INTEGER       NOT NULL REFERENCES departments(department_id) ON DELETE CASCADE,
    ward_id         INTEGER       REFERENCES wards(ward_id) ON DELETE SET NULL,
    shift           VARCHAR(30)   NOT NULL DEFAULT 'Day',
    phone_ext       VARCHAR(20)   NOT NULL DEFAULT '',
    is_active       BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_nurses_department ON nurses (department_id);
CREATE INDEX idx_nurses_ward       ON nurses (ward_id);
CREATE INDEX idx_nurses_shift      ON nurses (LOWER(shift));

-- =========================
-- 5. Appointments
-- =========================
CREATE TABLE appointments (
    appointment_id  SERIAL        PRIMARY KEY,
    patient_name    VARCHAR(100)  NOT NULL,
    patient_phone   VARCHAR(20)   NOT NULL DEFAULT '',
    doctor_id       INTEGER       NOT NULL REFERENCES doctors(doctor_id) ON DELETE CASCADE,
    appointment_date DATE         NOT NULL,
    appointment_time VARCHAR(20)  NOT NULL,
    status          VARCHAR(30)   NOT NULL DEFAULT 'Scheduled',
    notes           TEXT          NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    -- Prevent duplicate bookings: same doctor + date + time
    CONSTRAINT uq_doctor_slot UNIQUE (doctor_id, appointment_date, appointment_time)
);

CREATE INDEX idx_appointments_patient ON appointments (LOWER(patient_name));
CREATE INDEX idx_appointments_doctor  ON appointments (doctor_id);
CREATE INDEX idx_appointments_date    ON appointments (appointment_date);
CREATE INDEX idx_appointments_status  ON appointments (LOWER(status));

-- =========================
-- 6. Hospital Info (key-value)
-- =========================
CREATE TABLE hospital_info (
    info_key    VARCHAR(80)  PRIMARY KEY,
    info_value  TEXT         NOT NULL,
    category    VARCHAR(50)  NOT NULL DEFAULT 'general',
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_hospital_info_category ON hospital_info (LOWER(category));


-- ============================================================
-- SEED DATA
-- ============================================================

-- Departments (8)
INSERT INTO departments (name, description, floor, room_no, phone_ext) VALUES
    ('Cardiology',        'Heart and cardiovascular diseases',           2, '201', '2001'),
    ('Neurology',         'Brain, spine, and nervous system disorders',  4, '401', '4001'),
    ('Orthopedics',       'Bone, joint, and musculoskeletal care',       2, '210', '2010'),
    ('Dermatology',       'Skin, hair, and nail conditions',             1, '105', '1005'),
    ('General Surgery',   'Surgical procedures and post-op care',        3, '301', '3001'),
    ('Pediatrics',        'Child healthcare from birth to 18 years',     1, '110', '1010'),
    ('ENT',               'Ear, nose, and throat treatments',            3, '310', '3010'),
    ('Emergency',         'Emergency and trauma care, open 24 hours',    0, 'E-01','9001')
ON CONFLICT (name) DO NOTHING;

-- Doctors (14)
INSERT INTO doctors (name, specialization, qualification, department_id, registration_number, floor, room_no, availability, available_days, available_time, consultation_fee, phone_ext) VALUES
    ('Dr. Madhav Reddy',     'Cardiologist',         'MBBS, MD Cardiology, FESC',       1, 'AP-MCI-28341', 2, '202', 'Available',   'Mon-Sat', '09:00-16:00', 800,  '2002'),
    ('Dr. Lakshmi Nair',     'Cardiologist',         'MBBS, DM Cardiology',             1, 'AP-MCI-31456', 2, '203', 'On Leave',    'Mon-Fri', '10:00-15:00', 700,  '2003'),
    ('Dr. Anjali Desai',     'Neurologist',          'MBBS, DM Neurology',              2, 'AP-MCI-29012', 4, '403', 'Available',   'Mon-Sat', '09:00-17:00', 900,  '4003'),
    ('Dr. Arjun Patel',      'Neurologist',          'MBBS, MD Neurology, DNB',         2, 'AP-MCI-30891', 4, '404', 'Available',   'Tue-Sat', '10:00-16:00', 850,  '4004'),
    ('Dr. Suresh Babu',      'Orthopedic Surgeon',   'MBBS, MS Orthopedics',            3, 'AP-MCI-27654', 2, '211', 'Available',   'Mon-Sat', '09:00-17:00', 750,  '2011'),
    ('Dr. Priya Sharma',     'Dermatologist',        'MBBS, MD Dermatology',            4, 'AP-MCI-33102', 1, '106', 'Available',   'Mon-Fri', '09:00-14:00', 600,  '1006'),
    ('Dr. Kavitha Rao',      'Dermatologist',        'MBBS, DVD, DNB Derm',             4, 'AP-MCI-34210', 1, '107', 'Available',   'Mon-Sat', '10:00-16:00', 650,  '1007'),
    ('Dr. Ravi Kumar',       'General Surgeon',      'MBBS, MS General Surgery',        5, 'AP-MCI-26789', 3, '302', 'Available',   'Mon-Sat', '08:00-15:00', 700,  '3002'),
    ('Dr. Meena Iyer',       'Pediatrician',         'MBBS, MD Pediatrics, IAP Fellow', 6, 'AP-MCI-35011', 1, '111', 'Available',   'Mon-Sat', '09:00-17:00', 500,  '1011'),
    ('Dr. Sanjay Gupta',     'Pediatric Surgeon',    'MBBS, MCh Pediatric Surgery',     6, 'AP-MCI-36402', 1, '112', 'Available',   'Mon-Fri', '10:00-15:00', 800,  '1012'),
    ('Dr. Ramesh Varma',     'ENT Specialist',       'MBBS, MS ENT',                    7, 'AP-MCI-28903', 3, '311', 'Available',   'Mon-Sat', '09:00-16:00', 600,  '3011'),
    ('Dr. Sneha Kulkarni',   'Emergency Medicine',   'MBBS, MD Emergency Medicine',     8, 'AP-MCI-37801', 0, 'E-02','Available',   'Mon-Sun', '00:00-23:59', 400,  '9002'),
    ('Dr. Vikram Singh',     'Trauma Surgeon',       'MBBS, MS Surgery, MCh Trauma',    8, 'AP-MCI-38210', 0, 'E-03','Available',   'Mon-Sun', '00:00-23:59', 500,  '9003'),
    ('Dr. Farah Khan',       'Emergency Medicine',   'MBBS, MRCEM',                     8, 'AP-MCI-39100', 0, 'E-04','On Leave',    'Mon-Sun', '00:00-23:59', 400,  '9004')
ON CONFLICT DO NOTHING;

-- Wards (10)
INSERT INTO wards (name, ward_type, department_id, floor, total_beds, available_beds, phone_ext) VALUES
    ('Cardiac ICU',         'ICU',      1, 2, 12,  4, '2050'),
    ('Cardiac General',     'General',  1, 2, 20, 11, '2051'),
    ('Neuro ICU',           'ICU',      2, 4,  8,  3, '4050'),
    ('Neuro General',       'General',  2, 4, 16,  9, '4051'),
    ('Ortho Ward',          'General',  3, 2, 18, 10, '2060'),
    ('Surgical Ward',       'General',  5, 3, 24, 14, '3050'),
    ('Surgical ICU',        'ICU',      5, 3,  6,  2, '3051'),
    ('Pediatric Ward',      'General',  6, 1, 20, 12, '1050'),
    ('Pediatric ICU',       'ICU',      6, 1,  8,  5, '1051'),
    ('Emergency Ward',      'Emergency',8, 0, 30, 18, '9050')
ON CONFLICT (name) DO NOTHING;

-- Nurses (16)
INSERT INTO nurses (name, qualification, department_id, ward_id, shift, phone_ext) VALUES
    ('Sr. Nurse Padma',      'BSc Nursing, CCU Certified',  1,  1, 'Day',   '2070'),
    ('Nurse Revathi',        'GNM',                         1,  1, 'Night', '2071'),
    ('Nurse Deepa',          'BSc Nursing',                 1,  2, 'Day',   '2072'),
    ('Sr. Nurse Sunita',     'MSc Nursing, Neuro ICU',      2,  3, 'Day',   '4070'),
    ('Nurse Anitha',         'GNM',                         2,  4, 'Night', '4071'),
    ('Nurse Swathi',         'BSc Nursing',                 3,  5, 'Day',   '2080'),
    ('Nurse Ramya',          'GNM',                         3,  5, 'Night', '2081'),
    ('Sr. Nurse Bhavani',    'MSc Nursing, OT Certified',   5,  6, 'Day',   '3070'),
    ('Nurse Jyothi',         'BSc Nursing',                 5,  7, 'Night', '3071'),
    ('Sr. Nurse Saroja',     'MSc Nursing, Pediatric',      6,  8, 'Day',   '1070'),
    ('Nurse Lavanya',        'BSc Nursing',                 6,  8, 'Day',   '1071'),
    ('Nurse Keerthi',        'GNM',                         6,  9, 'Night', '1072'),
    ('Nurse Divya',          'BSc Nursing',                 7, NULL,'Day',   '3080'),
    ('Sr. Nurse Radha',      'MSc Nursing, Trauma Care',    8, 10, 'Day',   '9070'),
    ('Nurse Fatima',         'BSc Nursing, BLS/ACLS',       8, 10, 'Night', '9071'),
    ('Nurse Vani',           'GNM',                         8, 10, 'Night', '9072')
ON CONFLICT DO NOTHING;

-- Appointments (sample for today + tomorrow)
INSERT INTO appointments (patient_name, patient_phone, doctor_id, appointment_date, appointment_time, status, notes) VALUES
    ('Rajesh Kumar',     '9876543210',  1, CURRENT_DATE,     '10:00 AM', 'Scheduled',  'Follow-up ECG review'),
    ('Sita Devi',        '9876501234',  6, CURRENT_DATE,     '11:30 AM', 'Confirmed',  'Skin allergy consultation'),
    ('Venkat Rao',       '9988776655',  3, CURRENT_DATE,     '02:00 PM', 'Scheduled',  'Migraine follow-up'),
    ('Priya Reddy',      '9123456780',  8, CURRENT_DATE,     '03:30 PM', 'Cancelled',  'Cancelled by patient'),
    ('Mohammed Ismail',  '9001234567',  5, CURRENT_DATE,     '11:00 AM', 'Confirmed',  'Knee replacement pre-op'),
    ('Lakshmi Devi',     '9556677889',  9, CURRENT_DATE,     '10:30 AM', 'Scheduled',  'Child vaccination'),
    ('Naveen Chandra',   '9445566778',  1, CURRENT_DATE + 1, '09:30 AM', 'Scheduled',  'Cardiac stress test'),
    ('Anjali Prasad',    '9334455667',  3, CURRENT_DATE + 1, '11:00 AM', 'Scheduled',  'Neuro assessment'),
    ('Ramu Naidu',       '9223344556',  11,CURRENT_DATE,     '03:00 PM', 'Confirmed',  'Ear infection follow-up'),
    ('Swapna Rani',      '9112233445',  9, CURRENT_DATE + 1, '04:00 PM', 'Scheduled',  'Pediatric checkup')
ON CONFLICT (doctor_id, appointment_date, appointment_time) DO NOTHING;

-- Hospital Info (key-value, categorized)
INSERT INTO hospital_info (info_key, info_value, category) VALUES
    ('name',               'NIMS Multi-Speciality Hospital',                       'general'),
    ('address',            'Punjagutta, Hyderabad, Telangana 500082',              'general'),
    ('phone',              '+91-40-2345-6789',                                     'general'),
    ('email',              'info@nimshospital.in',                                 'general'),
    ('website',            'www.nimshospital.in',                                  'general'),
    ('established',        '1998',                                                 'general'),
    ('total_beds',         '250',                                                  'general'),
    ('total_floors',       '5 (Ground + 4)',                                       'general'),
    ('opd_hours',          'Monday to Saturday, 9:00 AM to 5:00 PM',              'opd'),
    ('opd_registration',   'Ground Floor, Counter 1-4',                            'opd'),
    ('opd_phone',          '+91-40-2345-6790',                                     'opd'),
    ('emergency_location', 'Ground Floor (Floor 0), Room E-01',                    'emergency'),
    ('emergency_hours',    '24 hours, 7 days a week',                              'emergency'),
    ('emergency_phone',    '+91-40-2345-6700',                                     'emergency'),
    ('ambulance_number',   '108 (Toll-free) or +91-40-2345-6701',                 'emergency'),
    ('pharmacy_location',  'Ground Floor, near main entrance',                     'pharmacy'),
    ('pharmacy_hours',     'Open 24 hours (emergency medicines always available)', 'pharmacy'),
    ('pharmacy_phone',     '+91-40-2345-6750',                                     'pharmacy'),
    ('visiting_hours',     '4:00 PM to 6:00 PM daily',                             'visiting'),
    ('icu_visiting',       '11:00 AM to 11:30 AM and 5:00 PM to 5:30 PM',         'visiting'),
    ('parking',            'Underground parking available for 200 vehicles',       'facilities'),
    ('cafeteria',          'Ground floor cafeteria, open 7 AM to 9 PM',            'facilities'),
    ('atm',                'SBI ATM at Ground Floor lobby',                         'facilities'),
    ('blood_bank',         'Blood bank on Floor 0, open 24 hours',                 'facilities'),
    ('lab',                'Pathology & Radiology lab on Floor 1, Room 120',        'facilities'),
    ('billing',            'Billing counter at Ground Floor, Counter 5-6',          'facilities')
ON CONFLICT (info_key) DO UPDATE SET info_value = EXCLUDED.info_value,
                                     category   = EXCLUDED.category,
                                     updated_at = NOW();
