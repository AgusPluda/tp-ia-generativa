"""Generador determinista de los datos de negocio (esquema `public`).

`generar_datos()` arma todas las filas en memoria, sin tocar la base, con un único
`random.Random(SEED)` consumido siempre en el mismo orden: dos llamadas devuelven exactamente
lo mismo (CE-007). La carga en Postgres está en `loader.py`.

Las filas no llevan la clave primaria: la carga inserta en orden fijo sobre tablas vacías
(`RESTART IDENTITY`), así que la fila `i` de cada tabla (desde 1) recibe el id `i`. El
generador usa esos mismos ids para las claves foráneas.

Cumple por construcción los invariantes de `data-model.md` y planta los escenarios de
research R7 (instructor destacado, faltas recientes, pagos vencidos, equipos en
mantenimiento y cintas con mantenimiento atrasado). Lo que el esquema no guarda (fecha de
baja, inicio del congelamiento, clases a las que se anotó cada socio) solo existe acá,
durante la generación.
"""

import calendar
import random
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, time, timedelta

from gym_agent.config import HISTORY_START, REFERENCE_DATE, SEED
from gym_agent.synthetic.catalog import (
    APELLIDOS,
    DIAS_SEMANA,
    MEDIOS_PAGO,
    NOMBRES,
    PLANES,
    SALA_POR_CLASE,
    SALA_POR_TIPO_EQUIPO,
    TIPOS_CLASE,
    TIPOS_EQUIPO,
)

# --- Estructura de las tablas ---------------------------------------------------

COLUMNAS: dict[str, tuple[str, ...]] = {
    "planes": ("nombre", "precio_mensual", "clases_por_semana", "duracion_meses"),
    "instructores": ("nombre", "apellido", "especialidad", "fecha_ingreso"),
    "socios": ("nombre", "apellido", "email", "fecha_nacimiento", "fecha_alta", "id_plan", "estado"),
    "clases": ("nombre", "id_instructor", "dia_semana", "hora", "cupo", "sala"),
    "asistencias": ("id_socio", "id_clase", "fecha", "presente"),
    "pagos": ("id_socio", "fecha_pago", "monto", "mes_correspondiente", "medio_pago", "estado"),
    "equipamiento": (
        "nombre", "tipo", "sala", "estado", "fecha_adquisicion", "ultimo_mantenimiento",
    ),
}
"""Columnas que se insertan en cada tabla (sin la clave primaria).

El orden de las claves es el orden de dependencias en que se cargan las tablas, y el orden de
las columnas es el de los valores en cada tupla que devuelve `generar_datos()`.
"""

CLAVE_PRIMARIA: dict[str, str] = {
    "planes": "id_plan",
    "instructores": "id_instructor",
    "socios": "id_socio",
    "clases": "id_clase",
    "asistencias": "id_asistencia",
    "pagos": "id_pago",
    "equipamiento": "id_equipo",
}
"""Columna `SERIAL` de cada tabla; ordena las filas al calcular el hash."""

# --- Fechas derivadas de REFERENCE_DATE ----------------------------------------

INICIO_ULTIMO_MES: date = REFERENCE_DATE - timedelta(days=29)
"""Primer día de la ventana "último mes" (30 días corridos, inclusive, data-model.md)."""

MES_REFERENCIA: date = REFERENCE_DATE.replace(day=1)
"""Mes en curso: el único cuya cuota puede estar `pendiente`."""

INICIO_CONGELAMIENTO: date = date(2026, 9, 1)
"""Los socios `congelado` lo están desde este día: así no tienen filas en el último mes y el
congelamiento no supera `REGLAS.congelamiento_max_dias` al llegar a `REFERENCE_DATE`."""

# --- Volúmenes y escenarios plantados (research R7) ----------------------------

ESPECIALIDADES_INSTRUCTORES: tuple[str, ...] = (
    "Funcional", "Spinning", "Yoga", "Musculación",
    "Entrenamiento de alta intensidad", "Danza", "Yoga", "Musculación",
)
"""Especialidad de cada uno de los 8 instructores, en orden de `id_instructor`."""

CLASES_POR_INSTRUCTOR: tuple[int, ...] = (4, 3, 3, 3, 3, 3, 3, 2)
"""Clases semanales que dicta cada instructor (24 en total)."""

