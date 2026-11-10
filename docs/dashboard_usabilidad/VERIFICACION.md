# Dashboard: desplazamiento, flexibilidad y usabilidad

Revisión del 4 de noviembre de 2026. Se modificaron únicamente el CSS y el componente JavaScript del panel de `fleet_rutas`. Se conservaron las acciones existentes, los modelos, los datos, `.env`, el dashboard de Grafana y sus ajustes.

## Problema y solución

Odoo 16 establece `overflow:hidden` y oculta las barras en el contenedor `.o_action` de escritorio. El dashboard heredaba esas reglas: parte del contenido quedaba fuera del área visible sin un desplazamiento accesible.

Ahora el panel dispone de un área interior `.fleet_viewport.o_content` que puede reducirse dentro del contenedor de Odoo y desplazarse verticalmente. La tabla mantiene su propio desplazamiento horizontal, sin ensanchar toda la página. Los textos extensos de vehículos se ajustan dentro de las celdas y tienen color explícito de alto contraste.

## Controles añadidos

- Deslizador de tamaño de texto entre 100% y 140%, operable mediante teclado.
- Vista compacta que reduce espacios conservando la información.
- Pausa y reanudación de la actualización automática; actualización manual disponible.
- Búsqueda por ruta, vehículo o nombre del recorrido sin sensibilidad a tildes.
- Estado de búsqueda sin coincidencias y opción para limpiar.
- Botón para restablecer la vista.
- Preferencias guardadas solamente en este navegador: tamaño, densidad y actualización. La búsqueda no se guarda.
- Acceso por teclado, enlace para saltar a los recorridos, etiquetas de campos y foco visible.
- Errores recuperables con reintento y conservación del último resultado recibido.

La búsqueda filtra los recorridos que ya muestra el panel; «Ver todos» abre la consulta completa de Odoo. El componente evita peticiones simultáneas y elimina su temporizador al salir de la vista.

## Validación realizada

Se utilizó Chrome en modo headless con un perfil temporal, Owl real de Odoo 16 y el CSS backend compilado por la instalación activa. Los datos de las capturas son **sintéticos de prueba** y las peticiones RPC se simularon. No se utilizaron sesiones personales ni se crearon recorridos, incidencias o posiciones de negocio.

| Prueba | Resultado |
|---|---|
| Anchos 320, 360, 390, 768, 1024, 1440 y 1920 px | Sin desbordamiento horizontal de la página; pie del panel alcanzable mediante scroll |
| Pantallas 844×390 y 1280×256 px | Todo el contenido sigue siendo alcanzable |
| Texto 140% en móvil y ancho 320 px | Sin desbordamiento horizontal de página |
| Tabla con diez nombres extensos | Ajuste de celdas y desplazamiento horizontal independiente cuando es necesario |
| Deslizador por teclado | Home/End nativos; probado End hasta 140% |
| Búsqueda | «intercampus» encuentra «Intercampús»; limpiar restaura los diez registros de prueba |
| Actualización automática | Pausar evita nuevas llamadas; reanudar restablece el intervalo de 30 s; actualizar manualmente funciona |
| Petición pendiente | No se inicia otra petición hasta terminar la primera |
| Fallo RPC | Se conservan los datos y funciona Reintentar |
| Salida del panel | El temporizador deja de efectuar llamadas |
| Acceso rápido por teclado | Enfoca los recorridos sin cambiar el hash de navegación de Odoo |
| JavaScript en navegador | Sin excepciones no controladas |
| Sintaxis y estructura | JavaScript y las dos plantillas OWL válidos; verificación estática del proyecto aprobada |

Contraste medido en las cinco muestras:

| Elemento | Relación de contraste |
|---|---:|
| Descripciones de indicadores | 9.08:1 |
| Nombre del vehículo | 13.53:1 |
| Texto secundario de la ruta | 9.50:1 |
| Resultado de búsqueda | 9.50:1 |
| Botón de actualización | 9.22:1 |

Evidencia completa: [resultados_navegador.json](resultados_navegador.json). Capturas de prueba: [escritorio](dashboard_1440.png), [móvil](dashboard_390.png) y [móvil con texto al 140%](dashboard_movil_texto_140.png).

## Relación con calidad y accesibilidad

[ISO/IEC 25010:2023](https://www.iso.org/standard/78176.html) ofrece un modelo para especificar, medir y evaluar propiedades de calidad. Esta mejora aporta evidencia parcial sobre la interacción y la flexibilidad del panel; no constituye una certificación ni acredita todas las características del producto.

| Aspecto evaluado | Mejora y evidencia |
|---|---|
| Operación y comprensión de la interfaz | Controles con nombres, búsqueda, restablecer, estados de carga/error y navegación conservada |
| Adaptación a distintos contextos de uso | Nueve tamaños de ventana, texto ajustable y densidad compacta |
| Accesibilidad de interacción | Controles nativos, foco visible, etiquetas, estado legible y regiones desplazables con teclado |
| Robustez de la interfaz | Últimos datos conservados ante error, reintento, protección frente a llamadas superpuestas y limpieza del temporizador |
| Compatibilidad con otras funciones | Selectores limitados al panel; Grafana conserva sus archivos y responde HTTP 200 |

Para criterios verificables de accesibilidad se tomaron como referencia las explicaciones de W3C sobre [reflujo a 320 píxeles CSS](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) y [contraste mínimo de 4.5:1 para texto normal](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html). Estas pruebas puntuales no equivalen a una auditoría integral WCAG ni a una evaluación formal completa de ISO/IEC 25010. Quedan pendientes lectores de pantalla, dispositivos físicos y evaluación de tareas con usuarios.

## Aplicación sin eliminar versiones anteriores

Los bundles nuevos se generaron mediante `scripts/actualizar_assets_dashboard.py`, suprimiendo la limpieza de assets antiguos únicamente durante esa generación. Se conservaron los tres assets existentes (IDs 268, 270 y 271) y se añadieron las nuevas versiones CSS/JS. Los conteos de negocio permanecieron iguales antes y después: 7 vehículos, 3 rutas, 12 paradas, 2 recorridos, 0 posiciones, 1 incidencia y 0 métricas.

Se reinició únicamente Odoo para cargar las referencias nuevas. Odoo, el CSS, el JavaScript y la salud de Grafana respondieron HTTP 200. No se actualizaron módulos ni se migró la base.

Si el navegador conserva la apariencia anterior, recargar con **Ctrl+F5**. Las preferencias pueden volver a su estado inicial mediante «Restablecer vista».

## Reproducción de las pruebas

```powershell
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe scripts/verificar_dashboard_navegador.py --css-url /web/assets/275-9f60a75/web.assets_backend.min.css --compiled-only
node --check addons/fleet_rutas/static/src/js/fleet_dashboard.js
python scripts/verificar_fuentes.py
```

La URL del bundle cambia si se vuelven a generar assets; utilizar la correspondiente a la instalación. Las capturas adjuntas muestran el componente aislado con estilos compilados reales, no el estado operativo de la flota.
