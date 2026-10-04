"""Texto de los tres PDFs sintéticos del RAG (research R8).

Los plazos, frecuencias y recomendaciones salen de `catalog.py`, la misma fuente que usan el
generador de datos y la batería de evaluación, así que el texto no puede contradecir a la base.

Reglas de redacción (principio III y test T022):

- Sin precios, montos, cupos ni datos de socios, instructores o equipos concretos: viven en la base.
- Los textos de `CLAVES_HECHOS` aparecen literales ("48 horas", no "dos días").
- Cada sección del manual de equipamiento se llama igual que `equipamiento.tipo` y menciona solo
  su propia frecuencia de mantenimiento.
- Ningún documento trata el estacionamiento (la pregunta B08 espera que no esté cubierto).
- Cada párrafo nombra su tema ("la cinta de correr", "el congelamiento") para que un chunk
  suelto se entienda sin el título de la sección.

Las reglas de la cuota coinciden con los datos (research R7): la cuota del mes en curso figura como
pendiente, vence pasados `mora_dias_para_vencido` días del fin de su mes, y los socios congelados
no pagan el mes congelado.
"""

from dataclasses import dataclass

from gym_agent.synthetic.catalog import (
    COMIDA_PRE_ENTRENAMIENTO,
    COMIDA_PRE_ENTRENAMIENTO_HORAS,
    DOCUMENTOS,
    REGLAS,
    TIPOS_EQUIPO,
    Documento,
)


@dataclass(frozen=True)
class Seccion:
    """Un título de sección y sus párrafos."""

    titulo: str
    parrafos: tuple[str, ...]


Pagina = tuple[Seccion, ...]
"""Secciones de una página del PDF; el renderizador inserta un salto de página entre páginas."""


@dataclass(frozen=True)
class ContenidoDocumento:
    """Contenido de un PDF: el documento del catálogo y sus páginas (de 3 a 6)."""

    documento: Documento
    paginas: tuple[Pagina, ...]


# --- Reglamento interno ------------------------------------------------------

_R = REGLAS