INSTRUCTOR_DESTACADO: int = 1
"""`id_instructor` que debe tener estrictamente más asistencias en el último mes (pregunta S02).

Dicta una clase más que el resto y sus clases atraen más socios (`PESO_CLASE_DESTACADA`)."""

PESO_CLASE_DESTACADA: float = 1.45
"""Peso relativo de las clases del instructor destacado al elegir a qué clases va cada socio."""

MARGEN_DESTACADO: float = 1.1
"""El instructor destacado debe tener al menos un 10 % más de asistencias que el segundo."""

HORARIOS: tuple[time, ...] = (time(8, 0), time(10, 0), time(18, 0), time(19, 0), time(20, 0))
"""Horarios posibles de las clases (de lunes a sábado; cada par día-horario se usa una vez)."""

CUPOS: tuple[int, ...] = (15, 20, 25)

CANTIDAD_SOCIOS: dict[str, int] = {"activo": 45, "congelado": 8, "baja": 7}

PESO_PLANES: tuple[int, ...] = (25, 30, 15, 15, 15)
"""Probabilidad relativa de cada plan de `PLANES` (en el mismo orden)."""

MAX_CLASES_POR_SOCIO: int = 4
"""Tope de clases semanales a las que va un socio, aunque su plan permita más."""

SOCIOS_CON_FALTAS_RECIENTES: int = 6
"""Socios activos con faltas (`presente = false`) en el último mes (pregunta H01). Son los
únicos con faltas en esa ventana, para que la lista de la respuesta sea manejable."""

PROB_FALTA_REGISTRADA: float = 0.3
"""Fuera de la ventana, probabilidad de que una inasistencia quede registrada como falta (el
socio había reservado). Las demás inasistencias no dejan fila."""

PAGOS_VENCIDOS: int = 5
"""Cuotas de agosto impagas (pasan a `vencido`; preguntas S03 y H03)."""

PAGOS_PENDIENTES: int = 6
"""Cuotas de septiembre todavía sin pagar (`pendiente`, que no es lo mismo que vencido)."""

MES_VENCIDO: date = date(2026, 8, 1)
"""Mes de las cuotas vencidas: 31/8 + 10 días de gracia = 10/9, anterior a `REFERENCE_DATE`, y
todavía sin llegar a los `REGLAS.mora_dias_suspension` días que suspenderían el acceso."""

CANTIDAD_EQUIPOS: dict[str, int] = {
    "Cinta de correr": 10,
    "Bicicleta fija": 8,
    "Elíptico": 6,
    "Máquina de pesas": 8,
}
"""Equipos por tipo (32 en total). Las claves coinciden con `TIPOS_EQUIPO`."""

ESTADOS_EQUIPOS_PLANTADOS: dict[tuple[str, int], str] = {
    ("Cinta de correr", 5): "en_mantenimiento",
    ("Bicicleta fija", 2): "en_mantenimiento",
    ("Máquina de pesas", 6): "en_mantenimiento",
    ("Elíptico", 4): "fuera_de_servicio",
    ("Bicicleta fija", 6): "fuera_de_servicio",
}
"""Equipos que no están `operativo` (preguntas H02 y S07). Clave: (tipo, número del equipo)."""

CINTAS_ATRASADAS: dict[tuple[str, int], int] = {
    ("Cinta de correr", 3): 52,
    ("Cinta de correr", 7): 41,
}
"""Cintas cuyo último mantenimiento fue hace más días que la frecuencia del manual (pregunta H04).
Valor: días antes de `REFERENCE_DATE`. El resto de los equipos está al día."""

EQUIPOS_NUEVOS: dict[tuple[str, int], date] = {("Bicicleta fija", 8): date(2026, 9, 20)}
"""Equipos recién comprados, todavía sin mantenimiento (`ultimo_mantenimiento` nulo)."""


# --- Utilidades -----------------------------------------------------------------


def _fecha_aleatoria(rng: random.Random, desde: date, hasta: date) -> date:
    """Fecha uniforme entre `desde` y `hasta`, ambas inclusive."""
    return desde + timedelta(days=rng.randint(0, (hasta - desde).days))


def _fin_de_mes(mes: date) -> date:
    """Último día del mes de `mes`."""
    return mes.replace(day=calendar.monthrange(mes.year, mes.month)[1])


def _meses(desde: date, hasta: date) -> list[date]:
    """Primeros días de cada mes entre `desde` y `hasta` (ambos meses inclusive)."""
    meses, actual = [], desde.replace(day=1)
    while actual <= hasta:
        meses.append(actual)
        actual = (actual + timedelta(days=32)).replace(day=1)
    return meses


