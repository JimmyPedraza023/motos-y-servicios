-- Migration 002: restricción UNIQUE para upsert de lead_scores
-- Permite re-ejecutar el pipeline sin duplicar scores del mismo run
ALTER TABLE lead_scores
ADD CONSTRAINT uq_lead_run UNIQUE (lead_id, pipeline_run_id);