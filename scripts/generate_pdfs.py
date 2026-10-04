"""Genera los tres PDFs sintéticos en `data/pdfs/`.

Uso: python scripts/generate_pdfs.py

Sobrescribe los archivos existentes; como el renderizado es invariante, si el texto de
`pdf_content.py` no cambió, los PDFs quedan idénticos (git no muestra diferencias).
"""

import hashlib

from pypdf import PdfReader

from gym_agent.config import PDF_DIR
from gym_agent.synthetic.pdf_render import renderizar_pdfs


def main() -> None:
    print(f"{'archivo':<30}{'páginas':>8}  sha256")
    for ruta in renderizar_pdfs(PDF_DIR):
        paginas = len(PdfReader(ruta).pages)
        digest = hashlib.sha256(ruta.read_bytes()).hexdigest()[:16]
        print(f"{ruta.name:<30}{paginas:>8}  {digest}")


if __name__ == "__main__":
    main()
