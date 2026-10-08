"""Runner de la evaluación: corre la batería contra el agente real y calcula CE-001 a CE-004.

Uso (desde la raíz del repositorio, con la base levantada y la ingesta hecha)::

    python -m eval.run_eval                                   # 3 corridas completas (~270 llamadas)
    python -m eval.run_eval --solo S01,B01                    # solo esas preguntas, sin criterios
    python -m eval.run_eval --corridas 1 --resumen docs/resultados-evaluacion.md

Por cada pregunta: calcula el hash de las tablas, la hace al agente (forzando `CHAT_MODEL`, sin
modelo de respaldo), lee su línea en la traza, vuelve a calcular el hash y corrige los chequeos. El
juez va al final y solo si los demás pasaron: no se gasta cuota en una respuesta que ya falló. La
traza de la evaluación se escribe en `eval/results/<fecha>-traza.jsonl`, aparte de `logs/traza.jsonl`.

Códigos de salida: 0 si se cumplen los criterios, 1 si alguno no se cumple y 2 si la corrida es
inválida o quedó incompleta (batería inválida, juez igual al agente, base o juez caídos, cuota diaria
agotada). Una pregunta que falla es un resultado; una corrida incompleta no tiene resultado.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg

from eval import battery, judge
from eval.battery import ContieneValoresDeSql, Juez, PreguntaEval, SinVolcadoDeChunks
from eval.checks import Contexto, Intento, ResultadoChequeo, ejecutar_chequeo, fuentes_ok
from eval.criteria import (
    Criterio,
    ResultadoCorrida,
    ResultadoPregunta,
    calcular_criterios,
    duraciones,
    es_modificacion,
    tasa_por_pregunta,
    veredicto,
)
from gym_agent import llm, observability
from gym_agent.config import CHAT_MODEL, EVAL_CORRIDAS, EVAL_PAUSA_S, EVAL_RESULTS_DIR, JUDGE_MODEL
from gym_agent.db import connect_admin, connect_ro
from gym_agent.graph.builder import run_question
from gym_agent.graph.state import RespuestaAgente
from gym_agent.synthetic.loader import hash_tablas

_ERRORES_DE_INFRAESTRUCTURA = (RuntimeError, OSError, psycopg.Error)
"""Fallas de lo que rodea al agente (base, archivos, juez): cortan la corrida como incompleta."""

_MAXIMO_MOTIVO = 90
"""Largo máximo del motivo en la tabla de la consola."""


class CuotaAgotada(RuntimeError):
    """El modelo del agente agotó su cuota diaria: seguir solo produciría fallas falsas."""


def _consola_segura() -> None:
    """Hace que la consola no falle al imprimir un carácter que su codificación no tiene."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _hash_real() -> dict[str, str]:
    """Hash de las tablas de `public`, calculado como administrador."""
    with connect_admin() as conn:
        return hash_tablas(conn)


def _dorada_real(sql: str) -> list[tuple]:
    """Filas de una consulta dorada, ejecutada con el rol de solo lectura."""
    with connect_ro() as conn:
        return battery.ejecutar_dorada(conn, sql)


def _chunks_reales() -> list[str]:
    """Contenido de todos los chunks de `rag.chunks`."""
    with connect_admin() as conn:
        return [fila[0] for fila in conn.execute("SELECT contenido FROM rag.chunks").fetchall()]


def _entero_positivo(texto: str) -> int:
    """Argumento de línea de comandos: un entero mayor que cero."""
    try:
        valor = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{texto}' no es un número entero") from None
    if valor < 1:
        raise argparse.ArgumentTypeError("debe ser 1 o más")
    return valor


def _parser() -> argparse.ArgumentParser:
    """Opciones de la línea de comandos."""
    parser = argparse.ArgumentParser(prog="python -m eval.run_eval", description="Evalúa el agente con la batería.")
    parser.add_argument(
        "--corridas",
        type=_entero_positivo,
        default=EVAL_CORRIDAS,
        help=f"veces que se corre la batería ({EVAL_CORRIDAS})",
    )
    parser.add_argument("--solo", help="IDs separados por coma; corre solo esas preguntas y no calcula criterios")
    parser.add_argument("--resumen", type=Path, help="archivo markdown donde escribir el resumen")
    return parser


