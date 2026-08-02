<p align="center">
  <img src="osc_app/resources/osc_app_logo.png" alt="Logo de OSC App" width="190">
</p>

<h1 align="center">OSC App</h1>

<p align="center">
  Analizador de escritorio para adquisiciones CSV y BIN de osciloscopios SIGLENT.
</p>

OSC App convierte capturas extensas del osciloscopio en una experiencia de análisis interactiva: visualización multicanal, navegación tipo `Time/div`, cursores, mediciones, estadísticas y exportación de gráficas. El desarrollo actual está enfocado en la familia SIGLENT SDS1xx4X-E/U y en mantener intactos los datos originales.

> Estado: versión experimental en desarrollo. Verifica siempre los resultados críticos contra el instrumento o contra una exportación CSV oficial.

## Funciones disponibles

- Importación de CSV con tiempo explícito y hasta cuatro canales.
- Lectura experimental del BIN moderno SIGLENT de 8 bits.
- Detección de canales, escala, offset, sonda, tasa de muestreo y trigger.
- Carga de capturas de hasta 14 Mpts probada con archivos reales.
- Zoom horizontal tipo `Time/div` con pasos 1–2–5.
- `Ctrl + rueda` para ajustar la escala vertical.
- Modos visuales de picos y promedio.
- Activación independiente de canales y modo `Solo`.
- Configuración de atenuación de sonda por canal, desde 0.01X hasta 1000X.
- Cursores X1/X2 y Y1/Y2 con colocación guiada.
- Referencia de ciclo motor 0°–720°, cuatro etapas coloreadas, grados y RPM.
- Tabla superpuesta exportable con 0°, 720°, duración, RPM y etapa inicial.
- Modo compresímetro calibrable en PSI por rango de voltaje, presión y factor del sensor.
- Presión mínima/máxima del ciclo, ángulo del pico y máximo de cada etapa.
- Región de medición y estadísticas por canal.
- Frecuencia automática y Duty+ por canal con umbral medio e histéresis 40/60 %.
- Tablas superpuestas de cursores y estadísticas.
- Exportación PNG incluyendo cursores y mediciones visibles.

## Capturas compatibles

| Formato | Estado | Observaciones |
|---|---|---|
| CSV | Compatible | Tiempo explícito y columnas CH1–CH4 |
| SIGLENT BIN moderno, 8 bits | Experimental | Validado con cabecera `0x800` en SDS1xx4X-E/U |
| SIGLENT BIN de 16 bits | Pendiente | Se rechaza de forma segura |
| BIN SIGLENT antiguo | Pendiente | Requiere otro parser |
| MATLAB/DAT | Pendiente | Planificado como importador adicional |

## Requisitos

- Windows 10/11.
- Python 3.10 o superior; Python 3.12 recomendado.
- PySide6.
- PyQtGraph.
- NumPy.

## Instalación para desarrollo

```powershell
git clone <URL-DEL-REPOSITORIO>
cd "OSC APP"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Sustituye `<URL-DEL-REPOSITORIO>` por la dirección que GitHub proporcione después de publicar el proyecto.

## Ejecutar

```powershell
python -m osc_app
```

También queda disponible el comando:

```powershell
osc-app
```

Desde la aplicación usa **Archivo → Abrir adquisición** para seleccionar `.csv` o `.bin`.

## Datos sintéticos

Para crear un CSV reproducible de cuatro canales:

```powershell
python -m osc_app.tools.generate_sample_csv examples/siglent_fake_4ch.csv
```

Para cambiar la cantidad de muestras y la tasa:

```powershell
python -m osc_app.tools.generate_sample_csv examples/captura.csv --samples 100000 --sample-rate 1000000
```

Los BIN reales, proyectos y capturas de trabajo están excluidos por `.gitignore` para evitar publicar archivos grandes o potencialmente privados.

## Controles principales

| Acción | Control |
|---|---|
| Acercar o alejar tiempo | Rueda sobre la gráfica |
| Acercar o alejar voltaje | `Ctrl + rueda` |
| Colocar cursores | Activar X o Y y hacer dos clics |
| Medir Freq y Duty+ | Consultar la tabla de estadísticas; usa la región X1–X2 si está activa |
| Mover cursores | Arrastrar después de colocarlos |
| Mover texto Y1/Y2 | Arrastrar la etiqueta de voltaje a lo largo de su línea |
| Mover tablas superpuestas | Arrastrar la tabla con el botón izquierdo |
| Analizar ciclo motor | Pulsar `Marcar 0° y 720°` y señalar ambos puntos |
| Medir ángulos | Definir el ciclo y colocar los cursores verticales X1/X2 |
| Cambiar el orden del ciclo | Elegir la etapa que comienza en 0° |
| Medir presión | Configurar el rango del sensor y activar `Mostrar y medir en PSI` |
| Corregir voltaje real | Ajustar `Sonda` en el panel de canales |
| Opciones de gráfica | Clic derecho |
| Guardar imagen | `Ctrl + S` |
| Abrir adquisición | `Ctrl + O` |

La conversión del compresímetro usa los dos puntos de calibración del sensor:
`voltaje mínimo → PSI mínimo` y `voltaje máximo → PSI máximo`. El factor del sensor
permite aplicar una corrección adicional sin modificar las muestras originales.

## Calidad y pruebas

```powershell
python -m pytest
ruff check .
```

La automatización de GitHub ejecuta ambas comprobaciones en cada actualización y propuesta de cambio.

## Estructura

```text
OSC APP/
├── .github/workflows/     # Verificación automática
├── docs/                  # Especificaciones y planificación
├── examples/              # Datos sintéticos o ejemplos permitidos
├── osc_app/
│   ├── app/               # Interfaz PySide6/PyQtGraph
│   ├── core/              # Modelos, importadores y mediciones
│   ├── resources/         # Logo y recursos empaquetados
│   └── tools/             # Generadores y utilidades
├── tests/                 # Pruebas automatizadas
├── CONTRIBUTING.md
├── README.md
└── pyproject.toml
```

## Documentación

- [Índice de documentación](docs/README.md)
- [Especificación general del producto](docs/product-specification.md)
- [Especificación ejecutable del MVP](docs/mvp-specification.md)
- [Plan de desarrollo](docs/development-plan.md)
- [Guía para contribuir](CONTRIBUTING.md)

## Limitaciones conocidas

- El lector BIN todavía cubre una sola variante moderna de 8 bits.
- La interpretación del BIN debe validarse con parejas BIN/CSV del mismo instrumento.
- El procesamiento de capturas grandes aún puede optimizarse con ejes temporales implícitos y trabajo en segundo plano.
- No hay todavía empaquetado final `.exe`, proyectos persistentes, FFT, filtros ni calibraciones de sensores.

## Licencia

El proyecto todavía no declara una licencia de distribución. Antes de aceptar contribuciones públicas o permitir reutilización general, el propietario debe elegir y añadir una licencia, por ejemplo MIT, Apache-2.0 o GPL-3.0.
