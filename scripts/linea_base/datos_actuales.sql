-- Solo lectura sobre la base del proyecto.
BEGIN READ ONLY;
SELECT json_build_object(
 'modulos', (SELECT json_object_agg(name, state || ' ' || coalesce(latest_version, '')) FROM ir_module_module WHERE name IN ('portal','fleet_rutas','fleet_traccar','fleet_reports')),
 'vehiculos', (SELECT count(*) FROM fleet_vehicle),
 'rutas', (SELECT count(*) FROM fleet_ruta),
 'paradas', (SELECT count(*) FROM fleet_parada),
 'recorridos', (SELECT json_agg(x) FROM (SELECT estado, simulado, count(*) AS n FROM fleet_recorrido GROUP BY 1,2 ORDER BY 1) x),
 'posiciones', (SELECT json_agg(x) FROM (SELECT fuente, count(*) AS n, count(payload_origen) AS con_snapshot, count(recorrido_id) AS con_recorrido FROM fleet_posicion_gps GROUP BY 1 ORDER BY 1) x),
 'ids_traccar_duplicados', (SELECT count(*) FROM (SELECT traccar_position_id FROM fleet_posicion_gps WHERE traccar_position_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1) d),
 'incidencias', (SELECT json_object_agg(tipo, n) FROM (SELECT tipo, count(*) n FROM fleet_incidencia GROUP BY 1) x),
 'incidencias_validadas', (SELECT count(*) FROM fleet_incidencia WHERE validacion <> 'pendiente'),
 'metricas', (SELECT row_to_json(x) FROM (SELECT count(*) AS n,
    count(*) FILTER (WHERE NOT coalesce(r.simulado,false)) AS n_reales,
    round(avg(pct_cumplimiento_ruta)::numeric,2) AS cumplimiento,
    round(avg(pct_puntualidad)::numeric,2) AS puntualidad,
    round(avg(retraso_promedio_min)::numeric,2) AS retraso_min,
    round(avg(pct_paradas_cumplidas)::numeric,2) AS paradas,
    round(avg(pct_desviacion_ruta)::numeric,2) AS desviacion,
    round(avg(diferencia_distancia_km)::numeric,3) AS dif_distancia_km,
    round(avg(m.duracion_real_min)::numeric,2) AS duracion_min,
    round(avg(frecuencia_incidencias)::numeric,2) AS incidencias_h,
    round(avg(integridad_gps_pct)::numeric,2) AS integridad,
    count(*) FILTER (WHERE calidad_sync_disponible) AS con_exactitud,
    count(*) FILTER (WHERE deteccion_validada) AS con_deteccion
    FROM fleet_metricas_recorrido m JOIN fleet_recorrido r ON r.id = m.recorrido_id) x),
 'sync', (SELECT json_object_agg(estado, n) FROM (SELECT estado, count(*) n FROM fleet_traccar_sync GROUP BY 1) x),
 'paradas_rutas', (SELECT json_agg(x) FROM (SELECT r.name AS ruta, r.distancia_estimada_km AS estimada_km, json_agg(json_build_array(p.latitud, p.longitud) ORDER BY p.secuencia, p.id) AS puntos FROM fleet_ruta r JOIN fleet_parada p ON p.ruta_id = r.id GROUP BY r.id ORDER BY r.id) x)
);
COMMIT;
