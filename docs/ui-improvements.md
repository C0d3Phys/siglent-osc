# Mejoras de interfaz — primera tanda

Este documento registra el primer paquete de mejoras de interfaz de OSC App: qué se
implementó, por qué, y qué se dejó fuera deliberadamente para una siguiente iteración.

## Motivación

Una revisión de `main_window.py` y de los documentos de producto identificó que la
funcionalidad de análisis estaba muy por delante de la usabilidad de la interfaz: todo vivía
en menús de texto, los paneles clave arrancaban ocultos, no existían atajos más allá de
`Ctrl+O`/`Ctrl+S`, no había arrastrar y soltar ni lista de archivos recientes, y el resumen de
la adquisición activa no informaba canales activos ni memoria usada.

## Cambios implementados

### Barra de herramientas

`MainWindow._build_toolbar()` agrega una `QToolBar` fija con íconos estándar de Qt y
tooltips para las acciones más frecuentes: abrir adquisición, guardar imagen, cursores X1/X2
y Y1/Y2, Auto Y, zoom a región, vista completa, crear canal matemático y analizador FFT. Las
mismas `QAction` se comparten entre menú y barra, así que el estado (marcado/activo) se
mantiene sincronizado automáticamente.

### Panel de canales visible tras importar

`open_file()` ahora llama a `_set_channel_panel_visible(True)` al terminar una importación
exitosa. El panel sigue pudiéndose ocultar manualmente; solo cambia el punto de partida.

### Atajos de teclado adicionales

Se añadieron atajos a acciones ya existentes en los menús (no se crearon acciones nuevas):
`Ctrl+1/2/3` para los paneles de canales, herramientas y estadísticas; `Ctrl+4/5` para
cursores X1/X2 y Y1/Y2; `Ctrl+F` para el analizador FFT; `Ctrl+M` para crear un canal
matemático; `Ctrl+R` para zoom a región; `Ctrl+0` para vista completa; `Ctrl+Y` para Auto Y.

### Arrastrar y soltar

`MainWindow.setAcceptDrops(True)` más `dragEnterEvent`/`dropEvent` aceptan archivos
`.csv`, `.bin` o `.lwf` soltados sobre la ventana y los abren con `open_file()`. El filtro de
extensión vive en `osc_app.core.file_support.is_supported_acquisition_file`, una función pura
sin dependencias de Qt, para poder probarla sin levantar una aplicación gráfica.

### Archivos recientes

`Archivo → Abrir reciente` guarda hasta 8 rutas mediante `QSettings`, con la más reciente
primero y sin duplicados. La lógica de orden y deduplicación vive en
`osc_app.core.recent_files.push_recent_file` (pura, testable). Al desplegar el menú se filtran
las rutas que ya no existen en disco (`filter_existing_paths`).

### Resumen permanente de estado

La etiqueta bajo la gráfica (`self.info`), que ya era persistente, ahora se construye con
`osc_app.core.status_summary.build_status_summary` e incluye archivo, muestras, duración,
tasa de muestreo, canales activos sobre el total y memoria estimada de las muestras crudas.
Se actualiza al importar y al mostrar/ocultar cualquier canal
(`_set_channel_visible` → `_refresh_status_summary`).

## Decisiones de alcance

Se evaluaron pero **no** se implementaron en esta tanda, por ser cambios arquitectónicos de
mayor riesgo que merecen su propio ciclo de diseño y pruebas:

- **Deshacer/rehacer.** Ya está pedido en `product-specification.md` (sección 23) pero
  requiere un historial de operaciones que hoy no existe; tocar esto a la vez que la
  interfaz habría mezclado dos refactors grandes en un solo cambio.
- **Modo de trabajo por pestañas** (Osciloscopio / Automotriz / Espectro / Serial). Implica
  reorganizar cómo conviven los diálogos y paneles actuales; se prefiere planearlo aparte
  cuando se agreguen los módulos de CKP/CMP, inyector y bobina del roadmap.
