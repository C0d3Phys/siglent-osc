# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). El proyecto
está en fase alpha; los números de versión pueden reorganizarse hasta la primera publicación
estable.

## [Sin publicar]

### Agregado

- Barra de herramientas con íconos y tooltips para las acciones más usadas (abrir, guardar
  imagen, cursores X/Y, Auto Y, zoom a región, vista completa, canal matemático, FFT).
- Arrastrar y soltar archivos `.csv`, `.bin` o `.lwf` sobre la ventana principal.
- Menú `Archivo → Abrir reciente` con los últimos 8 archivos, persistente entre sesiones
  mediante `QSettings` y filtrado automático de rutas que ya no existen.
- Resumen permanente de la adquisición activa (archivo, muestras, duración, tasa, canales
  activos/total y memoria estimada), actualizado al importar y al mostrar u ocultar canales.
- Atajos de teclado adicionales: `Ctrl+1/2/3` (paneles), `Ctrl+4/5` (cursores X/Y), `Ctrl+F`
  (FFT), `Ctrl+M` (canal matemático), `Ctrl+R` (zoom a región), `Ctrl+0` (vista completa),
  `Ctrl+Y` (Auto Y).
- Módulos puros `osc_app.core.file_support`, `osc_app.core.recent_files` y
  `osc_app.core.status_summary`, con sus respectivas pruebas unitarias.
- Suite de pruebas de interfaz (`tests/test_main_window_ui.py`) usando Qt en modo
  `offscreen`, más `tests/conftest.py` para configurarlo por defecto.

### Cambiado

- Los tres paneles (Canales, Herramientas, Estadísticas) ahora se muestran automáticamente
  al importar una adquisición.
- El resumen bajo la gráfica pasó de mostrar solo el total de canales a mostrar
  canales activos sobre el total, y añadió la memoria estimada de las muestras crudas.
- Los íconos de la barra de herramientas dejaron de usar los íconos nativos del sistema
  operativo (inconsistentes y anticuados) y ahora son un set propio de íconos planos
  dibujados por código, que se adaptan al color de texto del tema activo.
- La barra de herramientas ahora se puede ocultar desde `Opciones → Barra de herramientas`
  o con clic derecho sobre ella.
- El panel de canales pasó de una tabla de 5 columnas a una tarjeta por canal (borde del
  color del canal, sonda y offset en la misma fila), eliminando el desbordamiento horizontal
  que cortaba el botón `Solo` y el control de offset.
- El offset visual por canal bajó de 6 a 3 decimales para acortar el control sin perder
  utilidad práctica (es un ajuste puramente visual, no una medición).

Ver [docs/ui-improvements.md](docs/ui-improvements.md) para el detalle de diseño y las
decisiones de alcance de esta tanda.

## [0.2.0]

Última versión etiquetada antes de este registro. Ver
[Releases](https://github.com/C0d3Phys/siglent-osc/releases) para el ejecutable de Windows.
