-- BMS CDC example schema for MySQL.
-- Run this script against the database configured by BMS_DB_NAME.

CREATE DATABASE IF NOT EXISTS bms_database;
USE bms_database;

CREATE TABLE IF NOT EXISTS alarms (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sensor_number VARCHAR(100) NOT NULL,
    time DATETIME(6) NOT NULL,
    value DECIMAL(20, 6) NOT NULL,
    trend VARCHAR(32) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    INDEX idx_alarms_sensor_time (sensor_number, time)
) ENGINE = InnoDB;

-- Insert one test alarm. This INSERT should be captured by the CDC listener
-- when MySQL row-based binary logging is enabled.
INSERT INTO alarms (sensor_number, time, value, trend)
VALUES ('BMS-101', '2026-09-23 13:30:00', 24.5, 'high');