- **Dividir `main_window.py`** en los módulos que ya sugiere
  `docs/analysis-tools-roadmap.md` (sección 10). Es un refactor de alto riesgo para un archivo
  de más de 2600 líneas; conviene hacerlo con su propia batería de pruebas de regresión antes
  de seguir agregando funciones.

## Segunda tanda — ajustes tras revisión visual

Tras revisar la primera tanda en la aplicación real, se reportaron tres problemas concretos
que esta segunda tanda corrige:

### Íconos del ribbon "anticuados" y sin opción de ocultarlo

Los íconos estándar de Qt (`QStyle.StandardPixmap`) dependen del tema nativo del sistema
operativo y se ven inconsistentes entre plataformas. Se reemplazaron por un set propio de
íconos planos y monocromos dibujados con `QPainter` en `osc_app/app/icons.py`
(`make_icon(nombre, color)`), con el mismo grosor de trazo para todos. El color se toma de
`QPalette.ColorRole.WindowText` de la ventana, así se adapta al tema claro u oscuro del
sistema en vez de quedar fijo.

Además, `toolbar.toggleViewAction()` se agregó al menú `Opciones` (justo después de
`Auto Y`) como "Barra de herramientas", así se puede ocultar o volver a mostrar. Qt también
habilita por defecto el clic derecho sobre la barra para el mismo efecto.

### Solo se abría el panel de canales

Se aclaró con el usuario que la expectativa era que los **tres** paneles (Canales,
Herramientas, Estadísticas) se abrieran automáticamente al importar, no solo el de canales.
`open_file()` ahora llama a `_set_channel_panel_visible`, `_set_cursor_panel_visible` y
`_set_statistics_panel_visible` con `True` tras una importación exitosa.

### Panel de canales apretado: Sonda y Offset se cortaban

El panel de canales usaba una `QTableWidget` de 5 columnas (Ver, Canal, Sonda, Offset,
Solo) dentro de un panel de ~300 px. Con controles cuyo `sizeHint` natural es amplio (el
offset permitía rango ±1e9 con 6 decimales), Qt terminaba mostrando una barra de scroll
horizontal y cortando el botón `Solo` y el spin de offset.

Se reemplazó la tabla por una tarjeta (`ChannelCard`, en `main_window.py`) por canal:
un `QFrame` con borde izquierdo de 4 px del color del canal (mismo color que su trazo en la
gráfica), con una fila de encabezado (casilla de visibilidad, nombre coloreado, botón
`Solo`) y una fila de controles (Sonda y Offset, ambos inline, con ancho máximo acotado).
El contenedor de tarjetas vive dentro de un `QScrollArea` con scroll horizontal
deshabilitado (`ScrollBarAlwaysOff`), así el contenido siempre se ajusta al ancho
disponible en vez de desbordarse. El offset visual bajó de 6 a 3 decimales (suficiente para
un ajuste puramente visual) para acortar el control.

Verificado visualmente generando capturas de la ventana en modo `offscreen`
(`QWidget.grab()`) durante el desarrollo: el panel ya no muestra scroll horizontal y todos
los controles quedan visibles.

## Pruebas

- `tests/test_file_support.py`, `tests/test_recent_files.py` y `tests/test_status_summary.py`
  cubren la lógica pura sin Qt.
- `tests/test_main_window_ui.py` instancia `MainWindow` con Qt en modo `offscreen`
  (configurado por `tests/conftest.py`) para comprobar que los tres paneles se muestran al
  importar, que cada canal genera una tarjeta con su color e índice correctos, que el
  resumen se actualiza, que los archivos recientes se guardan y filtran, que la barra de
  herramientas se puede ocultar desde el menú, y que el filtro de arrastrar y soltar acepta o
  rechaza extensiones correctamente. Cada prueba aísla `QSettings` en un archivo `.ini`
  temporal para no tocar la configuración real del usuario que ejecute las pruebas.

Ejecutar todo con:

```powershell
python -m pytest
ruff check .
```
