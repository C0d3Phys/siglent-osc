# Especificación técnica para agente de desarrollo  
## OSC App para análisis de señales del SIGLENT SDS1104X-E

**Proyecto:** OSC App  
**Objetivo inicial:** importar y analizar adquisiciones exportadas en CSV desde un SIGLENT SDS1104X-E.  
**Fase posterior:** lectura directa de archivos BIN y, más adelante, adquisición por LAN/SCPI.  
**Plataforma objetivo inicial:** Windows 10/11.  
**Lenguaje recomendado:** Python 3.12+.  
**Interfaz recomendada:** PySide6.  
**Motor gráfico recomendado:** PyQtGraph.  
**Procesamiento numérico:** NumPy, SciPy, Pandas o Polars.

---

# 1. Visión general

Construir una aplicación de escritorio que funcione como un osciloscopio de análisis fuera de línea. La aplicación debe abrir capturas exportadas desde el SIGLENT, conservar todas las muestras disponibles y permitir análisis interactivo avanzado:

- visualización multicanal;
- zoom y desplazamiento;
- cursores temporales y verticales;
- estadísticas sobre toda la señal o una región;
- operaciones matemáticas entre canales;
- FFT;
- filtrado digital;
- derivada e integral;
- calibración de sensores;
- conversión de tiempo a grados de cigüeñal;
- análisis especializado de señales automotrices;
- almacenamiento de proyectos y resultados;
- generación de reportes.

La primera versión debe trabajar exclusivamente con **CSV**. La arquitectura debe quedar preparada para agregar después un lector BIN sin modificar el núcleo de análisis.

---

# 2. Principio de diseño

Separar la aplicación en capas independientes:

```text
Archivo CSV del SIGLENT
        ↓
Importador y normalizador
        ↓
Modelo interno de adquisición
        ↓
Motor matemático y de procesamiento
        ↓
Interfaz interactiva
        ↓
Módulos especializados
        ↓
Exportación y reportes
```

La interfaz nunca debe procesar directamente el archivo original. El importador convierte cualquier CSV compatible a un modelo interno normalizado.

---

# 3. Alcance de la versión inicial

## 3.1 Incluido

1. Importación de CSV.
2. Detección flexible de encabezados.
3. Soporte para uno o varios canales.
4. Reconstrucción del eje temporal.
5. Visualización fluida de millones de muestras.
6. Zoom horizontal y vertical.
7. Desplazamiento y selección de regiones.
8. Cursores X y Y.
9. Medidas estadísticas.
10. Canales matemáticos.
11. FFT.
12. Filtros digitales.
13. Calibración lineal y por tabla.
14. Conversión de voltaje a unidades físicas.
15. Guardado de proyectos.
16. Exportación de resultados.
17. Módulo automotriz inicial.
18. Planificador de memoria, muestreo y duración.

## 3.2 No incluido en la primera versión

- lectura directa de BIN;
- control directo del osciloscopio;
- adquisición en tiempo real;
- comunicación SCPI;
- decodificación automática completa de buses;
- aprendizaje automático;
- diagnóstico automático definitivo.

Estas funciones deben contemplarse en la arquitectura, pero no bloquear la primera entrega.

---

# 4. Hardware de referencia

## 4.1 Osciloscopio

SIGLENT SDS1104X-E:

- 4 canales analógicos;
- dos recursos ADC internos;
- memoria larga;
- exportación CSV;
- exportación BIN;
- posibilidad futura de control por LAN/SCPI.

La aplicación debe leer siempre los valores reales guardados en el archivo y no asumir una tasa de muestreo o profundidad fija.

## 4.2 Uso de los dos ADC

La aplicación debe permitir documentar la asignación física de canales y advertir sobre posibles recursos compartidos.

Distribución conceptual de trabajo:

```text
Grupo ADC A
 ├── C1
 └── C2

Grupo ADC B
 ├── C3
 └── C4
```

Esta asignación debe tratarse como configurable o verificable, ya que la correspondencia exacta debe confirmarse con documentación o pruebas del equipo.

Configuración automotriz recomendada:

```text
C1 → presión de cilindro
C2 → MAP, corriente, inyector u otra señal complementaria
C3 → CKP
C4 → CMP, encendido o inyector
```

La aplicación debe poder mostrar una recomendación como:

```text
Presión y CKP están asignados al mismo grupo ADC.
Considere usar C1 y C3 para separar las señales críticas.
```

---

# 5. Relación entre memoria, tasa y tiempo

La aplicación debe incorporar estas relaciones fundamentales.

