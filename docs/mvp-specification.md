# OSC App — Especificación ejecutable del MVP CSV

**Estado:** propuesta de implementación  
**Documento fuente:** `product-specification.md`  
**Plataforma:** Windows 10/11  
**Python:** 3.12 o superior  
**Interfaz:** PySide6  
**Gráficas:** PyQtGraph  
**Cálculo:** NumPy  
**Pruebas:** pytest

## 1. Propósito

Construir una aplicación de escritorio que importe adquisiciones CSV del SIGLENT SDS1104X-E, conserve las muestras originales y permita examinarlas mediante una gráfica interactiva, cursores temporales, selección de regiones y estadísticas básicas.

Este MVP valida primero los formatos CSV reales, la exactitud del modelo de datos y el rendimiento gráfico. FFT, filtros, calibración, análisis CKP/CMP, presión de cilindro, BIN y SCPI quedan fuera de esta entrega.

## 2. Resultado esperado

Al finalizar, el usuario podrá:

1. abrir un CSV mediante un selector de archivos;
2. revisar y, si es necesario, corregir el mapeo de columnas;
3. ver uno o varios canales sobre un eje temporal;
4. ampliar, desplazar y restablecer la vista;
5. activar dos cursores temporales;
6. seleccionar una región;
7. obtener mínimo, máximo, media, RMS y pico a pico;
8. exportar la región seleccionada a CSV;
9. guardar un proyecto ligero y volver a abrirlo;
10. adjuntar imágenes o archivos BIN como referencias de la adquisición;
11. recibir mensajes comprensibles ante archivos incompatibles.

## 3. Alcance

### 3.1 Incluido

- CSV con uno a cuatro canales.
- Archivos con columna temporal explícita.
- Archivos sin tiempo cuando `sample_interval` o `sample_rate` esté disponible en metadatos o sea suministrado por el usuario.
- Delimitadores coma, punto y coma y tabulación.
- Números con punto decimal; coma decimal solo cuando no sea ambigua con el delimitador.
- Codificaciones UTF-8, UTF-8 con BOM y una codificación heredada detectable.
- Tiempo uniforme y tiempo explícito no uniforme.
- Datos originales inmutables.
- Downsampling únicamente visual.
- Trabajos largos en segundo plano, con progreso y cancelación.
- Registro de importación y errores.
- Imágenes de referencia PNG, JPEG, BMP o TIFF.
- Archivos BIN de referencia vinculados o integrados en el proyecto, sin decodificación.

### 3.2 Fuera del MVP

- BIN y adquisición directa por LAN/SCPI.
- Interpretación, graficación o conversión del contenido de un BIN.
- FFT, PSD, THD y armónicos.
- Filtros, derivada, integral y canales matemáticos.
- Calibración de sensores y conversión de unidades.
- Conversión tiempo–ángulo y módulos automotrices.
- Sistema dinámico de plugins.
- Generación de reportes PDF.
- Diagnóstico automático.

## 4. Reglas funcionales

### 4.1 Importación

El importador realizará estas etapas:

1. leer una muestra del archivo sin cargarlo por completo;
2. detectar codificación, delimitador y posible fila de encabezados;
3. separar metadatos de la tabla;
4. proponer el mapeo de tiempo y canales;
5. pedir confirmación solo si existe ambigüedad;
6. convertir valores por bloques;
7. validar el eje temporal y las longitudes;
8. construir el modelo normalizado;
9. emitir un informe estructurado.

La detección automática nunca inventará datos faltantes. Si un archivo contiene únicamente muestras y no existe información temporal, la importación quedará pendiente hasta que el usuario indique la tasa o el intervalo.

El informe de importación contendrá como mínimo:

```text
source_file
encoding
delimiter
header_row
metadata_rows
time_column
channel_columns
row_count_read
row_count_accepted
row_count_rejected
sample_rate_declared
sample_rate_inferred
warnings
errors
```

### 4.2 Validación temporal