def _sin_tildes(texto: str) -> str:
    """Pasa a minúsculas y quita tildes y espacios, para armar direcciones de correo."""
    normalizado = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in normalizado if not unicodedata.combining(c)).replace(" ", "")


def _fechas_de_clase(dia_semana: str, desde: date, hasta: date) -> list[date]:
    """Fechas entre `desde` y `hasta` (inclusive) que caen en `dia_semana`."""
    objetivo = DIAS_SEMANA.index(dia_semana)
    primera = desde + timedelta(days=(objetivo - desde.weekday()) % 7)
    if primera > hasta:
        return []
    return [primera + timedelta(weeks=i) for i in range((hasta - primera).days // 7 + 1)]


@dataclass
class _Socio:
    """Socio durante la generación, con los datos que el esquema no guarda."""

    nombre: str
    apellido: str
    fecha_nacimiento: date
    fecha_alta: date
    id_plan: int
    estado: str
    fin_actividad: date
    """Último día en que puede asistir: `REFERENCE_DATE`, el día previo al congelamiento o la baja."""
    tasa_asistencia: float
    clases: list[int] = field(default_factory=list)
    """`id_clase` de las clases a las que va todas las semanas."""


# --- Tablas -----------------------------------------------------------------------


def _planes() -> list[tuple]:
    """Los 5 planes de `catalog.PLANES`, en orden."""
    return [(p.nombre, p.precio_mensual, p.clases_por_semana, p.duracion_meses) for p in PLANES]


def _instructores(rng: random.Random, nombres: list[tuple[str, str]]) -> list[tuple]:
    """8 instructores con la especialidad de `ESPECIALIDADES_INSTRUCTORES`."""
    return [
        (nombre, apellido, especialidad, _fecha_aleatoria(rng, date(2018, 3, 1), date(2025, 8, 1)))
        for (nombre, apellido), especialidad in zip(nombres, ESPECIALIDADES_INSTRUCTORES, strict=True)
    ]


def _clases(rng: random.Random) -> list[tuple]:
    """24 clases semanales; cada una en un par (día, horario) distinto, así nunca se superponen."""
    turnos = [(dia, hora) for dia in DIAS_SEMANA[:6] for hora in HORARIOS]
    rng.shuffle(turnos)
    filas = []
    for id_instructor, (especialidad, cantidad) in enumerate(
        zip(ESPECIALIDADES_INSTRUCTORES, CLASES_POR_INSTRUCTOR, strict=True), start=1
    ):
        nombres_clase = TIPOS_CLASE[especialidad]
        for i in range(cantidad):
            nombre = nombres_clase[i % len(nombres_clase)]
            dia, hora = turnos.pop()
            filas.append((nombre, id_instructor, dia, hora, rng.choice(CUPOS), SALA_POR_CLASE[nombre]))
    return filas


def _socios(rng: random.Random, nombres: list[tuple[str, str]]) -> list[_Socio]:
    """~60 socios ordenados por fecha de alta (el `id_socio` sigue el orden de llegada)."""
    estados = [estado for estado, cantidad in CANTIDAD_SOCIOS.items() for _ in range(cantidad)]
    rng.shuffle(estados)
    socios = []
    for (nombre, apellido), estado in zip(nombres, estados, strict=True):
        id_plan = rng.choices(range(1, len(PLANES) + 1), weights=PESO_PLANES)[0]
        if PLANES[id_plan - 1].nombre == "Estudiante":
            nacimiento = _fecha_aleatoria(rng, date(2001, 1, 1), date(2008, 6, 30))
        else:
            nacimiento = _fecha_aleatoria(rng, date(1965, 1, 1), date(2004, 12, 31))

        if estado == "activo":
            if rng.random() < 0.78:
                alta = _fecha_aleatoria(rng, date(2023, 1, 1), HISTORY_START - timedelta(days=1))
            else:
                alta = _fecha_aleatoria(rng, HISTORY_START, date(2026, 9, 20))
            fin = REFERENCE_DATE
        elif estado == "congelado":
            alta = _fecha_aleatoria(rng, date(2024, 1, 1), date(2026, 6, 30))
            fin = INICIO_CONGELAMIENTO - timedelta(days=1)
        else:
            alta = _fecha_aleatoria(rng, date(2023, 6, 1), HISTORY_START - timedelta(days=1))
            fin = _fecha_aleatoria(rng, date(2026, 5, 10), date(2026, 8, 25))

        socios.append(_Socio(
            nombre, apellido, nacimiento, alta, id_plan, estado, fin,
            tasa_asistencia=rng.uniform(0.65, 0.95),
        ))
    socios.sort(key=lambda s: s.fecha_alta)
    return socios


def _inscribir_en_clases(rng: random.Random, socios: list[_Socio], clases: list[tuple]) -> None:
    """Elige a qué clases va cada socio, sin superar el cupo de ninguna.

    La cantidad sale del plan (`clases_por_semana`, con tope `MAX_CLASES_POR_SOCIO`); las
    clases del instructor destacado pesan más.
    """
    cupo_libre = {i: fila[4] for i, fila in enumerate(clases, start=1)}
    pesos = {
        i: PESO_CLASE_DESTACADA if fila[1] == INSTRUCTOR_DESTACADO else 1.0
        for i, fila in enumerate(clases, start=1)
    }
    for socio in socios:
        cantidad = max(1, min(PLANES[socio.id_plan - 1].clases_por_semana, MAX_CLASES_POR_SOCIO))
        for _ in range(cantidad):
            candidatas = [i for i in cupo_libre if cupo_libre[i] > 0 and i not in socio.clases]
            elegida = rng.choices(candidatas, weights=[pesos[i] for i in candidatas])[0]
            socio.clases.append(elegida)
            cupo_libre[elegida] -= 1
        socio.clases.sort()


def _asistencias(
    rng: random.Random, socios: list[_Socio], clases: list[tuple], con_faltas_recientes: list[int]
) -> list[tuple]:
    """Una fila por cada clase reservada, ordenadas por fecha, clase y socio.

    Cada semana el socio asiste a cada una de sus clases con su `tasa_asistencia`. Si no
    asiste, fuera del último mes la falta queda registrada con `PROB_FALTA_REGISTRADA`; dentro
    del último mes, solo para los socios de `con_faltas_recientes` (que son activos).
    """
    filas = []
    for id_socio, socio in enumerate(socios, start=1):
        desde = max(socio.fecha_alta, HISTORY_START)
        plantado = id_socio in con_faltas_recientes
        propias = []
        for id_clase in socio.clases:
            for fecha in _fechas_de_clase(clases[id_clase - 1][2], desde, socio.fin_actividad):
                if rng.random() < socio.tasa_asistencia:
                    propias.append((id_socio, id_clase, fecha, True))
                elif fecha >= INICIO_ULTIMO_MES:
                    if plantado:
                        propias.append((id_socio, id_clase, fecha, False))
                elif rng.random() < PROB_FALTA_REGISTRADA:
                    propias.append((id_socio, id_clase, fecha, False))
        if plantado and not any(not p and f >= INICIO_ULTIMO_MES for _, _, f, p in propias):
            # Garantiza al menos una falta en la ventana: la primera clase reciente pasa a falta.
            i = next(i for i, (_, _, f, _) in enumerate(propias) if f >= INICIO_ULTIMO_MES)
            propias[i] = (*propias[i][:3], False)
        filas.extend(propias)
    filas.sort(key=lambda a: (a[2], a[1], a[0]))
    return filas


def _pagos(
    rng: random.Random, socios: list[_Socio], vencidos: list[int], pendientes: list[int]
) -> list[tuple]:
    """Una cuota por socio y mes, desde su alta (o abril) hasta su último mes de actividad.

    La cuota se paga durante su mes (`fecha_pago` en los primeros días desde el alta o el
    inicio del mes). Los socios congelados no pagan septiembre (cuota congelada) y los de baja
    pagan hasta el mes en que se van. `medio_pago` es obligatorio en el esquema, así que las
    cuotas impagas llevan el medio con el que el socio suele pagar.
    """
    filas = []
    for id_socio, socio in enumerate(socios, start=1):
        precio = PLANES[socio.id_plan - 1].precio_mensual
        ultimo_mes = socio.fin_actividad.replace(day=1)
        for mes in _meses(max(socio.fecha_alta, HISTORY_START), ultimo_mes):
            medio = rng.choice(MEDIOS_PAGO)
            if mes == MES_VENCIDO and id_socio in vencidos:
                filas.append((id_socio, None, precio, mes, medio, "vencido"))
            elif mes == MES_REFERENCIA and id_socio in pendientes:
                filas.append((id_socio, None, precio, mes, medio, "pendiente"))
            else:
                desde = max(mes, socio.fecha_alta)
                hasta = min(desde + timedelta(days=9), _fin_de_mes(mes), REFERENCE_DATE)
                filas.append((id_socio, _fecha_aleatoria(rng, desde, hasta), precio, mes, medio, "pagado"))
    filas.sort(key=lambda p: (p[3], p[0]))
    return filas


def _equipamiento(rng: random.Random) -> list[tuple]:
    """32 equipos de los tipos del manual, con los estados y atrasos plantados."""
    filas = []
    for tipo, cantidad in CANTIDAD_EQUIPOS.items():
        frecuencia = TIPOS_EQUIPO[tipo]
        for numero in range(1, cantidad + 1):
            clave = (tipo, numero)
            estado = ESTADOS_EQUIPOS_PLANTADOS.get(clave, "operativo")
            if clave in EQUIPOS_NUEVOS:
                adquisicion, ultimo = EQUIPOS_NUEVOS[clave], None
            else:
                adquisicion = _fecha_aleatoria(rng, date(2021, 1, 1), date(2025, 12, 31))
                atraso = CINTAS_ATRASADAS.get(clave, rng.randint(0, frecuencia - 1))
                ultimo = REFERENCE_DATE - timedelta(days=atraso)
            filas.append((f"{tipo} {numero:02d}", tipo, SALA_POR_TIPO_EQUIPO[tipo], estado, adquisicion, ultimo))
    return filas


def _verificar_instructor_destacado(clases: list[tuple], asistencias: list[tuple]) -> None:
    """Falla si el instructor destacado no supera al segundo por `MARGEN_DESTACADO`.

    Se comprueba con la ventana del último mes y con la misma ventana corrida un día (por si
    una consulta toma `REFERENCE_DATE - 30`), para que la respuesta de S02 no sea frágil.
    """
    for inicio in (INICIO_ULTIMO_MES, INICIO_ULTIMO_MES - timedelta(days=1)):
        conteo = Counter(
            clases[id_clase - 1][1]
            for _, id_clase, fecha, presente in asistencias
            if presente and fecha >= inicio
        )
        (primero, n1), (_, n2) = conteo.most_common(2)
        if primero != INSTRUCTOR_DESTACADO or n1 < n2 * MARGEN_DESTACADO:
            raise RuntimeError(f"Escenario S02 no plantado: {conteo.most_common(3)}")


def generar_datos() -> dict[str, list[tuple]]:
    """Genera las filas de las 7 tablas de `public`, sin acceder a la base.

    Returns:
        Tabla → lista de tuplas con los valores de `COLUMNAS[tabla]`, en el orden de carga.
        Dos llamadas devuelven exactamente el mismo resultado.
    """
    rng = random.Random(SEED)
    personas = rng.sample([(n, a) for n in NOMBRES for a in APELLIDOS], 8 + sum(CANTIDAD_SOCIOS.values()))

    instructores = _instructores(rng, personas[:8])
    clases = _clases(rng)
    socios = _socios(rng, personas[8:])
    _inscribir_en_clases(rng, socios, clases)

    activos = [i for i, s in enumerate(socios, start=1) if s.estado == "activo"]
    con_faltas = rng.sample([i for i in activos if socios[i - 1].fecha_alta < INICIO_ULTIMO_MES],
                            SOCIOS_CON_FALTAS_RECIENTES)
    vencidos = rng.sample([i for i in activos if socios[i - 1].fecha_alta < MES_VENCIDO], PAGOS_VENCIDOS)
    pendientes = rng.sample(activos, PAGOS_PENDIENTES)

    asistencias = _asistencias(rng, socios, clases, con_faltas)
    _verificar_instructor_destacado(clases, asistencias)

    return {
        "planes": _planes(),
        "instructores": instructores,
        "socios": [
            (s.nombre, s.apellido, f"{_sin_tildes(s.nombre)}.{_sin_tildes(s.apellido)}@correo.com",
             s.fecha_nacimiento, s.fecha_alta, s.id_plan, s.estado)
            for s in socios
        ],
        "clases": clases,
        "asistencias": asistencias,
        "pagos": _pagos(rng, socios, vencidos, pendientes),
        "equipamiento": _equipamiento(rng),
    }