## 5.1 Tiempo capturado

\[
T = \frac{N}{f_s}
\]

Donde:

- \(T\): duración total de la adquisición en segundos;
- \(N\): número de muestras;
- \(f_s\): tasa de muestreo en muestras por segundo.

## 5.2 Memoria necesaria

\[
N = T f_s
\]

## 5.3 Tasa máxima para una duración

\[
f_s = \frac{N}{T}
\]

## 5.4 Intervalo entre muestras

\[
\Delta t = \frac{1}{f_s}
\]

## 5.5 Eje temporal

\[
t_i = t_0 + i\Delta t
\]

Si existe posición de trigger:

\[
t_i = t_{\text{trigger}} + (i-i_{\text{trigger}})\Delta t
\]

---

# 6. Cálculos automotrices

## 6.1 Tiempo de una revolución

\[
T_{360} = \frac{60}{RPM}
\]

## 6.2 Tiempo de un ciclo de cuatro tiempos

\[
T_{720} = \frac{120}{RPM}
\]

## 6.3 Tiempo para varios ciclos

\[
T = n\frac{120}{RPM}
\]

Donde \(n\) es el número de ciclos de 720°.

## 6.4 Memoria necesaria para varios ciclos

\[
N = f_s n \frac{120}{RPM}
\]

## 6.5 Resolución angular teórica por muestra

\[
\Delta\theta =
\frac{RPM \cdot 360}{60f_s}
\]

Simplificando:

\[
\Delta\theta =
\frac{6RPM}{f_s}
\]

con \(f_s\) expresado en muestras por segundo.

## 6.6 Ejemplo a 4000 rpm

A 4000 rpm:

\[
T_{720} = \frac{120}{4000}=0.03\text{ s}
\]

Un ciclo completo dura 30 ms.

A 1 MSa/s:

\[
\Delta\theta =
\frac{6\cdot4000}{1\,000\,000}
=0.024^\circ/\text{muestra}
\]

A 500 kSa/s:

\[
\Delta\theta = 0.048^\circ/\text{muestra}
\]

Estas resoluciones son suficientes para presión, CKP, CMP y varias señales automotrices. La limitación práctica será normalmente el sensor, el ruido, el adaptador, el ancho de banda y la detección de eventos, no la cantidad teórica de muestras.

---

# 7. Registro de un pull

La aplicación debe incluir un planificador específico para capturar una aceleración o pull.

Ejemplo con 7 Mpts disponibles por canal:

| Tasa | Duración aproximada |
|---:|---:|
| 10 MSa/s | 0.7 s |
| 5 MSa/s | 1.4 s |
| 2 MSa/s | 3.5 s |
| 1 MSa/s | 7 s |
| 500 kSa/s | 14 s |
| 250 kSa/s | 28 s |
| 100 kSa/s | 70 s |

Para un pull de 5 a 7 segundos:

```text
Tasa recomendada inicial: 1 MSa/s
Memoria: hasta 7 Mpts por canal
Canales: 4
```

Para un pull de 10 a 14 segundos:

```text
Tasa recomendada inicial: 500 kSa/s
Memoria: hasta 7 Mpts por canal
Canales: 4
```

El planificador debe solicitar:

- duración esperada;
- RPM inicial;
- RPM final;
- número de canales;
- memoria disponible;
- resolución deseada;
- tipo de señal.

Debe devolver:

- tasa recomendada;
- memoria necesaria;
- duración máxima;
- resolución temporal;
- resolución angular a RPM máxima;
- advertencias.

---

# 8. Modelo interno de datos

Usar una estructura independiente del formato del archivo.

```python
Acquisition
├── metadata
├── time_axis
├── channels
├── math_channels
├── markers
├── cursors
├── measurements
├── processing_history
└── project_settings
```

## 8.1 Metadata

Campos mínimos:

```text
instrument_model
instrument_serial
firmware_version
source_file
import_date
sample_rate
sample_interval
record_length
trigger_time
trigger_index
timebase
acquisition_mode
channel_count
notes
```

No todos los CSV tendrán todos los campos. Los ausentes deben guardarse como `None`, no inventarse.

## 8.2 Canal

Cada canal debe contener:

```text
id
name
enabled
raw_samples
unit
vertical_scale
vertical_offset
probe_factor
coupling
bandwidth_limit
adc_group
sensor_profile
processed_views
```

## 8.3 Tipos de datos

- Tiempo: `float64`.
- Señal: preferentemente `float32` o `float64`.
- Datos crudos: conservar si están disponibles.
- Máscaras y eventos: arreglos enteros o booleanos.

