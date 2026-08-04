<p align="center">
  <img src="osc_app/resources/osc_app_logo.png" alt="Logo de OSC App" width="190">
</p>

<h1 align="center">OSC App</h1>

<p align="center">
  Visor y analizador de adquisiciones CSV y BIN de osciloscopios SIGLENT.
</p>

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Estado](https://img.shields.io/badge/estado-alpha-orange)](#estado-del-proyecto)
[![Versión](https://img.shields.io/badge/versión-0.2.0-blue)](https://github.com/C0d3Phys/siglent-osc/releases)

OSC App es una aplicación de escritorio para abrir capturas extensas, navegar como en un
osciloscopio y realizar mediciones sin modificar las muestras originales. El desarrollo actual
está enfocado en la familia SIGLENT SDS1xx4X-E/U.

> Importante: el lector BIN es experimental. Verifica mediciones críticas contra el instrumento
> o contra una exportación CSV oficial de la misma captura.

## Funciones actuales

- Importación de CSV con eje temporal explícito y hasta cuatro canales.
- Lectura directa del formato binario Hantek `.lwf`, sin requerir CSV ni REF.
- Lectura experimental del BIN moderno SIGLENT de 8 bits.
- Detección de canales activos, escala, offset, sonda, tasa de muestreo y trigger.
- Capturas de hasta 14 Mpts verificadas con archivos reales.
- Zoom horizontal tipo `Time/div` con pasos 1–2–5.
- Zoom vertical mediante `Ctrl + rueda`, Auto Y y controles Y+/Y−.
- Visualización por picos o promedio visual.
- Activación individual de canales y modo `Solo`.
- Atenuación de sonda configurable por canal entre 0.01X y 1000X.
- Acoplamiento DC, AC centrado, AC filtrado e inversión de polaridad por canal.
- Cursores verticales X1/X2 y horizontales Y1/Y2, apagados al iniciar.
- Colocación guiada, movimiento fino y etiquetas Y desplazables.
- Región X1–X2 con estadísticas y valores por canal.
- Frecuencia automática y Duty+ mediante umbral medio e histéresis 40/60 %.
- Tablas superpuestas movibles para cursores, estadísticas y ciclo motor.
- Exportación PNG con las mediciones y superposiciones visibles.
- Señales de referencia CSV/BIN con alineación, ganancia, offset y transparencia.
- Offset visual independiente por canal, separación automática y restablecimiento,
  sin modificar las muestras ni las mediciones eléctricas.
- Etiquetas C1/C2/C3/C4 junto al eje Y: arrastre para desplazar el canal y doble
  clic para regresar su offset a cero. Doble clic con la rueda restaura la vista.
- Reglas X bloqueables, entrada numérica y hasta 32 particiones configurables.
- Mediciones de flancos, pulsos, subida, bajada, overshoot, retardo y fase.
- Seis pruebas automotrices guiadas con conexiones, preparación y seguridad.
- Canales matemáticos seguros: operaciones A/B, derivada, integral y filtros.
- Analizador FFT con ventanas, escala lineal/dB y conversión de pico a RPM.
- Decodificación UART 8-N-1 inicial con tabla hexadecimal y validación de parada.

## Interfaz

- Barra de herramientas con íconos planos dibujados por código (no íconos nativos del
  sistema) y tooltips, para abrir, guardar imagen, cursores X/Y, Auto Y, zoom a región,
  vista completa, canal matemático y FFT. Se puede ocultar desde `Opciones → Barra de
  herramientas` o haciendo clic derecho sobre ella.
- Los tres paneles (Canales, Herramientas, Estadísticas) se muestran automáticamente al
  importar una adquisición.
- El panel de canales usa una tarjeta por canal, con un borde del color del trazo, casilla
  de visibilidad, botón `Solo`, y los controles de Sonda y Offset en la misma fila.
- Arrastrar y soltar un archivo `.csv`, `.bin` o `.lwf` sobre la ventana lo abre directamente.
- Menú `Archivo → Abrir reciente` con los últimos archivos abiertos, persistente entre sesiones.
- Resumen permanente bajo la gráfica con archivo, muestras, duración, tasa, canales activos
  sobre el total y memoria estimada; se actualiza al importar y al mostrar u ocultar canales.
- Atajos adicionales: `Ctrl+1/2/3` para los paneles de canales, herramientas y estadísticas;
  `Ctrl+4/5` para cursores X/Y; `Ctrl+F` FFT; `Ctrl+M` canal matemático; `Ctrl+R` zoom a región;
  `Ctrl+0` vista completa; `Ctrl+Y` Auto Y.

## Análisis de ciclo motor

La referencia angular se define señalando primero `0°` y después `720°`. La aplicación:

- divide el ciclo en cuatro áreas de 180°;
- colorea Trabajo, Escape, Admisión y Compresión;
- permite escoger qué etapa comienza en 0°;
- convierte X1, X2 y ΔX de tiempo a grados;
- calcula duración del ciclo y RPM;
- incluye los resultados en una tabla superpuesta exportable.

`1/Δt` corresponde exclusivamente a la separación de X1 y X2. La frecuencia automática del
canal aparece como `Freq` en la tabla de estadísticas y las RPM se muestran en la tabla del ciclo.

## Compresímetro en PSI

El modo compresímetro convierte un canal de voltaje a presión mediante dos puntos de calibración:

```text
voltaje mínimo  → presión mínima
voltaje máximo  → presión máxima
```

También admite un factor adicional de corrección del sensor. Al activarlo, la gráfica, el eje
vertical, Y1/Y2 y las estadísticas del canal seleccionado se muestran en PSI.

El análisis del ciclo informa:

- presión mínima y máxima;
- ángulo donde aparece la presión máxima;
- presión máxima durante cada una de las cuatro etapas.

Ejemplo para un sensor de `0.5–4.5 V / 0–500 PSI`:

| Ajuste | Valor |
|---|---:|
| Voltaje mínimo | 0.5 V |
| Voltaje máximo | 4.5 V |
| Presión mínima | 0 PSI |
| Presión máxima | 500 PSI |
| Factor sensor | 1.0X |

La conversión no recorta valores fuera del rango configurado, lo que permite detectar sobrepasos
o errores de cero.

## Formatos compatibles

| Formato | Estado | Observaciones |
|---|---|---|
| CSV | Compatible | Tiempo explícito y columnas CH1–CH4 |
| Hantek LWF binario | Experimental | Lectura autónoma; no requiere CSV, REF ni BMP |
| SIGLENT BIN moderno de 8 bits | Experimental | Validado con cabecera `0x800` |
| SIGLENT BIN de 16 bits | Pendiente | Se rechaza de forma segura |
| BIN SIGLENT antiguo | Pendiente | Necesita un parser independiente |
| MATLAB/DAT | Pendiente | Planificado como importador adicional |

## Instalación para desarrollo

Requisitos: Windows 10/11 y Python 3.10 o superior.

### Ejecutable para Windows

La versión `v0.2.0` se distribuye como `OSC-App-v0.2.0-windows-x64.exe` desde la sección
[Releases](https://github.com/C0d3Phys/siglent-osc/releases). Es un ejecutable autónomo: no
requiere instalar Python. Descárgalo, ejecútalo y usa **Archivo → Abrir adquisición** para cargar
CSV, BIN de SIGLENT o LWF de Hantek.

```powershell
git clone https://github.com/C0d3Phys/siglent-osc.git
cd siglent-osc
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Ejecutar

```powershell
python -m osc_app
```

Después de la instalación también está disponible:

```powershell
osc-app
```

Usa **Archivo → Abrir adquisición** para seleccionar un archivo `.csv`, `.bin` o `.lwf`. Para
una captura Hantek también puedes usar **Archivo → Abrir captura Hantek** y seleccionar el
binario `.lwf`; no se necesitan archivos CSV, REF ni BMP asociados.

## Generar el ejecutable

Con las dependencias de desarrollo instaladas:

```powershell
python -m PyInstaller OSC-App.spec --clean --noconfirm
```

El resultado se genera en `output/OSC-App.exe`. El archivo `.spec` incluye el logotipo y los
recursos necesarios de la aplicación.

## Controles principales

| Acción | Control |
|---|---|
| Acercar o alejar tiempo | Rueda sobre la gráfica |
| Acercar o alejar verticalmente | `Ctrl + rueda` |
| Colocar X1/X2 o Y1/Y2 | Activar el tipo de cursor y hacer dos clics |
| Mover cursores | Arrastrarlos después de colocarlos |
| Mover texto Y1/Y2 | Arrastrar solamente la etiqueta sobre su línea |
| Mover tablas superpuestas | Arrastrar la tabla con el botón izquierdo |
| Medir Freq y Duty+ | Consultar estadísticas; usa X1–X2 si la región está activa |
| Analizar ciclo motor | Pulsar `Marcar 0° y 720°` y señalar ambos puntos |
| Medir ángulos | Definir el ciclo y colocar X1/X2 |
| Cambiar la etapa inicial | Elegir la etapa que comienza en 0° |
| Medir presión | Configurar el sensor y activar `Mostrar y medir en PSI` |
| Corregir voltaje real | Ajustar `Sonda` en el panel de canales |
| Abrir menú de gráfica | Clic derecho sobre la gráfica |
| Abrir adquisición | `Ctrl + O`, botón de la barra de herramientas o arrastrar el archivo a la ventana |
| Abrir un archivo reciente | `Archivo → Abrir reciente` |
| Guardar imagen | `Ctrl + S` o botón de la barra de herramientas |
| Mostrar u ocultar panel de canales | `Ctrl + 1` |
| Mostrar u ocultar panel de herramientas | `Ctrl + 2` |
| Mostrar u ocultar panel de estadísticas | `Ctrl + 3` |
| Mostrar u ocultar cursores X1/X2 | `Ctrl + 4` |
| Mostrar u ocultar cursores Y1/Y2 | `Ctrl + 5` |
| Auto Y | `Ctrl + Y` o botón de la barra de herramientas |
| Vista completa | `Ctrl + 0` o botón de la barra de herramientas |
| Zoom a región X1–X2 | `Ctrl + R` o botón de la barra de herramientas |
| Abrir señal de referencia | `Herramientas → Abrir señal de referencia` |
| Seleccionar una referencia | `Ctrl + clic` sobre su trazo |
| Sincronizar una referencia seleccionada | `Ctrl + arrastrar` sobre la gráfica |
| Comparar matemáticamente con la referencia | `Herramientas → Comparar con referencia` |
| Crear canal matemático | `Ctrl + M` o `Herramientas → Crear canal matemático` |
| Analizar espectro | `Ctrl + F` o `Herramientas → Analizador FFT` |
| Decodificar UART | `Herramientas → Decodificación UART` |
| Abrir pruebas guiadas | `Análisis → Pruebas automotrices guiadas` |

## CSV sintético para pruebas

```powershell
python -m osc_app.tools.generate_sample_csv examples/siglent_fake_4ch.csv
```

Con cantidad de muestras y tasa personalizadas:

```powershell
python -m osc_app.tools.generate_sample_csv examples/captura.csv --samples 100000 --sample-rate 1000000
```

Los BIN y las capturas de trabajo están excluidos por `.gitignore` para evitar publicar archivos
grandes o potencialmente privados. Los CSV sintéticos dentro de `examples/` sí pueden versionarse.

## Calidad y pruebas

Las comprobaciones se ejecutan localmente; el proyecto no utiliza GitHub Actions.

```powershell
python -m pytest
ruff check .
```

Actualmente existen 57 pruebas automatizadas para importación CSV/BIN/LWF, estadísticas,
selección de muestras, frecuencia, Duty+, herramientas de análisis y el comportamiento de la
interfaz (barra de herramientas, apertura de paneles, tarjetas de canal, resumen de estado,
archivos recientes y arrastrar-y-soltar). Las pruebas de interfaz usan Qt en modo `offscreen`
(`tests/conftest.py` lo define por defecto) y no requieren un servidor gráfico.

## Estructura

```text
siglent-osc/
├── docs/                  # Especificaciones y planificación
├── osc_app/
│   ├── app/               # Interfaz PySide6 y PyQtGraph
│   ├── core/              # Modelos, importadores, mediciones y utilidades de interfaz
│   ├── resources/         # Logo y recursos empaquetados
│   └── tools/             # Generadores y utilidades
├── tests/                 # Pruebas automatizadas
├── CHANGELOG.md
├── CONTRIBUTING.md
├── README.md
└── pyproject.toml
```

## Documentación

- [Índice de documentación](docs/README.md)
- [Especificación general del producto](docs/product-specification.md)
- [Especificación del MVP](docs/mvp-specification.md)
- [Plan de desarrollo](docs/development-plan.md)
- [Mejoras de interfaz](docs/ui-improvements.md)
- [Guía para contribuir](CONTRIBUTING.md)
- [Registro de cambios](CHANGELOG.md)

## Estado del proyecto

El proyecto está en fase alpha. Las principales limitaciones actuales son:

- soporte experimental para una sola variante moderna del BIN de 8 bits;
- necesidad de validar más parejas BIN/CSV y más modelos SIGLENT;
- estadísticas de capturas grandes calculadas todavía en el hilo de la interfaz;
- ausencia de empaquetado `.exe`, proyectos persistentes, FFT y filtros;
- calibraciones del compresímetro todavía no se guardan entre sesiones.

## Colaboración

El repositorio público está disponible en
[github.com/C0d3Phys/siglent-osc](https://github.com/C0d3Phys/siglent-osc).
Antes de proponer cambios, consulta [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencia

El proyecto todavía no declara una licencia de distribución. Hasta que se añada una licencia,
el código puede consultarse públicamente, pero no se concede automáticamente permiso para
redistribuirlo o crear trabajos derivados.