- El tiempo debe ser finito y estrictamente creciente.
- Los valores repetidos o decrecientes producirán un error con la fila afectada.
- La tasa inferida se calculará con la mediana de las diferencias temporales.
- El eje será considerado uniforme cuando la desviación máxima respecto a la mediana esté dentro de una tolerancia configurable, inicialmente `1e-6` relativa y `1e-12 s` absoluta.
- El tiempo no uniforme se conservará explícitamente; no se remuestreará en el MVP.

### 4.3 Filas inválidas

- Una fila vacía se ignora y se contabiliza.
- Un tiempo inválido invalida la fila completa.
- Un valor inválido de canal se representa como `NaN` y genera advertencia.
- Las estadísticas ignoran `NaN` y muestran cuántas muestras válidas utilizaron.
- Si un canal no contiene valores válidos, la importación se rechaza para ese canal.

### 4.4 Modelo interno

```text
Acquisition
├── source: SourceReference
├── metadata: AcquisitionMetadata
├── time_axis: UniformTimeAxis | ExplicitTimeAxis
├── channels: tuple[Channel, ...]
└── import_report: ImportReport

Channel
├── id
├── name
├── unit
└── original_samples
```

Para un eje uniforme se almacenarán `start`, `interval` y `length`; no se mantendrá innecesariamente un arreglo completo de tiempo. Las muestras originales no podrán modificarse después de construir la adquisición.

Tipos recomendados:

- tiempo y parámetros temporales: `float64`;
- muestras: `float32` por defecto, con opción `float64` cuando el archivo lo requiera;
- índices: entero de 64 bits;
- máscaras: booleanos.

### 4.5 Visualización

- Vista superpuesta de hasta cuatro canales.
- Color, nombre, visibilidad y eje Y configurables por canal.
- Zoom con rueda, desplazamiento, zoom rectangular, autoescala y restablecimiento.
- Navegador inferior con una región que controle la ventana principal.
- Downsampling min/máx por columna visible o mecanismo equivalente que conserve picos.
- Al ampliar, se mostrarán progresivamente los datos originales del rango.
- Ninguna reducción visual alterará datos, estadísticas o exportaciones.

### 4.6 Cursores y región

Los cursores `X1` y `X2` se ajustarán a la muestra temporal más cercana. Se mostrará:

- tiempo e índice de cada cursor;
- `Δt = X2 - X1`;
- `1 / |Δt|` cuando `Δt != 0`;
- valor de cada canal en ambos puntos;
- diferencia por canal.

La región incluirá ambos extremos y será el ámbito de estadísticas y exportación.

### 4.7 Estadísticas

Para cada canal y ámbito seleccionado:

```text
count_total
count_valid
minimum
maximum
mean
rms
peak_to_peak
```

Definiciones:

\[
RMS = \sqrt{\frac{1}{N}\sum_{i=1}^{N}x_i^2}
\]

\[
V_{pp}=\max(x)-\min(x)
\]

Los acumuladores emplearán `float64`, aunque las muestras se almacenen como `float32`.

### 4.8 Exportación

- Exportar la región y los canales visibles a CSV UTF-8.
- Incluir tiempo explícito en el archivo exportado.
- No sobrescribir un archivo existente sin confirmación.
- Registrar archivo fuente, intervalo exportado y unidades en encabezados comentados o en un archivo JSON acompañante.

### 4.9 Proyecto

El MVP utilizará un archivo `.oscproj` en formato JSON versionado que contenga:

- versión del esquema;
- ruta absoluta y ruta relativa del CSV;
- tamaño y huella del archivo fuente;
- mapeo de columnas;
- nombres, colores y visibilidad de canales;
- cursores y región;
- notas.
- referencias adjuntas y su modo de almacenamiento.

No duplicará las muestras del CSV. Al reabrir, comprobará que el archivo fuente siga siendo compatible. Si falta, permitirá localizarlo nuevamente. No se almacenarán rutas o metadatos inventados.

### 4.10 Material de referencia

El usuario podrá agregar una o varias referencias asociadas a la adquisición o al proyecto:

