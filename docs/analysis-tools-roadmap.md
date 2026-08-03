# OSC App — Diseño de herramientas de análisis V1

## 1. Objetivo

Ampliar OSC App con seis áreas de análisis inspiradas en flujos profesionales de diagnóstico,
manteniendo una interfaz sencilla, datos originales inmutables y funcionamiento fluido con
capturas de hasta 14 millones de muestras por canal.

El orden de entrega es obligatorio:

1. señales de referencia;
2. reglas avanzadas y particiones;
3. mediciones temporales y entre canales;
4. pruebas automotrices guiadas;
5. canales matemáticos;
6. FFT y base de decodificación serial.

La sexta área comienza únicamente cuando las cinco primeras sean ejecutables y estén probadas.

## 2. Principios de arquitectura

- Las muestras importadas nunca se modifican.
- El procesamiento numérico vive en `osc_app/core`, no en los widgets.
- Toda señal derivada registra fuente, operación, parámetros y unidad.
- Los cálculos costosos se realizan al confirmar una acción o al soltar un control, no durante
  cada movimiento del ratón.
- Las herramientas opcionales comienzan ocultas.
- Cada entrega debe conservar compatibilidad con CSV y BIN existentes.
- La interfaz debe poder degradar una función de forma segura si faltan tasa de muestreo,
  canales compatibles o una región válida.

## 3. Modelo funcional compartido

### 3.1 Señal visible

Cada trazo representará una de estas fuentes:

- canal físico importado;
- señal de referencia;
- canal matemático;
- resultado espectral.

Todos exponen nombre, unidad, color, muestras, eje X, visibilidad y metadatos de procedencia.

### 3.2 Ámbitos de cálculo

Las mediciones y transformaciones podrán usar:

- adquisición completa;
- región X1–X2;
- ciclo motor 0°–720°;
- canales visibles seleccionados.

### 3.3 Rendimiento

- Reutilizar el eje temporal cuando sea compatible.
- Usar `float32` para trazos y `float64` para acumulaciones sensibles.
- Limitar cachés a resultados activos.
- Evitar recalcular durante arrastres.
- Mantener downsampling visual por picos.

## 4. Entrega 1 — Señales de referencia

### Alcance

- Abrir una segunda adquisición CSV o BIN como referencia.
- Seleccionar un canal de la referencia.
- Dibujarlo con estilo discontinuo y transparencia configurable.
- Ajustar ganancia y desplazamiento vertical sin cambiar los datos.
- Alinear por tiempo original, X1 o máximo absoluto dentro de X1–X2.
- Seleccionar con `Ctrl + clic` y sincronizar tiempo/amplitud con `Ctrl + arrastrar` sobre la gráfica.
- Calcular correlación, MAE, RMSE, error máximo, ganancia, offset, retardo residual,
  diferencias de frecuencia/Duty y escala temporal estimada.
- Mostrar opcionalmente la curva `Actual − Referencia`.
- Quitar una referencia sin afectar el archivo.

### Interfaz

Menú `Herramientas → Señal de referencia` y panel ocultable con:

- archivo y canal;
- alineación;
- ganancia;
- desplazamiento;
- transparencia;
- visibilidad y eliminación.

### Aceptación

- La referencia nunca reemplaza la adquisición activa.
- Quitarla libera el trazo y sus copias.
- La alineación por X1 y por pico es reproducible.
- Los errores de formato se muestran sin cerrar la adquisición principal.

## 5. Entrega 2 — Reglas avanzadas y particiones

### Alcance

- Bloquear X1–X2 para conservar `Δt` al mover el par.
- Introducir X1, X2, Y1 y Y2 numéricamente.
- Crear particiones configurables entre X1 y X2.
- Presets de 2, 4, 6, 8 y número personalizado.
- Mostrar grados por partición cuando existe ciclo 0°–720°.

### Interfaz

Ampliar la pestaña `Cursores` con bloqueo, campos numéricos y selector de particiones.

### Aceptación

- El bloqueo conserva la separación dentro de tolerancia numérica.
- Una entrada fuera del rango sigue siendo válida y amplía la vista solo cuando el usuario lo
  solicita.
- Las particiones no participan en autoescala vertical.
- Cuatro particiones coinciden con etapas de 180° en un ciclo motor.

## 6. Entrega 3 — Mediciones avanzadas

### Alcance

Por canal:

- conteo de flancos ascendentes y descendentes;
- ancho alto y ancho bajo medios;
- tiempo de subida 10–90 %;
- tiempo de bajada 90–10 %;
- overshoot y undershoot;
- frecuencia y Duty+ existentes.