Para capturas grandes se debe considerar `numpy.memmap`.

---

# 9. Importación de CSV

## 9.1 Requisitos

El importador debe:

1. detectar codificación;
2. detectar delimitador;
3. identificar líneas de metadatos;
4. localizar el inicio de la tabla;
5. detectar columnas;
6. reconocer tiempo, voltaje y canales;
7. convertir valores a tipos numéricos;
8. manejar separador decimal coma o punto;
9. eliminar filas inválidas;
10. validar monotonicidad temporal;
11. detectar tasa de muestreo;
12. producir un informe de importación.

## 9.2 Variantes esperadas

CSV con tiempo y señal:

```csv
Time,CH1
-0.050000,0.512
-0.049999,0.514
```

CSV con múltiples canales:

```csv
Time,CH1,CH2,CH3,CH4
0.000000,1.2,0.1,4.8,0.0
```

CSV con solo valores:

```csv
0.512
0.514
0.516
```

En el último caso se requiere \(\Delta t\) desde metadatos o ingreso manual.

## 9.3 Detección de columnas

Buscar nombres equivalentes:

```text
Time
Second
Seconds
X
Timestamp

CH1
C1
Channel 1
Volt
Voltage
Amplitude
```

La detección debe ser configurable y mostrar al usuario el mapeo antes de importar cuando exista ambigüedad.

## 9.4 Validaciones

- número de filas;
- valores NaN;
- tiempo repetido;
- tiempo no monótono;
- separación temporal variable;
- canales de longitud desigual;
- tasa inferida;
- posibles unidades incorrectas.

---

# 10. Visualización principal

## 10.1 Requisitos

- hasta cuatro canales físicos;
- canales matemáticos adicionales;
- zoom por rueda;
- zoom por selección rectangular;
- desplazamiento por arrastre;
- autoescala;
- escalas independientes;
- ocultar o mostrar canales;
- rejilla;
- ejes en unidades físicas;
- vista completa;
- historial de zoom;
- restablecer vista;
- modo superpuesto;
- modo apilado;
- fondo y tema configurables.

## 10.2 Rendimiento

No dibujar necesariamente todos los puntos cuando la vista no los requiere.

Implementar:

- downsampling visual;
- min/max por píxel;
- niveles de detalle;
- caché por rango;
- actualización diferida durante arrastre;
- procesamiento por bloques;
- `clipToView`;
- arreglos NumPy contiguos.

Al ampliar, deben aparecer progresivamente las muestras reales.

## 10.3 Navegador inferior

Agregar una vista resumida de toda la adquisición con una región seleccionable que controle la ventana principal.

---

# 11. Cursores

## 11.1 Cursores temporales

Dos cursores verticales:

```text
X1
X2
```

Medidas:

\[
\Delta t = X_2-X_1
\]

\[
f = \frac{1}{\Delta t}
\]

Mostrar:

- \(t_1\);
- \(t_2\);
- \(\Delta t\);
- frecuencia equivalente;
- índice de muestra;
- valor de cada canal en cada cursor;
- diferencia por canal.

## 11.2 Cursores verticales

Dos cursores horizontales:

```text
Y1
Y2
```

\[
\Delta Y=Y_2-Y_1
\]

Deben respetar la unidad actual:

- V;
- A;
- PSI;
- kPa;
- bar;
- grados;
- unidades personalizadas.

## 11.3 Cursores de seguimiento

El cursor debe ajustarse a la muestra más cercana y mostrar:

```text
índice
tiempo
valor original
valor calibrado
ángulo
pendiente local
canal
```

## 11.4 Cursores por región

Una región seleccionada debe actuar como ámbito para:

- estadísticas;
- FFT;
- filtros;
- exportación;
- detección de eventos;
- ajuste de modelos.

---

# 12. Mediciones y estadísticas

Calcular sobre:

- captura completa;
- región seleccionada;
- ciclo seleccionado;
- conjunto de ciclos;
- canal original;
- canal procesado;
- canal matemático.

## 12.1 Estadísticas básicas

- mínimo;
- máximo;
- pico a pico;
- media;
- mediana;
- RMS;
- desviación estándar;
- varianza;
- percentiles;
- número de muestras;
- suma;
- integral;
- área positiva;
- área negativa.

## 12.2 Mediciones temporales

- período;
- frecuencia;
- ciclo de trabajo;
- ancho de pulso;
- tiempo de subida;
- tiempo de caída;
- retardo entre canales;
- cruce por umbral;
- fase aproximada.