- imagen de la pantalla del osciloscopio;
- captura de una gráfica o diagrama técnico;
- fotografía de conexión o sensor;
- archivo BIN correspondiente a la misma adquisición;
- otro archivo auxiliar permitido por configuración.

Cada referencia contendrá:

```text
id
kind: image | binary | other
display_name
description
storage_mode: linked | embedded
original_path
relative_path
size_bytes
sha256
created_at
acquisition_relation
```

Reglas:

- Una imagen se mostrará en un visor con zoom, ajuste a ventana y apertura independiente.
- La imagen podrá marcarse como referencia principal del proyecto.
- El MVP no intentará extraer automáticamente escalas ni formas de onda de una imagen.
- Un BIN se mostrará como archivo de referencia con nombre, tamaño, huella y notas.
- El MVP no interpretará ni graficará el BIN; su contenido se conservará byte por byte.
- En modo `linked`, el proyecto guardará la ruta y la huella, y permitirá relocalizar el archivo.
- En modo `embedded`, la referencia se incluirá dentro del contenedor `.oscproj`.
- Antes de integrar un archivo grande se mostrará el aumento estimado del tamaño del proyecto.
- Si una referencia enlazada cambia, falta o no coincide con su huella, se advertirá al usuario sin sustituirla silenciosamente.
- El usuario podrá quitar una referencia del proyecto sin eliminar el archivo original.
- Las notas podrán indicar que un CSV, un BIN y una imagen pertenecen a la misma captura.

Para permitir referencias integradas, `.oscproj` evolucionará de JSON simple a un contenedor ZIP cuando exista al menos un adjunto embebido:

```text
project.json
references/
  images/
  binaries/
```

Un proyecto sin adjuntos podrá continuar usando una representación JSON compatible. El lector determinará el formato por su contenido y versión, no únicamente por la extensión.

## 5. Arquitectura mínima

```text
osc_app/
├── app/
│   ├── main.py
│   ├── windows/
│   ├── widgets/
│   └── tasks/
├── core/
│   ├── models/
│   ├── importers/
│   ├── measurements/
│   ├── projects/
│   └── exporters/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── performance/
│   └── fixtures/
├── pyproject.toml
└── README.md
```

Reglas de dependencia:

- `core` no importará PySide6 ni PyQtGraph.
- Los widgets no analizarán CSV ni realizarán cálculos numéricos.
- Las tareas en segundo plano devolverán resultados del núcleo mediante señales.
- Solo el hilo principal modificará widgets.
- Cada tarea tendrá progreso, cancelación y manejo de error.

El contrato inicial de importadores será equivalente a:

```python
class AcquisitionImporter(Protocol):
    def probe(self, path: Path) -> ProbeResult: ...
    def inspect(self, path: Path) -> ImportProposal: ...
    def load(self, request: ImportRequest) -> ImportResult: ...
```

Esto permitirá agregar posteriormente `SiglentBinImporter` sin implementar todavía un sistema de plugins.

## 6. Interfaz mínima

La ventana principal contendrá:

- menú Archivo: abrir CSV, abrir/guardar proyecto, exportar región y salir;
- explorador de canales;
- gráfica principal;
- navegador inferior;
- panel de cursores y estadísticas;
- panel de informe de importación;
- panel de referencias con miniaturas, descripción y estado del vínculo;
- barra de estado con archivo, muestras, duración, tasa, región visible y memoria estimada.

Durante una operación larga se mostrará progreso y una acción para cancelar. La ventana seguirá respondiendo.

## 7. Manejo de errores

Cada error visible incluirá:

- qué operación falló;
- causa comprensible;
- archivo o fila relacionada, cuando corresponda;
- una acción sugerida;
- detalle técnico desplegable.

Casos mínimos:

- archivo inaccesible;
- codificación no reconocida;
- delimitador ambiguo;
- tabla no localizada;
- tiempo ausente;
- columnas ambiguas;
- valores temporales inválidos;
- falta de memoria;
- proyecto dañado o incompatible;
- fuente de proyecto ausente.
- referencia ausente, modificada, corrupta o demasiado grande para integrarse.

