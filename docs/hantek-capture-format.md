# Formato binario Hantek LWF

## Relación entre los archivos estudiados

Los archivos con el mismo nombre base representan exportaciones relacionadas de una medición,
pero no forman un paquete obligatorio:

| Extensión | Función | Dependencia para abrir LWF |
|---|---|---|
| `.lwf` | Adquisición binaria recuperable del osciloscopio | Ninguna |
| `.csv` | Exportación textual de tiempo y voltaje | No requerida; se usó para validar |
| `.ref` | Forma de onda de referencia recuperable por el instrumento | No requerida |
| `.bmp` | Captura visual de la pantalla | No requerida |

El manual de Hantek identifica LWF como **Wave (Binary)** y permite recuperarlo en el
osciloscopio. CSV y BMP son exportaciones independientes. OSC App abre directamente el LWF y no
busca archivos hermanos.

## Estructura decodificada

La variante comprobada tiene:

1. firma `lwf\0` y versión binaria;
2. cuatro descriptores de canal con activación, base temporal, profundidad, cantidad de muestras,
   tasa de muestreo, offset vertical y código V/div;
3. datos de los canales activos como enteros `int16` little-endian;
4. marcador final `78 56 34 12`.

Las muestras se encuentran al final del archivo, antes del marcador. Para cada canal:

```text
voltaje = (muestra_entera - offset_vertical) × (voltios_por_división / 25)
tiempo  = (índice - índice_de_trigger) / muestras_por_segundo
```

Hantek utiliza 25 cuentas verticales por división. La tabla de códigos V/div abarca desde
`500 µV/div` hasta `10 V/div`.

## Validación

La captura `U168_6.lwf` se abrió sin consultar sus archivos CSV, REF o BMP. El resultado fue:

- versión LWF 2001;
- CH1 activo;
- 4.000 muestras;
- 12.500 Sa/s;
- eje temporal de `-0,15992 s` a `0,16 s`;
- rango de `0 V` a `0,206 V`.

El tiempo, escala y casi toda la secuencia de voltaje se contrastaron con la exportación CSV de
la misma serie. Una diferencia circular de 16 muestras es compatible con exportaciones hechas en
instantes consecutivos mientras el osciloscopio continuaba adquiriendo; no se aplica una rotación
artificial al binario.
