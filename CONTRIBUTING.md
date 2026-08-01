# Contribuir a OSC App

Gracias por ayudar a desarrollar OSC App. El objetivo es mantener una aplicación numéricamente confiable, rápida con capturas extensas y fácil de usar en Windows.

## Preparación

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Flujo recomendado

1. Crea una rama breve para el cambio.
2. Mantén el núcleo numérico separado de la interfaz.
3. Añade o actualiza pruebas.
4. Ejecuta `ruff check .` y `python -m pytest`.
5. Describe qué cambió, cómo se verificó y qué limitaciones quedan.

## Reglas técnicas

- No modificar las muestras originales después de importarlas.
- No colocar parsers o cálculos numéricos dentro de widgets.
- No usar `eval` para expresiones matemáticas.
- No inventar metadatos ausentes del archivo.
- Rechazar de forma segura formatos BIN desconocidos.
- Documentar cualquier interpolación, calibración o conversión.
- Mantener compatibilidad con Windows.

## Datos de prueba

No subas capturas privadas o archivos BIN grandes. Para un error de importación:

- describe modelo y firmware;
- incluye una cabecera anonimizada cuando sea suficiente;
- usa datos sintéticos o una captura mínima autorizada;
- si compartes BIN y CSV, confirma que corresponden a la misma adquisición.

## Propuestas de cambio

Una propuesta debe incluir:

- problema resuelto;
- alcance del cambio;
- pasos de verificación;
- capturas de interfaz cuando cambie la experiencia visual;
- riesgos o formatos todavía no cubiertos.