## 12.3 Estadísticas repetidas

Para varios ciclos:

- media de la medida;
- mínimo;
- máximo;
- desviación estándar;
- coeficiente de variación;
- cantidad de ciclos;
- banda media ±1σ;
- banda media ±2σ.

## 12.4 Definiciones

RMS:

\[
x_{RMS} =
\sqrt{\frac{1}{N}\sum_{i=1}^{N}x_i^2}
\]

Media:

\[
\bar{x} =
\frac{1}{N}\sum_{i=1}^{N}x_i
\]

Desviación estándar poblacional:

\[
\sigma =
\sqrt{
\frac{1}{N}
\sum_{i=1}^{N}(x_i-\bar{x})^2
}
\]

---

# 13. Canales matemáticos

Permitir crear expresiones:

```text
M1 = C1 + C2
M2 = C1 - C2
M3 = C1 * C2
M4 = C1 / C2
```

## 13.1 Operaciones mínimas

- suma;
- resta;
- multiplicación;
- división;
- inversión;
- valor absoluto;
- raíz;
- potencia;
- logaritmo;
- eliminación de DC;
- normalización;
- derivada;
- integral;
- promedio móvil.

## 13.2 Protección de división

\[
M[n]=\frac{C_1[n]}{C_2[n]+\varepsilon}
\]

El sistema debe:

- detectar divisores cercanos a cero;
- marcar valores inválidos;
- permitir usar NaN;
- mostrar advertencia;
- no ocultar errores silenciosamente.

## 13.3 Compatibilidad temporal

Si dos canales tienen ejes temporales diferentes:

1. determinar región común;
2. seleccionar eje de referencia;
3. interpolar;
4. registrar la interpolación en el historial.

---

# 14. FFT

## 14.1 Selección

Permitir FFT de:

- señal completa;
- región entre cursores;
- ciclo;
- varios ciclos;
- canal matemático;
- señal filtrada.

## 14.2 Parámetros

- longitud FFT;
- zero padding;
- eliminación de DC;
- detrend;
- ventana;
- escala lineal;
- escala dB;
- amplitud pico;
- amplitud RMS;
- PSD;
- frecuencia máxima visible.

## 14.3 Ventanas

- rectangular;
- Hann;
- Hamming;
- Blackman;
- Blackman-Harris;
- Flat Top.

## 14.4 Eje de frecuencia

\[
f_k=\frac{k f_s}{N}
\]

Resolución:

\[
\Delta f=\frac{f_s}{N}
\]

Nyquist:

\[
f_N=\frac{f_s}{2}
\]

## 14.5 Resultados

- frecuencia dominante;
- amplitud dominante;
- armónicos;
- THD;
- ruido RMS;
- energía por banda;
- cursores espectrales;
- conversión de frecuencia a RPM.

Conversión básica:

\[
RPM=60f
\]

Debe permitirse definir eventos por revolución:

\[
RPM =
\frac{60f}{n_{\text{eventos/rev}}}
\]

---

# 15. Filtros digitales

Los filtros nunca deben modificar los datos originales.

Mantener:

```text
señal original
señal calibrada
señal procesada
```

## 15.1 Filtros mínimos

- promedio móvil;
- mediana;
- Savitzky-Golay;
- pasa bajos;
- pasa altos;
- pasa banda;
- elimina banda;
- Butterworth;
- Bessel;
- notch 50/60 Hz;
- eliminación de DC.

## 15.2 Parámetros

- frecuencia de corte;
- orden;
- frecuencia central;
- ancho de banda;
- aplicación causal;
- aplicación de fase cero;
- manejo de bordes.

## 15.3 Advertencias

La aplicación debe mostrar:

- filtro activo;
- parámetros;
- posible desfase;
- señal utilizada para estadísticas;
- si se aplicó `filtfilt`;
- si la región es demasiado corta.

---

# 16. Derivada e integral

## 16.1 Derivada temporal

\[
\frac{dx}{dt}
\]

Aplicación:

- detección de flancos;
- velocidad de cambio de presión;
- apertura y cierre de válvulas;
- detección de eventos.

## 16.2 Derivada angular

Si existe eje angular:

\[
\frac{dP}{d\theta}
\]

## 16.3 Integral

\[
I(t)=\int x(t)\,dt
\]

Aplicaciones:

- carga eléctrica;
- energía;
- área de presión;
- corriente acumulada.

Para potencia:

\[
P(t)=V(t)I(t)
\]

Para energía:

\[
E=\int V(t)I(t)\,dt
\]

---

# 17. Calibración de sensores

