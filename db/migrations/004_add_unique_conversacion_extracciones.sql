-- Permite upsert por conversacion_id en conversacion_extracciones
ALTER TABLE conversacion_extracciones
    ADD CONSTRAINT uq_conversacion_extracciones_conv_id
    UNIQUE (conversacion_id);