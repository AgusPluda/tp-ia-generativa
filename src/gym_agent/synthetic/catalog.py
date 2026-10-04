"""Catálogo de hechos compartidos: única fuente de verdad entre la base, los PDFs y la evaluación.

El generador de datos (`data.py`), el texto de los PDFs (`pdf_content.py`) y la batería de
evaluación importan este módulo, de modo que no pueden contradecirse (plan, "Decisión de
estructura").

Reglas de contenido (principio III, "cada fuente tiene un rol claro"):

- Los **precios** viven solo acá y en la tabla `planes`; nunca aparecen en los PDFs.
- Las **reglas y plazos** (`REGLAS`) y las **frecuencias de mantenimiento** (`TIPOS_EQUIPO`)
  aparecen en los PDFs; la base solo guarda los hechos (pagos, equipos, fechas).

Los valores son una propuesta concreta para que la batería tenga respuestas determinadas;
no deben cambiar una vez definida la batería de evaluación.
"""

from dataclasses import dataclass
from decimal import Decimal

# --- Documentos -------------------------------------------------------------


@dataclass(frozen=True)
class Documento:
    """Un PDF sintético: identificador interno, archivo en `data/pdfs/` y título legible."""

    id: str
    nombre_archivo: str
    titulo: str


DOCUMENTOS: dict[str, Documento] = {
    d.id: d
    for d in (
        Documento("reglamento_interno", "reglamento_interno.pdf", "Reglamento interno"),
        Documento("guia_rutinas_nutricion", "guia_rutinas_nutricion.pdf", "Guía de rutinas y nutrición"),
        Documento(
            "manual_equipamiento",
            "manual_equipamiento.pdf",
            "Manual de uso y mantenimiento del equipamiento",
        ),
    )
}
"""Los tres documentos del RAG, por id. El título es el que se guarda en `rag.documentos` y se cita."""

# --- Planes (solo en la base) -----------------------------------------------


@dataclass(frozen=True)
class Plan:
    """Fila de la tabla `planes`. `precio_mensual` en pesos; **nunca** se escribe en los PDFs."""

    nombre: str  # VARCHAR(50) UNIQUE
    precio_mensual: Decimal  # NUMERIC(10,2) > 0
    clases_por_semana: int  # >= 0
    duracion_meses: int  # > 0


PLANES: tuple[Plan, ...] = (
    Plan("Básico", Decimal("35000.00"), 2, 1),
    Plan("Estándar", Decimal("45000.00"), 3, 1),
    Plan("Premium", Decimal("60000.00"), 6, 1),
    Plan("Estudiante", Decimal("28000.00"), 3, 1),
    Plan("Anual", Decimal("38000.00"), 3, 12),
)
"""Los 5 planes, en el orden de inserción (define `id_plan` 1 a 5)."""

# --- Equipamiento -----------------------------------------------------------

TIPOS_EQUIPO: dict[str, int] = {
    "Cinta de correr": 30,
    "Bicicleta fija": 45,
    "Elíptico": 60,
    "Máquina de pesas": 90,
}
"""Tipo de equipo (`equipamiento.tipo`, VARCHAR(40)) → frecuencia de mantenimiento en días.

Cada tipo es una sección del manual de equipamiento con el mismo nombre.
"""

SALAS_EQUIPAMIENTO: tuple[str, ...] = ("Sala de musculación", "Sala de cardio")
"""Salas donde está el equipamiento (VARCHAR(30))."""

SALA_POR_TIPO_EQUIPO: dict[str, str] = {
    "Cinta de correr": "Sala de cardio",
    "Bicicleta fija": "Sala de cardio",
    "Elíptico": "Sala de cardio",
    "Máquina de pesas": "Sala de musculación",
}
"""Sala en la que se ubica cada tipo de equipo."""

# --- Reglas del reglamento y de la guía -------------------------------------


@dataclass(frozen=True)
class Reglas:
    """Plazos y límites que publican el reglamento interno y la guía de rutinas."""

    congelamiento_max_dias: int
    """Duración máxima de cada congelamiento de la cuota."""
    congelamiento_max_veces_anio: int
    """Cantidad máxima de congelamientos por año calendario."""
    congelamiento_aviso_horas: int
    """Anticipación mínima para pedir el congelamiento."""
    mora_dias_para_vencido: int
    """Días de gracia **después de terminar el mes** de la cuota; pasado ese plazo, la cuota vence."""
    mora_dias_suspension: int
    """Días con la cuota vencida tras los cuales se suspende el acceso al gimnasio."""
    baja_aviso_dias: int
    """Anticipación mínima para pedir la baja."""
    cancelacion_anticipacion_horas: int
    """Anticipación mínima para cancelar la reserva de una clase."""
    faltas_sin_aviso_limite: int
    """Faltas sin aviso a partir de las cuales se pierde la prioridad de reserva."""
    rutina_principiante_dias_semana: int
    """Días de entrenamiento por semana recomendados para principiantes."""


REGLAS = Reglas(
    congelamiento_max_dias=30,
    congelamiento_max_veces_anio=2,
    congelamiento_aviso_horas=48,
    mora_dias_para_vencido=10,
    mora_dias_suspension=30,
    baja_aviso_dias=15,
    cancelacion_anticipacion_horas=2,
    faltas_sin_aviso_limite=3,
    rutina_principiante_dias_semana=3,
)
"""Valores vigentes de las reglas."""

COMIDA_PRE_ENTRENAMIENTO: str = "hidratos de carbono"
"""Recomendación central de la guía para comer antes de entrenar (pregunta R05)."""

