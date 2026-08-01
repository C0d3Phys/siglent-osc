# OSC App — Plan de desarrollo del MVP

**Referencia funcional:** `mvp-specification.md`  
**Método:** entregas pequeñas, ejecutables y verificables  
**Unidad de avance:** una etapa termina únicamente cuando cumple sus pruebas y condición de salida

## 1. Principios de ejecución

- Validar CSV reales antes de generalizar el importador.
- Mantener los datos originales inmutables.
- Separar núcleo, tareas e interfaz desde el inicio.
- Medir rendimiento con conjuntos reproducibles.
- No comenzar FFT, filtros o análisis automotriz antes de aceptar el MVP.
- Mantener siempre una aplicación ejecutable al cerrar una etapa.

## 2. Entregables

| Etapa | Resultado ejecutable | Dependencia |
|---|---|---|
| 0 | Proyecto preparado y aplicación vacía iniciable | Ninguna |
| 1 | Catálogo de CSV y contrato del importador | CSV reales |
| 2 | Núcleo capaz de importar y validar adquisiciones | Etapa 1 |
| 3 | Visor de uno y varios canales | Etapa 2 |
| 4 | Cursores, región y estadísticas | Etapa 3 |
| 5 | Exportación, proyectos y referencias | Etapa 4 |
| 6 | Rendimiento, estabilidad y empaquetado | Etapas 2–5 |
| 7 | Aceptación del MVP y backlog de V1 | Etapa 6 |

## 3. Etapa 0 — Base del proyecto

### Trabajo

- Inicializar control de versiones.
- Crear `pyproject.toml` para Python 3.12+.
- Crear paquetes `app`, `core` y `tests`.
- Añadir PySide6, PyQtGraph, NumPy y pytest.
- Configurar ruff y pyright o mypy.
- Crear una ventana mínima y un punto de entrada.
- Añadir pruebas de arranque e importación de paquetes.
- Documentar instalación y ejecución.

### Salida

- La aplicación abre una ventana en Windows.
- Las comprobaciones de estilo, tipos y pruebas pasan con un solo flujo documentado.
- No existe lógica de negocio dentro de widgets.

## 4. Etapa 1 — Descubrimiento del CSV real

### Trabajo

- Recopilar las capturas indicadas en la especificación del MVP.
- Crear un inventario sin incluir datos privados innecesarios.
- Identificar codificación, delimitador, metadatos, encabezados y variantes.
- Comparar valores visibles en el osciloscopio con el archivo.
- Definir sinónimos reales para tiempo y canales.
- Convertir ejemplos pequeños en fixtures versionables.
- Registrar casos todavía no soportados.

### Decisión necesaria

Congelar la primera versión de `ImportProposal`, `ImportRequest`, `ImportResult` e `ImportReport` solo después de revisar las muestras reales.

### Salida

- Existe una matriz de formatos y al menos un fixture por variante aprobada.
- Cada fixture tiene resultado esperado.
- Las ambigüedades que requieren intervención del usuario están enumeradas.

## 5. Etapa 2 — Modelo e importación

### Incremento 2.1: modelo

- Implementar adquisición, canales y ejes temporal uniforme y explícito.
- Garantizar inmutabilidad mediante API y pruebas.
- Implementar estimación de memoria.

### Incremento 2.2: inspección

- Detectar codificación y delimitador sobre una muestra.
- Encontrar metadatos, encabezado y columnas candidatas.
- Producir una propuesta sin cargar todo el archivo.

### Incremento 2.3: carga

- Leer por bloques.
- Convertir tiempo y muestras.
- Aplicar reglas de filas inválidas.
- Validar monotonicidad y uniformidad.
- Crear el informe de importación.
- Añadir progreso y cancelación independientes de Qt.

### Incremento 2.4: interfaz de importación

- Selector de archivo.
- Diálogo de mapeo cuando sea necesario.
- Progreso, cancelación y errores accionables.

