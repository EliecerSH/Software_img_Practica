"""
codigos.py — Entrada de datos: lectura de las líneas de códigos y búsqueda de archivos.

Responsabilidades:
  1. Interpretar una línea de texto como una composición (lista de productos).
  2. Encontrar en disco la foto que corresponde a cada código.

Sintaxis de una línea (una composición por línea):
    COD1/COD2                  dos productos lado a lado
    COD1/COD2/COD3/COD4        3, 4 o más productos
    COD1                       un solo producto
    COD1:lateral/COD2:frontal  perspectiva por producto
    COD1:bolso/COD2            tipo de producto (se hereda al resto de la línea)
Las líneas vacías y las que empiezan con '#' se ignoran.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from catalogo import (
    PERSPECTIVES,
    detect_perspective_from_name,
    resolve_perspective,
    resolve_product,
)

DEFAULT_INPUT_DIR = "imagenes"
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


# =====================================================================
# MODELO: un producto dentro de una composición
# =====================================================================
@dataclass
class Item:
    code: str                            # código del producto ("30-CRU")
    perspective: str = "auto"            # "auto" = usar la global o deducirla del nombre del archivo
    product: Optional[str] = None        # None = usar el tipo global
    path: Optional[Path] = None          # ruta directa a la foto (omite la búsqueda por código)
    invalid: Optional[str] = None        # mensaje de error si la línea traía una opción desconocida

    def label(self) -> str:
        """Texto para mostrar: el código más las opciones escritas explícitamente."""
        extra = []
        if self.perspective != "auto":
            extra.append(self.perspective)
        if self.product:
            extra.append(self.product)
        return self.code + (":" + ":".join(extra) if extra else "")


# =====================================================================
# PARSEO DE LÍNEAS
# =====================================================================
def parse_item(text: str) -> Optional[Item]:
    """
    Interpreta 'CODIGO[:opcion[:opcion]]'.
    Cada opción puede ser una perspectiva ('frontal') o un tipo de producto ('bolso').
    Una opción desconocida no lanza excepción: queda en Item.invalid y se informa
    como error al procesar (así el contador de la interfaz nunca falla al escribir).
    """
    parts = [p.strip() for p in text.split(":")]
    if not parts[0]:
        return None

    item = Item(code=parts[0])
    for tok in parts[1:]:
        if not tok:
            continue
        persp = resolve_perspective(tok)
        if persp:
            item.perspective = persp
            continue
        prod = resolve_product(tok)
        if prod:
            item.product = prod
            continue
        item.invalid = f"Opción desconocida '{tok}' en '{text.strip()}'"
    return item


def parse_code_line(line: str) -> Optional[List[Item]]:
    """
    Interpreta una línea completa como lista de productos.
    Separadores admitidos: '/', '|', ',', ';' o ' - ' (se usa el primero que aparezca).
    Devuelve None si la línea está vacía o es un comentario.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    chunks = [line]                       # sin separador: un solo producto
    for sep in ("/", "|", ",", ";"):
        if sep in line:
            chunks = line.split(sep)
            break
    else:
        if " - " in line:                 # "30-CRU - 65-CAF"
            chunks = line.split(" - ")

    items = [parse_item(c) for c in chunks]
    items = [i for i in items if i]
    return items or None


def parse_code_pair(line: str) -> Optional[Tuple[str, str]]:
    """Compatibilidad con la versión anterior: (cod1, cod2) si la línea tiene exactamente 2 productos."""
    items = parse_code_line(line)
    if items and len(items) == 2:
        return items[0].code, items[1].code
    return None


def sanitize_filename(name: str) -> str:
    """Reemplaza los caracteres que Windows no permite en un nombre de archivo."""
    return re.sub(r'[\\/*?:"<>|]', '-', name)


# =====================================================================
# BÚSQUEDA DE ARCHIVOS POR CÓDIGO
# =====================================================================
def find_image_for_code(code: str, search_dir: str = DEFAULT_INPUT_DIR, perspective: str = "auto") -> Optional[Path]:
    """
    Busca en search_dir la foto que corresponde a 'code'.

    Prioridad de coincidencia (1 = mejor):
      1. Nombre exacto, sin extensión:           '30-CRU.jpg'
      2. Código como palabra con delimitadores:  'ALPARGATA-65-CAF-01.jpg' -> '65-CAF'
      3. Código como subcadena del nombre
    Si no hay nada en search_dir, se repite la búsqueda en la carpeta Descargas del usuario.

    Si se pide una perspectiva, entre los candidatos se prefieren los archivos etiquetados con ella
    ('30-CRU_lateral.jpg', '30-CRU-frontal.png'). Si ninguno la tiene, se usa el mejor candidato.
    A igual coincidencia, el orden de preferencia es: sin etiqueta > lateral > 3/4 > frontal > ...
    """
    code_clean = code.strip().upper()
    if not code_clean:
        return None

    search_dirs = [Path(search_dir)]
    downloads_dir = Path.home() / "Downloads"
    if downloads_dir.exists() and downloads_dir != search_dirs[0]:
        search_dirs.append(downloads_dir)

    # Código rodeado de delimitadores (o inicio/fin del nombre)
    pattern = re.compile(r'(^|[-_ \.\(\)])' + re.escape(code_clean) + r'([-_ \.\(\)]|$)')
    perspective_order = list(PERSPECTIVES)

    for current_dir in search_dirs:
        if not current_dir.exists():
            continue

        # 1) Reunir candidatos con su nivel de coincidencia (sorted = resultado determinista)
        candidates: List[Tuple[int, Path]] = []
        for f in sorted(current_dir.iterdir()):
            if not (f.is_file() and f.suffix.lower() in VALID_EXTENSIONS):
                continue
            stem = f.stem.strip().upper()
            if stem == code_clean:
                candidates.append((1, f))
            elif pattern.search(stem):
                candidates.append((2, f))
            elif code_clean in stem:
                candidates.append((3, f))

        if not candidates:
            continue

        # 2) Si se pidió una perspectiva, quedarse con los archivos etiquetados con ella (si existen)
        if perspective and perspective != "auto":
            tagged = [c for c in candidates
                      if detect_perspective_from_name(c[1].stem, code_clean) == perspective]
            if tagged:
                candidates = tagged

        # 3) Mejor coincidencia primero; a igualdad, según el orden de perspectivas
        candidates.sort(key=lambda c: (c[0], perspective_order.index(detect_perspective_from_name(c[1].stem, code_clean))))
        return candidates[0][1]

    return None
