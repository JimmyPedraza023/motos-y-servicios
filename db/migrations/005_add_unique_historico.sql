ALTER TABLE historico_cierres
    ADD CONSTRAINT uq_historico_cierres_id
    UNIQUE (historico_id);