def _seleccionar(preguntas: list[PreguntaEval], solo: str | None) -> list[PreguntaEval]:
    """Las preguntas a correr (en el orden de la batería); todas si `solo` es `None`.

    Raises:
        BateriaInvalida: si algún ID de `solo` no existe.
    """
    if solo is None:
        return preguntas
    pedidos = {i.strip() for i in solo.split(",") if i.strip()}
    inexistentes = sorted(pedidos - {p.id for p in preguntas})
    if inexistentes:
        raise battery.BateriaInvalida(f"Preguntas inexistentes en --solo: {', '.join(inexistentes)}")
    return [p for p in preguntas if p.id in pedidos]


def _lineas(ruta: Path) -> list[str]:
    """Líneas de un archivo de traza (ninguna si todavía no existe)."""
    try:
        return ruta.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []


def _leer_traza(ruta: Path, lineas_antes: int) -> dict | None:
    """La línea que la pregunta acaba de agregar a la traza, o `None` si no hay exactamente una nueva.

    Pedir exactamente una línea nueva evita leer por error la de la pregunta anterior cuando la
    actual no llegó a registrarse.
    """
    lineas = _lineas(ruta)
    if len(lineas) != lineas_antes + 1:
        return None
    try:
        traza = json.loads(lineas[-1])
    except json.JSONDecodeError:
        return None
    return traza if isinstance(traza, dict) else None


def _tipo_de_error(traza: dict | None) -> str:
    """Nombre de la excepción que registró la traza (sin su mensaje)."""
    error = str((traza or {}).get("error") or "")
    return error.split(":", 1)[0].strip() or "error desconocido"


def _tablas_modificadas(hashes: Sequence[dict[str, str]]) -> tuple[str, ...]:
    """Tablas cuyo hash difiere del primero en algún momento de la corrida (en orden alfabético)."""
    if not hashes:
        return ()
    base = hashes[0]
    cambiadas = {t for h in hashes[1:] for t in base.keys() | h.keys() if base.get(t) != h.get(t)}
    return tuple(sorted(cambiadas))


def _chequear(
    pregunta: PreguntaEval,
    intento: Intento,
    doradas: dict[tuple[str, int], list[tuple]],
    chunks: Sequence[str],
    juzgar: Callable[..., Any],
) -> list[ResultadoChequeo]:
    """Corrige las fuentes y los chequeos de la pregunta; el juez va al final y solo si el resto pasó."""
    resultados = [fuentes_ok(pregunta.fuentes_esperadas, intento.traza["fuentes_usadas"])]
    for i, chequeo in enumerate(pregunta.chequeos):
        if not isinstance(chequeo, Juez):
            contexto = Contexto(filas=doradas.get((pregunta.id, i)), chunks=chunks)
            resultados.append(ejecutar_chequeo(chequeo, intento, contexto))
    if all(r.ok for r in resultados):
        for chequeo in (c for c in pregunta.chequeos if isinstance(c, Juez)):
            opinion = juzgar(pregunta.pregunta, intento.respuesta.respuesta, chequeo.rubrica)
            resultados.append(ResultadoChequeo("juez", opinion.cumple, "" if opinion.cumple else opinion.motivo))
            if not opinion.cumple:
                break
    return resultados


def _preguntar(
    pregunta: PreguntaEval,
    *,
    ruta_traza: Path,
    preguntar: Callable[[str], RespuestaAgente],
    hash_base: Callable[[], dict[str, str]],
    juzgar: Callable[..., Any],
    doradas: dict[tuple[str, int], list[tuple]],
    chunks: Sequence[str],
    hashes: list[dict[str, str]],
) -> ResultadoPregunta:
    """Hace una pregunta al agente y la corrige.

    Agrega a `hashes` el hash de antes y el de después.

    Raises:
        CuotaAgotada: si la traza muestra que el modelo agotó su cuota diaria.
        JuezNoDisponible: si el juez no responde.
    """
    antes = hash_base()
    lineas_antes = len(_lineas(ruta_traza))
    with llm.solo_modelo(CHAT_MODEL):
        respuesta = preguntar(pregunta.pregunta)
    despues = hash_base()
    hashes.extend([antes, despues])
    traza = _leer_traza(ruta_traza, lineas_antes)
    if "PerDay" in str((traza or {}).get("error") or ""):
        raise CuotaAgotada(f"Se agotó la cuota diaria de {CHAT_MODEL} (pregunta {pregunta.id})")

    if respuesta.fallo:
        chequeos = [ResultadoChequeo("agente", False, f"El agente falló ({_tipo_de_error(traza)})")]
    elif traza is None:
        chequeos = [ResultadoChequeo("traza", False, "No se encontró la línea de traza de esta pregunta")]
    else:
        chequeos = _chequear(pregunta, Intento(respuesta, traza, antes, despues), doradas, chunks, juzgar)
    return ResultadoPregunta(
        id=pregunta.id,
        tipo=pregunta.tipo,
        aprobada=all(c.ok for c in chequeos),
        fuentes_usadas=(traza or {}).get("fuentes_usadas", respuesta.fuentes_usadas),
        es_modificacion=es_modificacion(pregunta),
        duracion_ms=respuesta.duracion_ms,
        respuesta=respuesta.respuesta,
        chequeos=tuple(chequeos),
    )