_REGLAMENTO: tuple[Pagina, ...] = (
    (
        Seccion(
            "Alcance",
            (
                "Este reglamento establece las normas que rigen la relación entre el gimnasio y sus "
                "socios: el pago de la cuota mensual, el congelamiento de la membresía, la baja y la "
                "reserva de clases. Al inscribirse, cada socio acepta estas normas.",
                "Los valores de las cuotas y las condiciones de cada plan se informan en recepción y "
                "no forman parte de este reglamento.",
            ),
        ),
        Seccion(
            "Inscripción y apto médico",
            (
                "Para inscribirse, la persona completa la ficha de socio con sus datos personales y un "
                "correo electrónico de contacto, elige un plan y presenta un apto médico vigente. El "
                "apto médico se renueva una vez por año.",
                "La fecha de alta es el día en que se completa la inscripción. Desde ese día el socio "
                "puede usar las instalaciones y reservar clases.",
            ),
        ),
        Seccion(
            "Estados de la membresía",
            (
                "Una membresía puede estar activa, congelada o dada de baja. El socio con la membresía "
                "activa puede asistir a clases y usar la sala de musculación y la sala de cardio.",
                "El socio con la membresía congelada no puede asistir a clases ni usar las "
                "instalaciones mientras dure el congelamiento. El socio dado de baja deja de tener "
                "acceso al gimnasio a partir de la fecha de baja.",
            ),
        ),
        Seccion(
            "Acceso al gimnasio",
            (
                "El ingreso se registra en recepción con la credencial de socio, que es personal e "
                "intransferible. La asistencia a cada clase reservada se registra al comienzo de la "
                "clase.",
            ),
        ),
    ),
    (
        Seccion(
            "Pago de la cuota mensual",
            (
                "La cuota de cada mes se abona durante ese mismo mes, en recepción o por los medios de "
                "pago habilitados. Cada pago corresponde a un único mes y queda registrado con su "
                "fecha y su medio de pago.",
                "Mientras transcurre el mes, la cuota que todavía no se abonó figura como pendiente. "
                "Estar con la cuota pendiente no tiene ninguna consecuencia: el socio puede abonarla "
                "en cualquier momento del mes.",
            ),
        ),
        Seccion(
            "Plazo de gracia y cuota vencida",
            (
                "Si al terminar el mes la cuota no fue abonada, el socio tiene un plazo de gracia de "
                f"{_R.mora_dias_para_vencido} días corridos para regularizarla. Pasados esos "
                f"{_R.mora_dias_para_vencido} días, la cuota se considera vencida y el socio entra en "
                "mora.",
                "Por ejemplo, la cuota de un mes que no se abonó sigue pendiente hasta el día "
                f"{_R.mora_dias_para_vencido} del mes siguiente y figura como vencida a partir del día "
                f"{_R.mora_dias_para_vencido + 1}.",
            ),
        ),
        Seccion(
            "Mora y suspensión del acceso",
            (
                "Un socio en mora puede seguir entrenando durante "
                f"{_R.mora_dias_suspension} días, contados desde que la cuota venció. Si pasados esos "
                f"{_R.mora_dias_suspension} días la cuota sigue vencida, se suspende el acceso al "
                "gimnasio y a las clases.",
                "Para regularizar la mora hay que abonar todas las cuotas vencidas. El acceso se "
                "rehabilita en el momento del pago y la suspensión no genera recargos.",
            ),
        ),
    ),
    (
        Seccion(
            "Congelamiento de la cuota",
            (
                "El congelamiento permite pausar la membresía por viaje, salud u otro motivo de fuerza "
                "mayor sin perder la condición de socio. Cada congelamiento dura como máximo "
                f"{_R.congelamiento_max_dias} días corridos, y cada socio puede congelar su membresía "
                f"hasta {_R.congelamiento_max_veces_anio} veces por año calendario.",
                "El congelamiento se pide en recepción o por correo electrónico con al menos "
                f"{_R.congelamiento_aviso_horas} horas de anticipación a la fecha de inicio. Un pedido "
                f"hecho con menos de {_R.congelamiento_aviso_horas} horas de anticipación empieza a "
                "regir recién cuando se cumple ese plazo.",
                "Mientras la membresía está congelada no se abona la cuota del período congelado. A "
                "cambio, el socio no puede asistir a clases ni usar las instalaciones hasta que "
                "termine el congelamiento.",
                "El congelamiento no anula las cuotas vencidas anteriores: si el socio estaba en mora "
                "al congelar, debe regularizar esas cuotas igual. Al terminar el plazo, la membresía "
                "vuelve a estar activa de forma automática y el socio retoma el pago de la cuota "
                "mensual.",
            ),
        ),
        Seccion(
            "Baja de la membresía",
            (
                "La baja se pide por escrito en recepción o por correo electrónico con al menos "
                f"{_R.baja_aviso_dias} días de anticipación. Hasta la fecha de baja, la membresía "
                "sigue activa y el socio puede seguir asistiendo.",
                "Para que la baja se haga efectiva, el socio debe tener abonadas todas las cuotas "
                "hasta el mes de la baja inclusive. Después de la baja no se registran asistencias ni "
                "pagos nuevos; para volver, la persona debe inscribirse otra vez.",
            ),
        ),
    ),
    (
        Seccion(
            "Reserva de clases",
            (
                "Las clases grupales requieren reserva previa, que se hace en recepción o por la "
                "aplicación del gimnasio. Cada clase tiene un cupo máximo de participantes; cuando "
                "se completa, no se aceptan nuevas reservas.",
            ),
        ),
        Seccion(
            "Cancelación de clases",
            (
                "Si el socio no puede asistir a una clase reservada, debe cancelar la reserva con al "
                f"menos {_R.cancelacion_anticipacion_horas} horas de anticipación al inicio de la "
                "clase, para que otro socio pueda ocupar el lugar.",
                "Una cancelación hecha con menos de "
                f"{_R.cancelacion_anticipacion_horas} horas de anticipación no se considera válida y "
                "cuenta como falta sin aviso.",
            ),
        ),
        Seccion(
            "Faltas sin aviso",
            (
                "Cuando un socio no asiste a una clase reservada y no la canceló a tiempo, se "
                "registra una falta sin aviso.",
                f"Al acumular {_R.faltas_sin_aviso_limite} faltas sin aviso en un mismo mes "
                "calendario, el socio pierde la prioridad de reserva durante el mes siguiente: solo "
                "puede reservar una clase el mismo día en que se dicta, si quedan lugares libres.",
                "Las faltas sin aviso no generan cargos adicionales ni modifican la cuota. Un socio "
                "que no puede asistir durante un período largo puede pedir el congelamiento de la "
                "cuota.",
            ),
        ),
    ),
    (
        Seccion(
            "Normas de convivencia",
            (
                "Es obligatorio usar ropa y calzado deportivo y llevar una toalla personal para apoyar "
                "sobre los equipos. Después de usar un equipo, el socio debe limpiarlo y dejarlo libre "
                "para el siguiente. Los discos, las mancuernas y las barras se devuelven a su lugar al "
                "terminar.",
                "Si un equipo funciona mal, el socio debe dejar de usarlo y avisar en recepción. Los "
                "equipos en mantenimiento o fuera de servicio están señalizados y no deben usarse.",
                "Los lockers se usan solo durante la permanencia en el gimnasio y deben quedar libres "
                "al retirarse. El gimnasio no se responsabiliza por los objetos olvidados.",
            ),
        ),
        Seccion(
            "Consultas y cambios al reglamento",
            (
                "Las consultas sobre este reglamento se hacen en recepción. Los cambios al reglamento "
                "se comunican a los socios por correo electrónico antes de entrar en vigencia.",
            ),
        ),
    ),
)

