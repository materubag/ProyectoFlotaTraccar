-- =============================================================================
-- VISTAS MATERIALIZADAS PARA POWER BI Y ANALÍTICA ESPACIAL AVANZADA
-- Sistema de Monitoreo y Evaluación de Rutas de Transporte Universitario
-- Norma de Referencia: ISO/IEC 25010 (SQuaRE)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. VISTA MATERIALIZADA: Rendimiento de Operación y Puntualidad por Recorrido
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_bi_recorridos_rendimiento AS
SELECT 
    rec.id AS recorrido_id,
    rec.name AS recorrido_nombre,
    rec.estado AS estado_recorrido,
    rec.fecha_inicio AS fecha_programada,
    rec.fecha_inicio_real,
    rec.fecha_fin_real,
    rec.duracion_real_min,
    rec.retraso_inicio_min,
    rec.distancia_real_km,
    rec.velocidad_promedio_real,
    rec.porcentaje_paradas_cumplidas,
    rec.tiene_desviacion,
    r.id AS ruta_id,
    r.code AS ruta_codigo,
    r.name AS ruta_nombre,
    r.origen AS ruta_origen,
    r.destino AS ruta_destino,
    r.distancia_estimada_km AS ruta_distancia_estimada,
    v.id AS vehiculo_id,
    v.license_plate AS placa_vehiculo,
    v.traccar_device_id,
    u.id AS conductor_id,
    u.login AS conductor_usuario,
    -- Métricas calculadas asociadas
    COALESCE(m.pct_cumplimiento_ruta, 0.0) AS pct_cumplimiento_ruta,
    COALESCE(m.pct_puntualidad, 0.0) AS pct_puntualidad,
    COALESCE(m.retraso_promedio_min, 0.0) AS retraso_promedio_min,
    COALESCE(m.integridad_gps_pct, 100.0) AS integridad_gps_pct,
    COALESCE(m.frecuencia_incidencias, 0.0) AS frecuencia_incidencias
FROM fleet_recorrido rec
INNER JOIN fleet_ruta r ON rec.ruta_id = r.id
INNER JOIN fleet_vehicle v ON rec.vehicle_id = v.id
LEFT JOIN res_users u ON rec.conductor_id = u.id
LEFT JOIN fleet_metricas_recorrido m ON m.recorrido_id = rec.id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_bi_recorridos_id ON mv_bi_recorridos_rendimiento (recorrido_id);
CREATE INDEX IF NOT EXISTS idx_mv_bi_recorridos_ruta ON mv_bi_recorridos_rendimiento (ruta_id, fecha_programada);

-- -----------------------------------------------------------------------------
-- 2. VISTA MATERIALIZADA: Cumplimiento Espacial y Horario de Paradas
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_bi_paradas_auditoria AS
SELECT 
    cp.id AS cumplimiento_id,
    rec.id AS recorrido_id,
    rec.name AS recorrido_nombre,
    r.id AS ruta_id,
    r.name AS ruta_nombre,
    p.id AS parada_id,
    p.name AS parada_nombre,
    p.secuencia AS parada_secuencia,
    p.tipo AS parada_tipo,
    p.latitud AS parada_latitud,
    p.longitud AS parada_longitud,
    p.radio_proximidad_m AS parada_radio_m,
    p.hora_prevista AS parada_hora_prevista,
    p.tolerancia_min AS tolerancia_min,
    cp.cumplida AS parada_cumplida,
    cp.timestamp_llegada AS hora_real_llegada,
    cp.retraso_min AS minutos_retraso,
    cp.distancia_minima_m AS distancia_minima_alcanzada,
    CASE 
        WHEN NOT cp.cumplida THEN 'Omitida'
        WHEN cp.retraso_min > p.tolerancia_min THEN 'Retrasada'
        WHEN cp.retraso_min < -p.tolerancia_min THEN 'Adelantada'
        ELSE 'Puntual'
    END AS clasificacion_puntualidad
FROM fleet_cumplimiento_parada cp
INNER JOIN fleet_recorrido rec ON cp.recorrido_id = rec.id
INNER JOIN fleet_parada p ON cp.parada_id = p.id
INNER JOIN fleet_ruta r ON rec.ruta_id = r.id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_bi_paradas_id ON mv_bi_paradas_auditoria (cumplimiento_id);
CREATE INDEX IF NOT EXISTS idx_mv_bi_paradas_rec ON mv_bi_paradas_auditoria (recorrido_id, parada_id);

-- -----------------------------------------------------------------------------
-- 3. VISTA MATERIALIZADA: Historial GPS y Desviaciones Espaciales (Mapas Power BI)
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_bi_telemetria_espacial AS
SELECT 
    gps.id AS posicion_id,
    gps.recorrido_id,
    gps.vehicle_id,
    v.license_plate AS placa_vehiculo,
    rec.ruta_id,
    r.name AS ruta_nombre,
    gps.timestamp AS fecha_hora_gps,
    gps.latitud,
    gps.longitud,
    gps.velocidad_kmh,
    gps.altitud_m,
    gps.precision_m,
    gps.es_desviacion,
    gps.distancia_ruta_m,
    gps.fuente
FROM fleet_posicion_gps gps
INNER JOIN fleet_vehicle v ON gps.vehicle_id = v.id
LEFT JOIN fleet_recorrido rec ON gps.recorrido_id = rec.id
LEFT JOIN fleet_ruta r ON rec.ruta_id = r.id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_bi_telemetria_id ON mv_bi_telemetria_espacial (posicion_id);
CREATE INDEX IF NOT EXISTS idx_mv_bi_telemetria_rec ON mv_bi_telemetria_espacial (recorrido_id, fecha_hora_gps);

-- -----------------------------------------------------------------------------
-- 4. VISTA MATERIALIZADA: Matriz de Incidencias Operativas
-- -----------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_bi_incidencias_analisis AS
SELECT 
    inc.id AS incidencia_id,
    inc.recorrido_id,
    rec.ruta_id,
    r.name AS ruta_nombre,
    v.license_plate AS placa_vehiculo,
    inc.tipo AS tipo_incidencia,
    inc.severidad,
    inc.timestamp AS fecha_incidencia,
    inc.latitud,
    inc.longitud,
    inc.valor_detectado,
    inc.valor_esperado,
    inc.unidad,
    inc.resuelta,
    inc.descripcion
FROM fleet_incidencia inc
LEFT JOIN fleet_recorrido rec ON inc.recorrido_id = rec.id
LEFT JOIN fleet_ruta r ON rec.ruta_id = r.id
LEFT JOIN fleet_vehicle v ON rec.vehicle_id = v.id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_bi_incidencias_id ON mv_bi_incidencias_analisis (incidencia_id);
CREATE INDEX IF NOT EXISTS idx_mv_bi_incidencias_tipo ON mv_bi_incidencias_analisis (tipo_incidencia, severidad);

-- -----------------------------------------------------------------------------
-- 5. FUNCIÓN Y PROCEDIMIENTO PARA REFRESCAR VISTAS MATERIALIZADAS
-- -----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_refrescar_vistas_analitica_flota()
LANGUAGE plpgsql
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_bi_recorridos_rendimiento;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_bi_paradas_auditoria;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_bi_telemetria_espacial;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_bi_incidencias_analisis;
END;
$$;