## 17.1 Perfil de sensor

Ejemplo:

```text
Nombre: P265 300 PSI
Unidad de entrada: V
Unidad de salida: PSI
V mínimo: 0.5 V
V máximo: 4.5 V
P mínimo: 0 PSI
P máximo: 300 PSI
```

## 17.2 Conversión lineal

\[
P =
P_{\min}+
\frac{V-V_{\min}}
{V_{\max}-V_{\min}}
(P_{\max}-P_{\min})
\]

## 17.3 Calibración por dos puntos

El usuario introduce dos pares:

```text
(V1, P1)
(V2, P2)
```

Se calcula:

\[
P=aV+b
\]

## 17.4 Calibración por tabla

Permitir:

```csv
Voltage,Pressure
0.50,0
1.00,37.5
2.00,112.5
4.50,300
```

Interpolación:

- lineal;
- spline opcional;
- extrapolación desactivada por defecto.

## 17.5 Ajuste polinómico

\[
P(V)=a_0+a_1V+a_2V^2+\cdots+a_nV^n
\]

Mostrar:

- coeficientes;
- residuos;
- RMSE;
- \(R^2\);
- rango válido;
- advertencia de extrapolación.

## 17.6 Perfiles guardables

- presión;
- corriente;
- temperatura;
- vacío;
- fuerza;
- desplazamiento;
- unidades personalizadas.

---

# 18. Conversión de tiempo a grados

## 18.1 Mediante dos picos consecutivos

Entre dos picos del mismo cilindro hay 720°:

\[
\theta(t)=
720^\circ
\frac{t-t_1}{t_2-t_1}
\]

Ventaja:

- implementación rápida.

Limitación:

- supone velocidad aproximadamente constante dentro del ciclo.

## 18.2 Mediante CKP

Proceso:

1. seleccionar canal CKP;
2. acondicionar;
3. detectar flancos;
4. identificar dientes;
5. detectar diente faltante;
6. asignar grados por diente;
7. interpolar entre dientes;
8. generar eje angular no uniforme;
9. remuestrear la presión sobre una cuadrícula angular.

Ventaja:

- compensa variaciones de RPM;
- permite análisis angular preciso.

## 18.3 Mediante CKP y CMP

CMP permite:

- distinguir las dos vueltas;
- identificar fase de cilindro;
- alinear ciclos de 720°;
- relacionar presión con eventos de válvulas.

---

# 19. Módulo de presión de cilindro

## 19.1 Objetivo

Analizar presión de cilindro en función del tiempo y del ángulo de cigüeñal.

## 19.2 Funciones

- conversión V → PSI, kPa o bar;
- detección de picos;
- segmentación de ciclos;
- alineación a 720°;
- superposición;
- promedio de ciclos;
- dispersión;
- marcadores de eventos;
- mediciones de presión;
- análisis de vacío;
- análisis de escape;
- análisis de sincronización.

## 19.3 Eventos de referencia

Usar etiquetas configurables:

```text
A → pico máximo
B → zona de presión media
C → presión mínima
D → vacío máximo
E → referencia de sincronización
F → inicio de escape
G → fin de escape / traslape
H → referencia de admisión
I → vacío comparable con D
J → zona de vacío estable
K → cierre de admisión
L → inicio de compresión
```

Estas etiquetas se basan en el esquema del artículo técnico revisado. Deben ser editables y no considerarse universales para todos los motores.

## 19.4 Métricas

- presión máxima;
- presión mínima;
- vacío;
- diferencia D-I;
- ángulo del máximo;
- pendiente antes y después del PMS;
- área bajo la curva;
- presión en ángulos definidos;
- contrapresión de escape;
- duración de rampas;
- repetibilidad;
- correlación con referencia.

## 19.5 Superposición de ciclos

Mostrar:

```text
Ciclo 1
Ciclo 2
...
Media
Media ±1σ
Media ±2σ
```

Calcular:

- RMSE entre ciclos;
- correlación;
- desplazamiento angular;
- amplitud relativa;
- detección de ciclos atípicos.

---

# 20. Módulos automotrices posteriores

Diseñar una interfaz de plugin para agregar:

## 20.1 CKP/CMP

- dientes;
- diente faltante;
- fase;
- sincronización;
- desviación temporal;
- velocidad instantánea.

## 20.2 Inyector

- tiempo de activación;
- corriente;
- pico inductivo;
- apertura mecánica aproximada;
- potencia;
- energía.

## 20.3 Bobina

- dwell;
- corriente primaria;
- saturación;
- tiempo de chispa;
- oscilaciones;
- energía.