## 8. Objetivos de rendimiento

Se medirán inicialmente en un equipo de referencia documentado. Hasta conocerlo, estos valores son objetivos provisionales:

- importar 7 millones de filas y cuatro canales sin bloquear la interfaz;
- primera representación visible en 10 segundos o menos tras completar la selección de columnas;
- interacción de zoom y desplazamiento con latencia visual objetivo inferior a 100 ms;
- no crear más de una copia completa temporal por canal durante la importación;
- cancelar una tarea en menos de 2 segundos entre bloques de procesamiento;
- manejar 28 millones de muestras totales dentro de un presupuesto objetivo de 1 GB de RAM atribuible a la aplicación.

Los límites se ajustarán con datos y hardware reales, pero no se eliminarán sin dejar una medición sustituta.

## 9. Pruebas obligatorias

### 9.1 Unitarias

- detección de delimitador y encabezados;
- reconocimiento de columnas;
- construcción de ambos tipos de eje temporal;
- monotonicidad y tasa inferida;
- estadísticas con datos normales, `NaN`, infinitos y selección vacía;
- selección de índices por cursores;
- serialización y migración del proyecto.

### 9.2 Integración

- importar CSV de uno, dos y cuatro canales;
- confirmar un mapeo ambiguo;
- cancelar una importación;
- exportar y volver a importar una región;
- guardar, cerrar y reabrir un proyecto;
- relocalizar una fuente movida.
- agregar, visualizar, integrar, vincular, relocalizar y quitar referencias.
- comprobar que un BIN integrado se recupera con la misma huella SHA-256.

### 9.3 Referencias numéricas

- estadísticas comparadas con NumPy mediante tolerancias explícitas;
- seno conocido para verificar tiempo, amplitud y frecuencia por cursores;
- señales sintéticas con discontinuidades para comprobar que el downsampling preserve picos.

### 9.4 Rendimiento

- conjuntos de 1, 7 y 28 millones de muestras totales;
- tiempo de importación;
- pico de memoria;
- latencia de zoom;
- tiempo de cancelación.

## 10. Criterios de aceptación

El MVP se acepta cuando:

1. todos los flujos de la sección 2 funcionan con CSV reales aprobados;
2. los datos fuente permanecen inmutables;
3. los cálculos coinciden con NumPy dentro de las tolerancias definidas por prueba;
4. la interfaz permanece operable durante importación, estadísticas y exportación;
5. los objetivos de rendimiento se miden y documentan, indicando cualquier desviación;
6. la suite automatizada finaliza correctamente;
7. el proyecto puede guardarse y reabrirse sin perder configuración;
8. una imagen de referencia puede visualizarse después de reabrir el proyecto;
9. un BIN puede vincularse o integrarse y recuperarse sin alteración, aunque todavía no se decodifique;
10. los errores obligatorios tienen mensajes accionables;
11. existe un ejecutable o paquete reproducible para Windows;
12. existe documentación breve para instalar, abrir un CSV y reportar un formato incompatible.

## 11. Información pendiente del usuario

Antes de congelar el importador se requiere un conjunto anonimizado de CSV:

- un canal con señal conocida;
- dos canales;
- cuatro canales;
- archivo con metadatos completos;
- archivo con solo valores, si el equipo lo produce;
- distintas bases de tiempo y profundidades;
- al menos un archivo grande real.

Por cada captura se registrará modelo, firmware, canales, memoria, tasa, base temporal, escalas, offsets, factor de sonda y trigger. Estos archivos se convertirán en fixtures o casos equivalentes anonimizados.

## 12. Decisiones aplazadas

- Correspondencia y reparto efectivo de recursos ADC del equipo.
- Límite definitivo de memoria y tiempos en el hardware objetivo.
- Pandas frente a Polars; el núcleo no dependerá de ninguno si NumPy basta.
- PyInstaller frente a Nuitka; PyInstaller será la primera prueba.
- Formato contenedor completo de proyectos con datos integrados.