Entre dos canales:

- retardo por correlación;
- fase en grados usando la frecuencia dominante del canal de referencia.

### Convenciones

- Umbrales bajo/alto: 10 % y 90 % del rango robusto.
- Umbral lógico: punto medio entre niveles bajo y alto.
- Histéresis: 40/60 % para conteo estable.
- Si no hay suficientes eventos, devolver `None`, nunca inventar cero.

### Aceptación

- Resultados verificados con seno, cuadrada, pulso y señales desplazadas sintéticas.
- NaN e infinitos no provocan excepciones.
- La región X1–X2 limita todas las mediciones cuando está activa.

## 7. Entrega 4 — Pruebas automotrices guiadas

### Alcance inicial

Catálogo local de seis plantillas:

1. compresión relativa;
2. presión dentro del cilindro;
3. sensor CKP;
4. sincronización CKP/CMP;
5. inyector;
6. rizado del alternador.

Cada plantilla contiene propósito, conexiones sugeridas, seguridad, canales requeridos,
configuración recomendada y lista de comprobación. No emitirá un diagnóstico definitivo.

### Interfaz

Menú `Análisis → Pruebas guiadas…`, selector de prueba y asistente con pasos Anterior/Siguiente.

### Aceptación

- Puede recorrerse una prueba sin adquisición.
- Aplicar una plantilla solo cambia opciones explícitamente confirmadas.
- Las advertencias eléctricas aparecen antes de conexiones o escalas sugeridas.
- El texto queda separado del código para poder ampliarlo y traducirlo.

## 8. Entrega 5 — Canales matemáticos

### Alcance

Crear un canal derivado a partir de uno o dos canales físicos:

- A+B, A−B, A×B y A/B;
- invertir y valor absoluto;
- derivada e integral;
- pasa-bajos y pasa-altos Butterworth.

El usuario define nombre, color, unidad y parámetros. No se evaluará texto Python arbitrario.

### Seguridad numérica

- División cercana a cero produce NaN.
- Derivada usa el eje temporal real.
- Integral usa acumulación trapezoidal.
- Los filtros requieren una tasa de muestreo válida y verifican Nyquist.

### Aceptación

- Cada operación tiene pruebas numéricas.
- El canal derivado se puede ocultar o eliminar.
- Su procedencia se muestra en la interfaz.
- No se altera ningún canal físico.

## 9. Entrega 6 — FFT y base de decodificación serial

### 9.1 FFT

- Vista espectral para canal físico o matemático.
- Ámbito completo o X1–X2.
- Ventanas rectangular, Hann, Hamming y Blackman.
- Escala lineal o dB.
- Frecuencia y amplitud dominantes.
- Conversión opcional de frecuencia a RPM.

### 9.2 Decodificación serial inicial

La primera entrega no intentará cubrir CAN/LIN completos. Creará una arquitectura de
decodificadores y un decodificador UART básico con:

- canal, umbral y polaridad;
- baud rate configurable;
- 8 bits de datos;
- bit de inicio y parada;
- tabla de tiempo, valor hexadecimal y estado.

CAN, LIN, SENT y FlexRay quedan documentados como extensiones posteriores.

### Aceptación

- FFT validada contra tonos sintéticos conocidos.
- UART validado con tramas sintéticas.
- Los resultados aparecen en vistas separadas y no bloquean el gráfico temporal.

## 10. Organización de código prevista

```text
osc_app/
├── app/
│   ├── main_window.py
│   ├── reference_panel.py
│   ├── guided_tests_dialog.py
│   ├── math_channel_dialog.py
│   └── spectrum_dialog.py
└── core/
    ├── references.py
    ├── advanced_measurements.py
    ├── math_channels.py
    ├── spectrum.py
    └── serial_decoding.py
```

## 11. Estrategia de pruebas

- Pruebas unitarias del núcleo con arreglos pequeños y resultados conocidos.
- Pruebas de integración de importación y creación de herramientas.
- Comprobación manual de la interfaz con `examples/example.bin`.
- Benchmark con captura larga para cursores, referencia, filtro, matemáticas y FFT.
- `pytest`, `ruff` y `git diff --check` deben pasar al cerrar cada entrega.

## 12. Fuera de alcance de esta iteración

- Adquisición en vivo o control SCPI.
- Diagnóstico automático de averías.
- Biblioteca en la nube.
- Decodificación completa de CAN, CAN-FD, LIN, SENT o FlexRay.
- Editor arbitrario de expresiones Python.
- Guardado completo de proyectos y preferencias persistentes.
