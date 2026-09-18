ALTER TABLE lead_asignaciones DROP CONSTRAINT uq_lead_asignacion_run;
TRUNCATE TABLE lead_asignaciones;
ALTER TABLE lead_asignaciones
ADD CONSTRAINT uq_lead_asignacion_lead UNIQUE (lead_id);