def _correr(
    seleccion: list[PreguntaEval],
    cantidad_corridas: int,
    corridas: list[ResultadoCorrida],
    dormir: Callable[[float], None],
    **dependencias: Any,
) -> None:
    """Corre la batería `cantidad_corridas` veces y agrega cada corrida a `corridas`.

    Si algo corta la ejecución, la corrida en curso se agrega con lo que alcanzó a responder y la
    excepción sigue su camino. Hay una pausa de `EVAL_PAUSA_S` entre preguntas consecutivas (también
    entre una corrida y la siguiente) y ninguna después de la última.
    """
    total = cantidad_corridas * len(seleccion)
    hechas = 0
    for _ in range(cantidad_corridas):
        resultados: list[ResultadoPregunta] = []
        hashes: list[dict[str, str]] = []
        try:
            for pregunta in seleccion:
                if hechas:
                    dormir(EVAL_PAUSA_S)
                resultado = _preguntar(pregunta, hashes=hashes, **dependencias)
                resultados.append(resultado)
                hechas += 1
                print(f"[{hechas}/{total}] {resultado.id}: {'aprobada' if resultado.aprobada else 'FALLA'}", flush=True)
        finally:
            if resultados:
                corridas.append(ResultadoCorrida(tuple(resultados), _tablas_modificadas(hashes)))


def _recortar(texto: str) -> str:
    """Una sola línea de a lo sumo `_MAXIMO_MOTIVO` caracteres."""
    texto = " ".join(texto.split())
    return texto if len(texto) <= _MAXIMO_MOTIVO else texto[: _MAXIMO_MOTIVO - 3] + "..."


def _filas_por_pregunta(corridas: Sequence[ResultadoCorrida]) -> list[tuple[str, str, str, str, str]]:
    """Una fila por pregunta: ID, tipo, aprobada (`sí`/`no` o `k/N`), fuentes usadas y motivo de la primera falla."""
    tasas = tasa_por_pregunta(corridas)
    filas = []
    for id_, tasa in tasas.items():
        apariciones = [p for c in corridas for p in c.preguntas if p.id == id_]
        aprobada = ("sí" if tasa.aprobadas else "no") if tasa.total == 1 else str(tasa)
        fuentes = "/".join(dict.fromkeys(p.fuentes_usadas for p in apariciones))
        motivo = next((p.motivo for p in apariciones if not p.aprobada), "")
        filas.append((id_, apariciones[0].tipo, aprobada, fuentes, motivo))
    return filas


def _tabla(corridas: Sequence[ResultadoCorrida]) -> str:
    """Tabla de texto para la consola."""
    filas = [("ID", "Tipo", "Aprobada", "Fuentes", "Motivo")] + [
        (*f[:4], _recortar(f[4])) for f in _filas_por_pregunta(corridas)
    ]
    anchos = [max(len(f[i]) for f in filas) for i in range(4)]
    return "\n".join("  ".join(f[i].ljust(anchos[i]) for i in range(4)) + "  " + f[4] for f in filas).rstrip()


def _lineas_de_criterios(criterios: Sequence[Criterio]) -> str:
    """Una línea por criterio para la consola."""
    return "\n".join(f"{c.nombre}  {'cumple    ' if c.cumple else 'NO CUMPLE'}  {c.detalle}" for c in criterios)


def _escapar_celda(texto: str) -> str:
    """Texto seguro para una celda de tabla markdown."""
    return " ".join(texto.split()).replace("|", "\\|")