# --- Guía de rutinas y nutrición ---------------------------------------------

_GUIA: tuple[Pagina, ...] = (
    (
        Seccion(
            "Introducción",
            (
                "Esta guía reúne recomendaciones generales de entrenamiento y alimentación para los "
                "socios del gimnasio. No reemplaza la consulta con un profesional de la salud: ante "
                "una lesión, un dolor persistente o una condición médica, conviene consultar al médico "
                "antes de empezar.",
            ),
        ),
        Seccion(
            "Cómo elegir el nivel",
            (
                "Nivel principiante: personas que nunca entrenaron o que retoman la actividad después "
                "de varios meses sin entrenar.",
                "Nivel intermedio: personas que entrenan de forma regular desde hace al menos tres "
                "meses y dominan la técnica de los ejercicios básicos.",
                "Nivel avanzado: personas con más de un año de entrenamiento continuo que buscan "
                "objetivos específicos de fuerza, volumen muscular o rendimiento.",
            ),
        ),
        Seccion(
            "Calentamiento",
            (
                "Toda sesión de entrenamiento empieza con un calentamiento de 5 a 10 minutos de cardio "
                "suave en la cinta, la bicicleta fija o el elíptico, seguido de movilidad articular de "
                "hombros, caderas, rodillas y tobillos.",
                "El calentamiento eleva la temperatura corporal, prepara las articulaciones y reduce el "
                "riesgo de lesiones. Antes de un ejercicio con carga, conviene hacer una serie liviana "
                "del mismo movimiento.",
            ),
        ),
    ),
    (
        Seccion(
            "Rutina para principiantes",
            (
                "Para principiantes se recomienda entrenar "
                f"{REGLAS.rutina_principiante_dias_semana} días por semana, en días no consecutivos, "
                "con sesiones de 45 a 60 minutos. Cada sesión trabaja el cuerpo completo, para "
                "aprender la técnica de los movimientos básicos y crear el hábito de entrenar.",
                "Ejercicios de la rutina para principiantes, en este orden:",
                "- Sentadilla con peso corporal o con mancuerna: 3 series de 12 repeticiones.",
                "- Press de pecho en máquina: 3 series de 12 repeticiones.",
                "- Remo con mancuerna a una mano: 3 series de 12 repeticiones por lado.",
                "- Estocadas alternadas: 3 series de 10 repeticiones por pierna.",
                "- Plancha abdominal: 3 series de 20 a 30 segundos.",
                "- Cardio final: 10 a 15 minutos de bicicleta fija o elíptico a ritmo moderado.",
            ),
        ),
        Seccion(
            "Progresión para principiantes",
            (
                "Durante las primeras semanas, el principiante prioriza la técnica sobre el peso. "
                "Cuando completa todas las series y repeticiones con buena técnica, puede aumentar la "
                "carga de a poco.",
                "Después de dos o tres meses de entrenamiento regular, el principiante puede pasar a "
                "la rutina de nivel intermedio.",
            ),
        ),
    ),
    (
        Seccion(
            "Rutina para nivel intermedio",
            (
                "Para el nivel intermedio se recomienda entrenar 4 días por semana con una rutina "
                "dividida en tren superior y tren inferior, alternando dos sesiones de cada una, con "
                "sesiones de alrededor de una hora.",
                "Tren superior: press de banca, remo con barra, press militar con mancuernas, "
                "dominadas asistidas y ejercicios de bíceps y tríceps, de 3 a 4 series de 8 a 10 "
                "repeticiones.",
                "Tren inferior: sentadilla con barra, peso muerto rumano, prensa de piernas, "
                "estocadas y elevación de talones, de 3 a 4 series de 8 a 10 repeticiones.",
            ),
        ),
        Seccion(
            "Rutina para nivel avanzado",
            (
                "Para el nivel avanzado se recomienda entrenar 5 días por semana con una rutina "
                "dividida por grupos musculares: pecho y tríceps, espalda y bíceps, piernas, hombros "
                "y abdomen, y una sesión de acondicionamiento o entrenamiento de alta intensidad.",
                "En el nivel avanzado conviene planificar el entrenamiento por ciclos, alternando "
                "semanas de mayor carga con semanas de descarga, y revisar los objetivos con un "
                "instructor cada dos o tres meses.",
            ),
        ),
    ),
    (
        Seccion(
            "Descanso y recuperación",
            (
                "Los músculos se recuperan y se fortalecen durante el descanso, no durante el "
                "entrenamiento. Se recomienda dormir entre 7 y 9 horas por noche y no entrenar el "
                "mismo grupo muscular en días consecutivos.",
                "Entre series, el descanso recomendado es de uno a dos minutos en los ejercicios con "
                "carga y de menos de un minuto en los ejercicios de resistencia o abdominales.",
                "Señales de que falta descanso: cansancio que no se va, dolor muscular que dura varios "
                "días, peor rendimiento y alteraciones del sueño. Ante esas señales conviene bajar la "
                "intensidad durante una semana.",
            ),
        ),
        Seccion(
            "Hidratación",
            (
                "Para mantenerse hidratado, se recomienda tomar agua antes, durante y después del "
                "entrenamiento: un vaso antes de empezar y pequeños sorbos cada 15 a 20 minutos "
                "durante la sesión. En los días de calor o en las clases intensas, la necesidad de "
                "agua aumenta.",
            ),
        ),
    ),
    (
        Seccion(
            "Alimentación antes de entrenar",
            (
                "La comida antes de entrenar debe basarse en "
                f"{COMIDA_PRE_ENTRENAMIENTO}, que son la principal fuente de energía para el "
                f"ejercicio, y conviene hacerla {COMIDA_PRE_ENTRENAMIENTO_HORAS} antes de entrenar.",
                "Ejemplos de comida antes de entrenar: avena con fruta, pan integral con queso "
                "untable, arroz con verduras o una banana. Conviene que sea una comida liviana, con "
                "poca grasa y poca fibra, para evitar molestias durante el ejercicio.",
            ),
        ),
        Seccion(
            "Alimentación después de entrenar",
            (
                "Después de entrenar se recomienda combinar proteínas, como huevo, carne magra, "
                "pollo, pescado, legumbres o yogur, con una porción de cereales, frutas o verduras "
                "para reponer energía y ayudar a la recuperación muscular.",
                "La comida después de entrenar se hace dentro de las dos horas posteriores a la "
                "sesión. Si el entrenamiento fue de noche, puede ser la cena.",
            ),
        ),
        Seccion(
            "Recomendaciones generales de alimentación",
            (
                "Se recomienda repartir la alimentación en cuatro comidas al día, incluir frutas y "
                "verduras en cada una y limitar los productos ultraprocesados y las bebidas "
                "azucaradas. Ante objetivos específicos, como bajar de peso o aumentar la masa "
                "muscular, conviene consultar a un nutricionista.",
            ),
        ),
    ),
)

