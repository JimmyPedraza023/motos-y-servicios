-- Migration 003: restricción UNIQUE para upsert de lead_asignaciones
-- Un lead solo puede tener una asignación activa por run
ALTER TABLE lead_asignaciones
ADD CONSTRAINT uq_lead_asignacion_run UNIQUE (lead_id, pipeline_run_id);