## 20.4 Compresión relativa

- corriente de arranque;
- ripple de batería;
- velocidad CKP;
- correlación por cilindro.

## 20.5 CAN

- visualización diferencial;
- resta CH-CANH y CANL;
- niveles;
- bit time;
- errores básicos;
- decodificación posterior.

---

# 21. Arquitectura de software

## 21.1 Paquetes propuestos

```text
osc_app/
├── app/
│   ├── main.py
│   ├── ui/
│   ├── controllers/
│   └── resources/
├── core/
│   ├── models/
│   ├── importers/
│   ├── processing/
│   ├── measurements/
│   ├── fft/
│   ├── filters/
│   ├── calibration/
│   ├── automotive/
│   └── exporters/
├── plugins/
├── tests/
├── examples/
├── docs/
└── pyproject.toml
```

## 21.2 Componentes

### `core.models`

- `Acquisition`;
- `Channel`;
- `TimeAxis`;
- `SensorProfile`;
- `MeasurementResult`;
- `ProcessingStep`;
- `Project`.

### `core.importers`

- `SiglentCsvImporter`;
- `GenericCsvImporter`;
- detector de formato;
- mapeo de columnas;
- parser de metadatos.

### `core.processing`

- resampling;
- interpolation;
- derivative;
- integration;
- math expressions;
- decimation.

### `core.measurements`

- statistics;
- edge detection;
- pulse measurements;
- cycle measurements.

### `core.fft`

- windowing;
- spectrum;
- PSD;
- THD;
- harmonic analysis.

### `core.filters`

- moving average;
- median;
- Savitzky-Golay;
- IIR;
- FIR;
- notch.

### `core.calibration`

- linear;
- table;
- polynomial;
- unit conversion.

### `core.automotive`

- RPM;
- crank angle;
- CKP detection;
- cylinder pressure;
- cycle overlay.

---

# 22. Interfaz de usuario

Diseño recomendado:

```text
┌──────────────────────────────────────────────────────────────┐
│ Archivo  Vista  Cursores  Medidas  Matemática  FFT  Filtros │
├───────────────┬──────────────────────────────────────────────┤
│ Canales       │                                              │
│ C1 Presión    │              Gráfica principal               │
│ C2 MAP        │                                              │
│ C3 CKP        │                                              │
│ C4 CMP        │                                              │
│ M1            │                                              │
├───────────────┼──────────────────────────────────────────────┤
│ Mediciones    │ Navegador de adquisición                    │
│ Máx           ├──────────────────────────────────────────────┤
│ RMS           │ Eventos / estadísticas / ciclos             │
│ Δt            │                                              │
│ ΔV            │                                              │
└───────────────┴──────────────────────────────────────────────┘
```

## 22.1 Paneles

- explorador de canales;
- propiedades;
- mediciones;
- cursores;
- FFT;
- filtros;
- calibración;
- eventos;
- consola de importación;
- historial de procesamiento.

## 22.2 Barra de estado

Mostrar:

```text
Archivo
Número de muestras
Tasa de muestreo
Duración
Canales activos
Región visible
Memoria usada
Unidad
Estado de filtros
```

---

# 23. Historial y reproducibilidad

Cada operación debe registrarse:

```text
1. Importar CSV
2. Asignar C1 como presión
3. Aplicar calibración P265
4. Quitar DC
5. Filtro Butterworth 100 Hz
6. Seleccionar región
7. Detectar ciclos
8. Calcular promedio
```

Permitir:

- deshacer;
- rehacer;
- reejecutar;
- exportar receta;
- comparar original y procesado.

No sobrescribir nunca el dato original.

---

# 24. Formato de proyecto

Usar un contenedor de proyecto, por ejemplo:

```text
proyecto.oscproj
```

Puede ser ZIP con:

```text
project.json
metadata.json
channels/
measurements.json
markers.json
sensor_profiles.json
processed/
thumbnails/
```

No es obligatorio duplicar el CSV original; se puede:

- enlazar;
- copiar;
- integrar opcionalmente.

---

# 25. Exportación

## 25.1 Datos

- CSV;
- Parquet;
- NumPy NPZ;
- JSON de metadatos;
- selección por cursores;
- ciclos alineados;
- espectro FFT.

## 25.2 Gráficas

- PNG;
- SVG;
- PDF;
- copia para reporte.

## 25.3 Reporte

Incluir:

- identificación del archivo;
- equipo;
- fecha;
- configuración;
- canales;
- calibraciones;
- capturas;
- mediciones;
- estadísticas;
- observaciones;
- advertencias;
- conclusión técnica editable.