def _resumen_markdown(
    momento: datetime,
    cantidad_corridas: int,
    criterios: Sequence[Criterio] | None,
    corridas: Sequence[ResultadoCorrida],
) -> str:
    """Resumen en markdown (criterios, tasas por pregunta, modelos y fecha) para copiar al informe."""
    mediana, maxima = duraciones(corridas)
    lineas = [
        "# Resultados de la evaluación",
        "",
        f"- Fecha: {momento.isoformat(timespec='seconds')}",
        f"- Modelo del agente: `{CHAT_MODEL}`",
        f"- Modelo del juez: `{JUDGE_MODEL}`",
        f"- Corridas: {cantidad_corridas} de {len(corridas[0].preguntas) if corridas else 0} preguntas",
        f"- Duración por pregunta: mediana {mediana} ms, máxima {maxima} ms",
        "",
        "## Criterios",
        "",
    ]
    if criterios is None:
        lineas.append("No se calcularon (se usó `--solo`).")
    else:
        lineas += ["| Criterio | Resultado | Detalle |", "|----------|-----------|---------|"]
        lineas += [
            f"| {c.nombre} | {'cumple' if c.cumple else 'NO cumple'} | {_escapar_celda(c.detalle)} |" for c in criterios
        ]
    lineas += [
        "",
        "## Tasa de aciertos por pregunta",
        "",
        "| ID | Tipo | Aprobada | Fuentes usadas | Motivo |",
        "|----|------|----------|----------------|--------|",
    ]
    lineas += [f"| {' | '.join(_escapar_celda(c) for c in fila)} |" for fila in _filas_por_pregunta(corridas)]
    return "\n".join(lineas) + "\n"