# --- Manual de uso y mantenimiento del equipamiento --------------------------

_NOMBRE_CON_ARTICULO = {
    "Cinta de correr": "la cinta de correr",
    "Bicicleta fija": "la bicicleta fija",
    "Elíptico": "el elíptico",
    "Máquina de pesas": "la máquina de pesas",
}


def _frecuencias_resumidas() -> str:
    """Enumera la frecuencia de cada tipo ("la cinta de correr cada 30 días, ...") desde el catálogo."""
    partes = [f"{_NOMBRE_CON_ARTICULO[tipo]} cada {dias} días" for tipo, dias in TIPOS_EQUIPO.items()]
    return ", ".join(partes[:-1]) + " y " + partes[-1]


_D = TIPOS_EQUIPO

_MANUAL: tuple[Pagina, ...] = (
    (
        Seccion(
            "Introducción",
            (
                "Este manual describe el uso correcto de los equipos de la sala de cardio y de la sala "
                "de musculación, y la frecuencia con la que cada tipo de equipo recibe mantenimiento "
                "preventivo. Lo aplican los instructores y el personal de mantenimiento, y sirve de "
                "referencia para los socios.",
            ),
        ),
        Seccion(
            "Frecuencia de mantenimiento preventivo",
            (
                "Cada tipo de equipo tiene su propia frecuencia de mantenimiento preventivo: "
                f"{_frecuencias_resumidas()}.",
                "Cada equipo tiene registrada la fecha de su último mantenimiento. Un equipo está "
                "atrasado cuando desde esa fecha pasaron más días que la frecuencia indicada para su "
                "tipo; en ese caso, la revisión se programa lo antes posible.",
                "Los equipos nuevos todavía no tienen un mantenimiento registrado: se revisan por "
                "primera vez cuando se cumple la frecuencia de su tipo contada desde la fecha de "
                "compra.",
            ),
        ),
        Seccion(
            "Estados de un equipo",
            (
                "Un equipo puede estar operativo, en mantenimiento o fuera de servicio. Un equipo "
                "operativo puede usarse normalmente.",
                "Un equipo en mantenimiento está siendo revisado o reparado y vuelve a estar "
                "disponible al terminar el trabajo. Un equipo fuera de servicio tiene una falla que "
                "impide usarlo y espera un repuesto o su reemplazo.",
            ),
        ),
    ),
    (
        Seccion(
            "Cinta de correr",
            (
                "Uso correcto de la cinta de correr: antes de subir, verificar que la banda esté "
                "detenida y sujetar el clip de seguridad a la ropa; si el usuario se cae o se aleja, "
                "el clip detiene la cinta. Empezar caminando a baja velocidad y aumentarla de a poco.",
                "Durante el ejercicio en la cinta de correr, mirar hacia adelante y no sostenerse de "
                "los pasamanos todo el tiempo. Nunca bajar de la cinta con la banda en movimiento: al "
                "terminar, reducir la velocidad hasta que se detenga.",
                "Mantenimiento de la cinta de correr: requiere mantenimiento preventivo cada "
                f"{_D['Cinta de correr']} días. La revisión incluye la lubricación de la banda, el "
                "control de la tensión y de la alineación de la banda, la limpieza del motor y la "
                "prueba del botón de parada de emergencia y del clip de seguridad.",
                "Señales de falla en la cinta de correr: la banda patina o se desvía hacia un costado, "
                "la velocidad no responde a los controles, hay olor a quemado o ruidos fuertes en el "
                "motor.",
            ),
        ),
    ),
    (
        Seccion(
            "Bicicleta fija",
            (
                "Uso correcto de la bicicleta fija: ajustar la altura del asiento para que la rodilla "
                "quede apenas flexionada con el pedal en el punto más bajo, y ajustar las correas de "
                "los pedales. La resistencia se regula con la perilla, de a poco y sin dejar de "
                "pedalear.",
                "Mantenimiento de la bicicleta fija: requiere mantenimiento preventivo cada "
                f"{_D['Bicicleta fija']} días. La revisión incluye el ajuste de pedales y bielas, el "
                "control de la correa de transmisión y del sistema de resistencia, el ajuste del "
                "asiento y la limpieza general.",
                "Señales de falla en la bicicleta fija: ruidos metálicos al pedalear, pedales flojos o "
                "una resistencia que no cambia al mover la perilla.",
            ),
        ),
        Seccion(
            "Elíptico",
            (
                "Uso correcto del elíptico: subir con el equipo detenido, apoyando primero un pie y "
                "después el otro sobre los pedales, y tomarse de los brazos móviles. Mantener la "
                "espalda recta y no invertir el sentido del movimiento de golpe.",
                "Mantenimiento del elíptico: requiere mantenimiento preventivo cada "
                f"{_D['Elíptico']} días. La revisión incluye la lubricación de los rieles y las "
                "articulaciones, el control de los rodamientos, el ajuste de los tornillos de los "
                "brazos y la limpieza de los rieles.",
                "Señales de falla en el elíptico: chirridos, movimiento a los saltos o brazos con "
                "juego.",
            ),
        ),
    ),
    (
        Seccion(
            "Máquina de pesas",
            (
                "Uso correcto de la máquina de pesas: ajustar el asiento y los apoyos a la altura del "
                "usuario antes de empezar y elegir la carga con el pasador, verificando que quede "
                "insertado por completo en la placa.",
                "Durante el ejercicio en la máquina de pesas, hacer movimientos controlados en la ida "
                "y en la vuelta, sin soltar el peso de golpe. Nunca poner las manos entre las placas "
                "ni cerca de las poleas en movimiento.",
                "Mantenimiento de la máquina de pesas: requiere mantenimiento preventivo cada "
                f"{_D['Máquina de pesas']} días. La revisión incluye el control de cables y poleas "
                "para detectar desgaste, la lubricación de las guías, el ajuste de pasadores y "
                "tornillos y la revisión de los tapizados.",
                "Señales de falla en la máquina de pesas: un cable deshilachado, una polea que traba "
                "o placas que no corren libremente. Un cable deshilachado deja la máquina fuera de "
                "servicio de inmediato.",
            ),
        ),
    ),
    (
        Seccion(
            "Qué hacer ante una falla",
            (
                "Ante una falla, el socio deja de usar el equipo de inmediato y avisa a un instructor "
                "o en recepción. Nunca debe intentar repararlo por su cuenta.",
                "El instructor señaliza el equipo para que nadie lo use y registra la falla. El "
                "personal de mantenimiento evalúa el problema: si la reparación puede hacerse en el "
                "momento, el equipo queda en mantenimiento; si hace falta un repuesto o la falla "
                "compromete la seguridad, el equipo queda fuera de servicio hasta su reparación o "
                "reemplazo.",
                "Antes de volver a habilitar un equipo, se prueba su funcionamiento completo y se "
                "actualiza la fecha de su último mantenimiento.",
            ),
        ),
        Seccion(
            "Limpieza diaria",
            (
                "Todos los equipos se limpian al final de cada jornada con un paño húmedo y un "
                "producto no abrasivo, sin rociar líquido sobre los paneles electrónicos. La limpieza "
                "diaria no reemplaza el mantenimiento preventivo.",
            ),
        ),
    ),
)

# --- Índice ------------------------------------------------------------------

CONTENIDOS: dict[str, ContenidoDocumento] = {
    "reglamento_interno": ContenidoDocumento(DOCUMENTOS["reglamento_interno"], _REGLAMENTO),
    "guia_rutinas_nutricion": ContenidoDocumento(DOCUMENTOS["guia_rutinas_nutricion"], _GUIA),
    "manual_equipamiento": ContenidoDocumento(DOCUMENTOS["manual_equipamiento"], _MANUAL),
}
"""Contenido de cada PDF, por id de documento (las mismas claves que `DOCUMENTOS`)."""


def texto_documento(id_documento: str) -> str:
    """Texto plano de un documento: título, títulos de sección y párrafos, separados por líneas en blanco."""
    contenido = CONTENIDOS[id_documento]
    bloques = [contenido.documento.titulo]
    for pagina in contenido.paginas:
        for seccion in pagina:
            bloques.append(seccion.titulo)
            bloques.extend(seccion.parrafos)
    return "\n\n".join(bloques)