---

# 26. Rendimiento y memoria

## 26.1 Objetivo

Manejar al menos:

```text
4 canales × 7 Mpts = 28 millones de muestras
```

## 26.2 Estimación

Con `float64`:

\[
28\,000\,000 \times 8 \approx 224\text{ MB}
\]

Sin incluir eje temporal, copias, filtros y cachés.

Con `float32`:

\[
28\,000\,000 \times 4 \approx 112\text{ MB}
\]

Estrategia:

- conservar tiempo implícito cuando sea uniforme;
- usar un solo eje temporal compartido;
- usar `float32` para muestras cuando sea suficiente;
- usar `float64` para cálculos sensibles;
- evitar copias;
- procesamiento por bloques;
- caché limitada;
- `memmap` para archivos grandes.

---

# 27. Seguridad numérica

- validar unidades;
- controlar división por cero;
- controlar NaN e infinitos;
- verificar monotonicidad temporal;
- evitar extrapolación silenciosa;
- mostrar desfase introducido por filtros;
- registrar interpolaciones;
- conservar precisión suficiente;
- no redondear durante cálculos;
- mostrar incertidumbre cuando exista.

---

# 28. Pruebas

## 28.1 Unitarias

- cálculo de tasa;
- cálculo de memoria;
- cálculo de duración;
- importación;
- detección de columnas;
- estadística;
- FFT;
- filtros;
- calibración;
- derivada;
- integral;
- conversión angular.

## 28.2 Datos sintéticos

Generar:

- seno;
- cuadrada;
- rampa;
- pulso;
- señal con ruido;
- señal multicanal;
- CKP simulado;
- presión de cilindro sintética.

## 28.3 Comparación

Validar contra:

- NumPy;
- SciPy;
- resultados conocidos;
- mediciones del osciloscopio;
- CSV oficial del SIGLENT.

## 28.4 Pruebas de rendimiento

- 1 Mpts;
- 7 Mpts;
- 14 Mpts;
- 28 Mpts totales;
- zoom;
- cursores;
- FFT;
- filtros.

---

# 29. Plan de desarrollo

## Fase 0 — Preparación

- crear repositorio;
- configurar entorno;
- seleccionar licencia;
- definir estilo de código;
- integrar pruebas;
- crear datos sintéticos.

## Fase 1 — MVP CSV

- abrir CSV;
- detectar columnas;
- importar un canal;
- mostrar señal;
- zoom;
- desplazamiento;
- información básica.

## Fase 2 — Multicanal

- hasta cuatro canales;
- escalas independientes;
- activar/ocultar;
- navegador inferior;
- proyectos.

## Fase 3 — Cursores y mediciones

- X1/X2;
- Y1/Y2;
- región;
- estadísticas;
- tabla de medidas.

## Fase 4 — Matemáticas y filtros

- +, -, *, /;
- derivada;
- integral;
- filtros;
- historial.

## Fase 5 — FFT

- ventanas;
- amplitud;
- dB;
- armónicos;
- cursores;
- exportación.

## Fase 6 — Calibración

- lineal;
- tabla;
- polinómica;
- perfiles de sensores;
- unidades físicas.

## Fase 7 — Automotriz inicial

- RPM;
- tiempo a grados;
- ciclos;
- superposición;
- presión de cilindro;
- eventos configurables.

## Fase 8 — CKP/CMP

- detección de dientes;
- diente faltante;
- eje angular;
- remuestreo angular.

## Fase 9 — BIN

Solo después de estabilizar el análisis CSV.

Proceso:

```text
BIN original
        ↓
CSV oficial equivalente
        ↓
comparación
        ↓
ingeniería inversa controlada
        ↓
lector BIN propio
```

## Fase 10 — SCPI

- conexión LAN;
- identificación;
- descarga de forma de onda;
- captura remota;
- configuración básica.

---

# 30. Estrategia futura para BIN

No desarrollar primero el lector BIN.

Cuando el MVP CSV sea estable:

1. guardar la misma adquisición en BIN y CSV;
2. recopilar pares de prueba;
3. variar escala vertical;
4. variar offset;
5. variar base de tiempo;
6. variar memoria;
7. variar canales;
8. variar posición del trigger;
9. comparar bytes con muestras conocidas;
10. identificar cabecera y bloques.

Probar hipótesis:

- `int8`;
- `uint8`;
- `int16`;
- `uint16`;
- little-endian;
- big-endian;
- canales intercalados;
- canales consecutivos.