def _datos_json(
    momento: datetime,
    cantidad_corridas: int,
    solo: list[str] | None,
    corridas: Sequence[ResultadoCorrida],
    criterios: Sequence[Criterio] | None,
    motivo_incompleta: str | None,
) -> dict[str, Any]:
    """Detalle completo de la evaluación, para guardar en `eval/results/`."""
    mediana, maxima = duraciones(corridas)
    return {
        "fecha": momento.isoformat(timespec="seconds"),
        "modelo_agente": CHAT_MODEL,
        "modelo_juez": JUDGE_MODEL,
        "cantidad_corridas": cantidad_corridas,
        "solo": solo,
        "completa": motivo_incompleta is None,
        "motivo_incompleta": motivo_incompleta,
        "criterios": None
        if criterios is None
        else [{"nombre": c.nombre, "cumple": c.cumple, "detalle": c.detalle, "valor": c.valor} for c in criterios],
        "tasa_por_pregunta": {id_: str(t) for id_, t in tasa_por_pregunta(corridas).items()},
        "duracion_mediana_ms": mediana,
        "duracion_maxima_ms": maxima,
        "corridas": [
            {
                "numero": n,
                "tablas_modificadas": list(c.tablas_modificadas),
                "preguntas": [
                    {
                        "id": p.id,
                        "tipo": p.tipo,
                        "aprobada": p.aprobada,
                        "fuentes_usadas": p.fuentes_usadas,
                        "duracion_ms": p.duracion_ms,
                        "motivo": p.motivo,
                        "chequeos": [{"tipo": r.tipo, "ok": r.ok, "detalle": r.detalle} for r in p.chequeos],
                        "respuesta": p.respuesta,
                    }
                    for p in c.preguntas
                ],
            }
            for n, c in enumerate(corridas, start=1)
        ],
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    bateria: Path | None = None,
    dir_resultados: Path | None = None,
    preguntar: Callable[[str], RespuestaAgente] | None = None,
    hash_base: Callable[[], dict[str, str]] | None = None,
    juzgar: Callable[..., Any] | None = None,
    ejecutar_dorada: Callable[[str], list[tuple]] | None = None,
    leer_chunks: Callable[[], Sequence[str]] | None = None,
    dormir: Callable[[float], None] | None = None,
    ahora: Callable[[], datetime] | None = None,
) -> int:
    """Corre la evaluación y devuelve el código de salida (0, 1 o 2).

    Los parámetros con nombre son las dependencias: por defecto son las reales (el agente, la base,
    el juez y el reloj); los tests pasan funciones falsas.

    Args:
        argv: argumentos de la línea de comandos (`--corridas`, `--solo`, `--resumen`).
        bateria: archivo YAML con las preguntas.
        dir_resultados: carpeta del JSON y de la traza de la evaluación.
        preguntar: reemplazo de `run_question`.
        hash_base: reemplazo del hash de las tablas de `public`.
        juzgar: reemplazo de `eval.judge.juzgar`.
        ejecutar_dorada: reemplazo que ejecuta una consulta dorada y devuelve sus filas.
        leer_chunks: reemplazo que devuelve el contenido de `rag.chunks`.
        dormir: reemplazo de `time.sleep`.
        ahora: reemplazo del reloj (la fecha del JSON y de los nombres de archivo).

    Returns:
        0 si se cumplen los criterios (o, con `--solo`, si todas las preguntas aprobaron); 1 si no;
        2 si la corrida es inválida o quedó incompleta.
    """
    _consola_segura()
    args = _parser().parse_args(argv)
    preguntar = preguntar or run_question
    hash_base = hash_base or _hash_real
    juzgar = juzgar or judge.juzgar
    ejecutar_dorada = ejecutar_dorada or _dorada_real
    leer_chunks = leer_chunks or _chunks_reales
    dormir = dormir or time.sleep
    momento = (ahora or datetime.now)()
    dir_resultados = Path(dir_resultados) if dir_resultados is not None else EVAL_RESULTS_DIR
    sello = momento.strftime("%Y-%m-%dT%H-%M-%S")

    # Todo lo que puede estar mal en la batería o en la base se descubre antes de gastar cuota.
    try:
        judge.verificar_modelos(CHAT_MODEL, JUDGE_MODEL)
        preguntas = battery.cargar_bateria(bateria or battery.BATTERY_PATH)
        seleccion = _seleccionar(preguntas, args.solo)
        doradas = {
            (p.id, i): ejecutar_dorada(c.sql)
            for p in seleccion
            for i, c in enumerate(p.chequeos)
            if isinstance(c, ContieneValoresDeSql)
        }
        necesita_chunks = any(isinstance(c, SinVolcadoDeChunks) for p in seleccion for c in p.chequeos)
        chunks = leer_chunks() if necesita_chunks else ()
    except (ValueError, *_ERRORES_DE_INFRAESTRUCTURA) as e:
        print(f"Corrida inválida: {e}")
        return 2

    ruta_traza = dir_resultados / f"{sello}-traza.jsonl"
    traza_original = observability.TRAZA_PATH
    observability.TRAZA_PATH = ruta_traza
    corridas: list[ResultadoCorrida] = []
    motivo_incompleta: str | None = None
    try:
        _correr(
            seleccion,
            args.corridas,
            corridas,
            dormir,
            ruta_traza=ruta_traza,
            preguntar=preguntar,
            hash_base=hash_base,
            juzgar=juzgar,
            doradas=doradas,
            chunks=chunks,
        )
    except KeyboardInterrupt:
        motivo_incompleta = "interrumpida por el usuario"
    except _ERRORES_DE_INFRAESTRUCTURA as e:
        motivo_incompleta = f"{type(e).__name__}: {e}"
    finally:
        observability.TRAZA_PATH = traza_original

    criterios = None
    if motivo_incompleta is None and args.solo is None:
        criterios = calcular_criterios(preguntas, corridas)

    dir_resultados.mkdir(parents=True, exist_ok=True)
    ruta_json = dir_resultados / f"{sello}.json"
    solo = [p.id for p in seleccion] if args.solo is not None else None
    datos = _datos_json(momento, args.corridas, solo, corridas, criterios, motivo_incompleta)
    ruta_json.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    if corridas:
        print(_tabla(corridas))
        print()
    print(f"Detalle guardado en {ruta_json}")

    if motivo_incompleta is not None:
        print(f"Corrida incompleta: {motivo_incompleta}. No se calcularon criterios.")
        if args.resumen is not None:
            print("No se escribió el resumen porque la corrida quedó incompleta.")
        return 2

    if args.resumen is not None:
        args.resumen.parent.mkdir(parents=True, exist_ok=True)
        args.resumen.write_text(_resumen_markdown(momento, args.corridas, criterios, corridas), encoding="utf-8")
        print(f"Resumen guardado en {args.resumen}")

    if criterios is None:
        return 0 if all(p.aprobada for c in corridas for p in c.preguntas) else 1
    print(_lineas_de_criterios(criterios))
    codigo = veredicto(criterios)
    print("Se cumplen los cuatro criterios." if codigo == 0 else "No se cumplen todos los criterios.")
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
