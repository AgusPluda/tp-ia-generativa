"""Renderizado de los PDFs sintéticos con `reportlab` (research R8).

Se usa el modo invariante (`invariant=1`): la fecha de creación y el identificador del archivo
quedan fijos, así que dos corridas producen exactamente los mismos bytes (test T024) y los PDFs
versionados no cambian si no cambia el texto.

Los estilos están elegidos para que `pypdf` (modo `layout`) recupere bien los párrafos:

- Texto alineado a la izquierda y sin división en sílabas, para que ninguna palabra se corte.
- Espacio después de cada párrafo mayor que una línea: `pypdf` lo devuelve como una línea en
  blanco, que es lo que usa el chunking para separar párrafos.
- Poco espacio entre un título de sección y su primer párrafo: quedan en el mismo bloque, así el
  título viaja dentro del chunk.
"""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate

from gym_agent.synthetic.pdf_content import CONTENIDOS, ContenidoDocumento

_TITULO = ParagraphStyle("Titulo", fontName="Helvetica-Bold", fontSize=18, leading=22, spaceAfter=16)
_SECCION = ParagraphStyle(
    "Seccion", fontName="Helvetica-Bold", fontSize=13, leading=16, spaceBefore=14, spaceAfter=3,
    keepWithNext=1,
)
_CUERPO = ParagraphStyle("Cuerpo", fontName="Helvetica", fontSize=10.5, leading=14, spaceAfter=10)

_AUTOR = "Gimnasio (documento sintético del TP)"


def _elementos(contenido: ContenidoDocumento) -> list[Flowable]:
    """Título del documento y, por página, sus secciones; un salto de página entre páginas."""
    elementos: list[Flowable] = [Paragraph(escape(contenido.documento.titulo), _TITULO)]
    for numero, pagina in enumerate(contenido.paginas):
        if numero > 0:
            elementos.append(PageBreak())
        for seccion in pagina:
            elementos.append(Paragraph(escape(seccion.titulo), _SECCION))
            elementos.extend(Paragraph(escape(parrafo), _CUERPO) for parrafo in seccion.parrafos)
    return elementos


def renderizar_pdfs(directorio: Path) -> list[Path]:
    """Escribe los tres PDFs en `directorio` (lo crea si no existe) y devuelve sus rutas.

    Los nombres de archivo son los de `DOCUMENTOS` en `catalog.py`.
    """
    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    rutas = []
    for contenido in CONTENIDOS.values():
        documento = contenido.documento
        ruta = directorio / documento.nombre_archivo
        pdf = SimpleDocTemplate(
            str(ruta),
            pagesize=A4,
            leftMargin=2.5 * cm,
            rightMargin=2.5 * cm,
            topMargin=2.5 * cm,
            bottomMargin=2.5 * cm,
            title=documento.titulo,
            author=_AUTOR,
            subject=documento.titulo,
            creator="gym_agent.synthetic.pdf_render",
            invariant=1,
        )
        pdf.build(_elementos(contenido))
        rutas.append(ruta)
    return rutas
