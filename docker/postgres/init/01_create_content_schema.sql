CREATE SCHEMA IF NOT EXISTS content;

ALTER ROLE oss_user IN DATABASE oss_db SET search_path TO content, public;
