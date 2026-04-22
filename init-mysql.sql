-- Runs once on first MySQL boot via /docker-entrypoint-initdb.d/
-- Creates both app databases and grants the shared user access to both.
CREATE DATABASE IF NOT EXISTS ams_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS cms_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON ams_db.* TO 'admin'@'%';
GRANT ALL PRIVILEGES ON cms_db.* TO 'admin'@'%';
FLUSH PRIVILEGES;
