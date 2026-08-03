from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuidedTest:
    name: str
    purpose: str
    connections: tuple[str, ...]
    setup: tuple[str, ...]
    checks: tuple[str, ...]
    warning: str


GUIDED_TESTS = (
    GuidedTest(
        "Compresión relativa",
        "Comparar el esfuerzo de compresión entre cilindros durante el arranque.",
        ("Pinza de corriente en el cable principal del motor de arranque.",),
        ("Desactivar combustible/encendido.", "Capturar varios ciclos de arranque."),
        ("Comparar amplitud entre eventos.", "Buscar un cilindro consistentemente bajo."),
        "Use una pinza adecuada; nunca conecte una entrada de tensión en serie con el arranque.",
    ),
    GuidedTest(
        "Presión dentro del cilindro",
        "Relacionar presión, vacío y eventos de válvulas con el ciclo de 720°.",
        ("Transductor de presión en el cilindro.", "Canal de sincronización opcional CKP/CMP."),
        ("Configurar la calibración PSI.", "Marcar dos picos consecutivos como 0° y 720°."),
        ("Revisar presión máxima.", "Comparar escape, admisión, compresión y trabajo."),
        "Confirme el rango térmico y de presión del transductor antes de arrancar el motor.",
    ),
    GuidedTest(
        "Sensor CKP",
        "Evaluar regularidad de dientes, amplitud y referencia de diente faltante.",
        ("Sonda al CKP con masa segura según el tipo de sensor.",),
        ("Usar acoplamiento DC inicialmente.", "Capturar al menos dos revoluciones."),
        ("Contar flancos.", "Buscar huecos, deformaciones o amplitud irregular."),
        "No perfore aislamiento ni use masa de chasis en circuitos diferenciales sin verificar.",
    ),
    GuidedTest(
        "Sincronización CKP/CMP",
        "Comparar la relación temporal entre cigüeñal y árbol de levas.",
        ("CKP en un canal y CMP en otro.",),
        ("Usar la misma base temporal.", "Mostrar varios ciclos completos."),
        ("Medir retardo/fase.", "Comparar con una referencia conocida del mismo motor."),
        "La forma y relación correctas dependen del motor; no concluya sin una referencia válida.",
    ),
    GuidedTest(
        "Inyector",
        "Medir tiempo de activación y comportamiento inductivo del inyector.",
        ("Sonda de tensión o pinza de corriente apropiada.",),
        ("Seleccionar rango para el pico inductivo.", "Capturar varios accionamientos."),
        ("Medir ancho de pulso.", "Revisar repetibilidad y pico de desconexión."),
        "Use atenuación y categoría de tensión adecuadas para evitar dañar el osciloscopio.",
    ),
    GuidedTest(
        "Rizado del alternador",
        "Detectar irregularidad de diodos o fases en la salida del alternador.",
        ("Medir sobre batería con conexión y atenuación seguras.",),
        ("Usar AC para eliminar el nivel de batería.", "Aplicar carga eléctrica estable."),
        ("Comparar repetición de picos.", "Buscar huecos o amplitudes desiguales."),
        "Evite cortocircuitos en batería y respete la categoría eléctrica de las sondas.",
    ),
)