Modelo de conversión:

\[
V_i=aD_i+b
\]

Reconstrucción temporal:

\[
t_i=t_0+i\Delta t
\]

Criterio de validación:

\[
RMSE =
\sqrt{
\frac{1}{N}
\sum_{i=1}^{N}
(V_{BIN,i}-V_{CSV,i})^2
}
\]

El lector BIN solo se considerará válido cuando:

- reproduzca el CSV oficial;
- conserve escala;
- conserve offset;
- conserve tiempo;
- conserve trigger;
- funcione con diferentes configuraciones;
- tenga pruebas automatizadas.

---

# 31. Requisitos de calidad para el agente

El agente debe:

1. escribir código modular;
2. usar tipado;
3. documentar funciones;
4. incluir manejo de errores;
5. agregar pruebas;
6. evitar lógica numérica dentro de widgets;
7. separar modelo, vista y control;
8. conservar datos originales;
9. registrar transformaciones;
10. no inventar metadatos;
11. medir rendimiento;
12. mantener compatibilidad con Windows;
13. preparar empaquetado con PyInstaller o Nuitka;
14. usar configuración en `pyproject.toml`;
15. producir entregas pequeñas y ejecutables.

---

# 32. Criterios de aceptación del MVP

El MVP se considera funcional cuando:

- abre un CSV real del SIGLENT;
- identifica el eje temporal;
- muestra al menos un canal;
- soporta varios millones de muestras;
- permite zoom fluido;
- permite desplazamiento;
- permite dos cursores temporales;
- calcula \(\Delta t\) y frecuencia;
- calcula mínimo, máximo, media, RMS y pico a pico;
- exporta una región;
- guarda y reabre un proyecto;
- no modifica el archivo original;
- informa errores de formato claramente.

---

# 33. Primera tarea práctica

Solicitar al usuario varios CSV del SIGLENT:

1. un canal, señal de calibración;
2. dos canales;
3. cuatro canales;
4. diferentes bases de tiempo;
5. diferentes memorias;
6. señal DC conocida;
7. seno conocido;
8. señal automotriz.

Para cada archivo registrar:

```text
modelo
firmware
canales activos
memoria
sample rate
timebase
vertical scale
offset
probe factor
trigger
tipo de exportación
```

A partir de esos archivos se diseña y valida el importador real.

---

# 34. Decisiones técnicas recomendadas

```text
GUI: PySide6
Gráfica: PyQtGraph
Numérico: NumPy + SciPy
Tablas: Polars o Pandas
Formato rápido: Parquet
Proyecto: ZIP + JSON + NPZ/Parquet
Pruebas: pytest
Tipado: mypy o pyright
Calidad: ruff
Empaquetado: PyInstaller inicialmente
```

---

# 35. Resultado final esperado

Una aplicación que aproveche las adquisiciones del SIGLENT como fuente de datos y convierta el osciloscopio en una plataforma de análisis ampliada:

```text
SIGLENT
   ↓
captura multicanal
   ↓
CSV
   ↓
OSC App
   ├── cursores
   ├── estadísticas
   ├── matemáticas
   ├── FFT
   ├── filtros
   ├── calibración
   ├── análisis angular
   ├── presión de cilindro
   ├── CKP/CMP
   └── reportes
```

El valor principal no es replicar únicamente la pantalla del osciloscopio, sino aprovechar la memoria, los canales y los datos exportados para construir herramientas de análisis especializadas, reproducibles y ampliables.

---

# 36. Instrucción maestra para el agente

```text
Construya una aplicación de escritorio modular en Python para analizar
adquisiciones CSV exportadas desde un SIGLENT SDS1104X-E.

Comience por un MVP que importe archivos CSV de formato variable,
normalice tiempo y canales, muestre millones de muestras con PyQtGraph,
permita zoom, desplazamiento, cursores y estadísticas básicas.

Mantenga totalmente separado el importador, el modelo de adquisición,
el motor numérico y la interfaz. Nunca modifique los datos originales.

Después agregue canales matemáticos, filtros, FFT, calibración de sensores,
conversión tiempo-grados, segmentación de ciclos y análisis de presión de
cilindro.

No implemente todavía lectura BIN. Diseñe una interfaz de importadores que
permita agregar posteriormente SiglentBinImporter sin modificar el núcleo.

Entregue cada fase ejecutable, probada y documentada. Use tipado, pruebas
unitarias, manejo de errores y datos sintéticos. Priorice exactitud numérica,
rendimiento con hasta 28 millones de muestras y reproducibilidad.
```