### Salida

- Todos los fixtures aprobados se importan con los resultados esperados.
- Una importación cancelada no deja un modelo parcial activo.
- La interfaz no se bloquea durante un archivo grande.

## 6. Etapa 3 — Visualización multicanal

### Incremento 3.1: gráfica básica

- Mostrar un canal con ejes y unidades.
- Implementar zoom, desplazamiento, autoescala y restablecimiento.

### Incremento 3.2: varios canales

- Mostrar hasta cuatro canales.
- Activar, ocultar, renombrar y colorear canales.
- Añadir modo superpuesto.

### Incremento 3.3: grandes volúmenes

- Añadir downsampling min/máx que preserve picos.
- Limitar copias y caché.
- Añadir navegador inferior.
- Medir latencia y memoria con 1, 7 y 28 millones de muestras.

### Salida

- Al ampliar se recuperan los puntos reales del rango.
- Picos sintéticos aislados permanecen visibles en vista reducida.
- Las métricas de rendimiento quedan registradas con el equipo usado.

## 7. Etapa 4 — Cursores, regiones y estadísticas

### Trabajo

- Implementar `X1`, `X2` y ajuste a muestra.
- Mostrar índice, tiempo, valores, diferencias y frecuencia equivalente.
- Implementar selección de región inclusiva.
- Calcular mínimo, máximo, media, RMS y pico a pico en segundo plano cuando corresponda.
- Mostrar muestras totales, válidas y omitidas.
- Añadir pruebas con regiones vacías, invertidas, de un punto y con `NaN`.

### Salida

- Los resultados coinciden con NumPy dentro de la tolerancia de cada prueba.
- Mover cursores no recalcula ni copia la adquisición completa.
- Cambiar rápidamente la región no muestra resultados antiguos.

## 8. Etapa 5 — Exportación, proyectos y referencias

### Incremento 5.1: exportación

- Exportar tiempo y canales visibles de la región.
- Añadir metadatos y unidades.
- Confirmar sobrescrituras.
- Probar la reimportación del archivo generado.

### Incremento 5.2: proyectos

- Definir esquema JSON con número de versión.
- Guardar referencia, huella y configuración visual.
- Reabrir y validar la fuente.
- Permitir relocalizar un CSV movido.
- Manejar versiones desconocidas y archivos dañados.

### Incremento 5.3: imágenes y BIN de referencia

- Definir el modelo de referencias y sus relaciones con una adquisición.
- Permitir elegir entre archivo vinculado e integrado.
- Calcular y validar la huella SHA-256.
- Mostrar imágenes con miniatura, zoom y descripción.
- Mostrar BIN como referencia documental sin intentar decodificarlo.
- Incorporar un contenedor ZIP para proyectos con adjuntos integrados.
- Advertir el tamaño final antes de integrar archivos grandes.
- Permitir relocalizar referencias enlazadas.
- Permitir retirar una referencia sin borrar el archivo original.
- Verificar que los bytes de un BIN integrado sean idénticos al recuperarlo.

### Salida

- Un proyecto conserva mapeos, canales, cursores y región.
- Un proyecto conserva imágenes y BIN vinculados o integrados con sus notas.
- La adquisición recargada corresponde al mismo archivo o avisa de la diferencia.
- Una referencia ausente o modificada se detecta mediante su huella.
- Exportar nunca altera las muestras originales.

## 9. Etapa 6 — Consolidación y distribución

### Rendimiento

- Crear un comando reproducible de benchmark.
- Medir importación, pico de RAM, primera gráfica, zoom, estadísticas y cancelación.
- Optimizar únicamente después de perfilar.
- Documentar objetivos cumplidos y desviaciones.

### Estabilidad

- Probar archivos truncados, vacíos, enormes y con valores inválidos.
- Probar rutas largas, caracteres Unicode y archivos de solo lectura.
- Probar imágenes dañadas y BIN grandes, ausentes o modificados.
- Ejecutar pruebas prolongadas de navegación y reapertura.
- Revisar liberación de memoria al cerrar una adquisición.