COMIDA_PRE_ENTRENAMIENTO_HORAS: str = "1 a 2 horas"
"""Cuánto antes de entrenar se recomienda esa comida."""

# --- Hechos verificables ----------------------------------------------------

_CLAVE_TIPO = {
    "Cinta de correr": "cintas",
    "Bicicleta fija": "bicicletas",
    "Elíptico": "elipticos",
    "Máquina de pesas": "maquinas_pesas",
}

CLAVES_HECHOS: dict[str, tuple[str, str]] = {
    # Reglamento interno
    "congelamiento_max_dias": ("reglamento_interno", f"{REGLAS.congelamiento_max_dias} días"),
    "congelamiento_max_veces_anio": ("reglamento_interno", f"{REGLAS.congelamiento_max_veces_anio} veces"),
    "congelamiento_aviso": ("reglamento_interno", f"{REGLAS.congelamiento_aviso_horas} horas"),
    "mora_dias_para_vencido": ("reglamento_interno", f"{REGLAS.mora_dias_para_vencido} días"),
    "mora_dias_suspension": ("reglamento_interno", f"{REGLAS.mora_dias_suspension} días"),
    "baja_aviso": ("reglamento_interno", f"{REGLAS.baja_aviso_dias} días"),
    "cancelacion_anticipacion": ("reglamento_interno", f"{REGLAS.cancelacion_anticipacion_horas} horas"),
    "faltas_sin_aviso_limite": ("reglamento_interno", f"{REGLAS.faltas_sin_aviso_limite} faltas"),
    # Guía de rutinas y nutrición
    "rutina_principiante_frecuencia": (
        "guia_rutinas_nutricion",
        f"{REGLAS.rutina_principiante_dias_semana} días",
    ),
    "comida_pre_entrenamiento": ("guia_rutinas_nutricion", COMIDA_PRE_ENTRENAMIENTO),
    # Manual de equipamiento: una clave por tipo, derivada de TIPOS_EQUIPO
    **{
        f"frecuencia_mantenimiento_{_CLAVE_TIPO[tipo]}": ("manual_equipamiento", f"{dias} días")
        for tipo, dias in TIPOS_EQUIPO.items()
    },
}
"""Clave → (id de documento, texto esperado).

El texto debe aparecer literalmente en el PDF indicado (test T022) y en la respuesta del agente
cuando la batería usa el chequeo `contiene_hecho`. Se mantienen cortos (valor y unidad) para que
la comparación no dependa de la redacción.
"""

# --- Listas curadas para el generador (sin Faker, research R7) --------------

NOMBRES: tuple[str, ...] = (
    "Agustina", "Martina", "Lucía", "Sofía", "Valentina", "Camila", "Julieta", "Florencia",
    "Micaela", "Carolina", "Paula", "Romina", "Daniela", "Natalia", "Belén", "Victoria",
    "Milagros", "Rocío", "Ana", "Laura",
    "Santiago", "Mateo", "Tomás", "Joaquín", "Facundo", "Nicolás", "Martín", "Lucas",
    "Federico", "Gonzalo", "Ignacio", "Matías", "Franco", "Juan", "Diego", "Pablo",
    "Sebastián", "Emiliano", "Bruno", "Ezequiel",
)
"""Nombres de pila (40). No incluye "Zacarías": la pregunta B04 usa un socio inexistente."""

APELLIDOS: tuple[str, ...] = (
    "González", "Rodríguez", "Gómez", "Fernández", "López", "Díaz", "Martínez", "Pérez",
    "García", "Sánchez", "Romero", "Sosa", "Torres", "Álvarez", "Ruiz", "Ramírez",
    "Flores", "Benítez", "Acosta", "Medina", "Herrera", "Suárez", "Aguirre", "Giménez",
    "Gutiérrez", "Pereyra", "Rojas", "Molina", "Castro", "Ortiz", "Silva", "Núñez",
    "Luna", "Juárez", "Cabrera", "Ríos", "Ferreyra", "Godoy", "Morales", "Domínguez",
)
"""Apellidos (40). No incluye "Inexistente" (pregunta B04)."""

TIPOS_CLASE: dict[str, tuple[str, ...]] = {
    "Funcional": ("Funcional", "Entrenamiento en circuito"),
    "Spinning": ("Spinning",),
    "Yoga": ("Yoga", "Pilates"),
    "Musculación": ("Musculación guiada", "Tonificación"),
    "Entrenamiento de alta intensidad": ("HIIT", "Cross training"),
    "Danza": ("Zumba", "Ritmos"),
}
"""Especialidad del instructor (`instructores.especialidad`) → nombres de clase que puede dictar."""

SALA_POR_CLASE: dict[str, str] = {
    "Funcional": "Sala 1",
    "Entrenamiento en circuito": "Sala 1",
    "Spinning": "Sala de spinning",
    "Yoga": "Estudio",
    "Pilates": "Estudio",
    "Musculación guiada": "Sala de musculación",
    "Tonificación": "Sala 2",
    "HIIT": "Sala 1",
    "Cross training": "Sala 2",
    "Zumba": "Sala 2",
    "Ritmos": "Sala 2",
}
"""Sala (`clases.sala`, VARCHAR(30)) en la que se dicta cada clase."""

DIAS_SEMANA: tuple[str, ...] = (
    "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo",
)
"""Valores de `clases.dia_semana`, **sin tildes**, en el orden de `date.weekday()` (0 = lunes)."""

MEDIOS_PAGO: tuple[str, ...] = ("efectivo", "transferencia", "tarjeta", "mercado_pago")
"""Valores válidos de `pagos.medio_pago`."""