### Distribución

- Generar inicialmente un paquete con PyInstaller.
- Probarlo en una máquina Windows limpia o entorno equivalente.
- Incluir versión, licencias de dependencias y registro diagnóstico.
- Documentar instalación, uso y desinstalación.

### Salida

- El paquete se inicia sin un entorno Python instalado.
- La suite y la lista de comprobación manual pasan.
- Las métricas finales están adjuntas a la entrega.

## 10. Etapa 7 — Aceptación del MVP

Realizar una sesión con al menos:

1. CSV real de un canal;
2. CSV real de cuatro canales;
3. captura grande;
4. formato ambiguo que solicite mapeo;
5. guardado y reapertura de proyecto;
6. imagen de referencia vinculada e integrada;
7. BIN de referencia vinculado e integrado, validado byte por byte;
8. exportación de una región;
9. cancelación de una operación.

Registrar cada resultado como aprobado, rechazado o aprobado con observación. Los defectos que impidan los diez criterios de aceptación bloquean el cierre; las mejoras fuera de alcance pasan al backlog.

## 11. Backlog posterior al MVP

Orden recomendado:

1. canales matemáticos con analizador seguro de expresiones;
2. filtros y procesamiento reproducible;
3. FFT con convenciones numéricas documentadas;
4. calibración y sistema de unidades;
5. contenedor de proyecto con datos opcionales;
6. tiempo a grados mediante referencias manuales;
7. presión de cilindro y superposición de ciclos;
8. CKP/CMP y remuestreo angular;
9. lector BIN validado contra pares BIN/CSV;
10. adquisición SCPI.

Cada elemento posterior deberá tener su propia especificación y criterios de aceptación antes de implementarse.

## 12. Riesgos y controles

| Riesgo | Consecuencia | Control |
|---|---|---|
| CSV reales distintos a los ejemplos | Importador frágil | Etapa de descubrimiento y fixtures |
| Cargar el archivo completo varias veces | Exceso de RAM | Lectura por bloques, perfilado y límites de copia |
| Downsampling que oculta picos | Interpretación incorrecta | Agregación min/máx y señales sintéticas |
| Cálculos en el hilo visual | Interfaz congelada | Cola de tareas con progreso y cancelación |
| Resultados tardíos de una selección anterior | Datos incoherentes en pantalla | Identificadores de tarea y descarte de resultados obsoletos |
| Proyecto enlazado a un CSV modificado | Resultados no reproducibles | Tamaño, huella, validación y relocalización |
| BIN integrado demasiado grande | Proyecto difícil de mover o guardar | Mostrar tamaño, ofrecer vínculo y copiar por bloques |
| Referencia vinculada movida o alterada | Comparación equivocada | Huella SHA-256, estado visible y relocalización explícita |
| Crecimiento prematuro del alcance | MVP interminable | Criterios de salida y backlog separado |
| Suposición incorrecta sobre ADC | Recomendación técnica falsa | No implementarla hasta validación documental o experimental |

## 13. Definición de terminado por incremento

Un incremento está terminado cuando:

- cumple el comportamiento descrito;
- incluye pruebas automatizadas relevantes;
- no introduce fallos en pruebas existentes;
- informa errores de forma accionable;
- no bloquea la interfaz en tareas largas;
- actualiza la documentación de usuario o técnica necesaria;
- puede demostrarse desde una compilación limpia;
- no deja decisiones críticas escondidas en comentarios o valores mágicos.

## 14. Primera acción concreta

Solicitar y catalogar los CSV reales. Mientras se obtienen, completar únicamente la Etapa 0 y generar datos sintéticos para desarrollar el modelo, las estadísticas y las mediciones de rendimiento. La detección definitiva del formato no debe basarse solo en ejemplos inventados.
