"""
composicion.py — Arma la imagen final a partir de los recortes ya limpios.

Flujo de assemble():

    piezas (recortes)  ->  elegir distribución  ->  posiciones (x, y, tamaño)
                                                         |
              lienzo blanco  <-  sombras  <-  pegado de cada pieza

Cada DISTRIBUCIÓN (fila, cuadrícula, diagonal) es una función independiente que recibe las
piezas y devuelve dónde va cada una. Para crear una distribución nueva:
  1. escribir una función _place_xxx con la misma forma que las existentes,
  2. registrarla en PLACERS,
  3. agregar su nombre en catalogo.LAYOUTS.

Las SOMBRAS dependen de la perspectiva de cada producto:
  - "ground": producto apoyado (lateral, 3/4, frontal, trasera) -> sombra de contacto bajo la base.
  - "drop":   producto plano (vista superior, inferior, ropa)   -> sombra proyectada suave.
"""
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from imagen import fit_box

# =====================================================================
# ESPECIFICACIONES DE LA COMPOSICIÓN
# =====================================================================
W = H = 1000             # tamaño de lienzo por defecto (px)
BG = (255, 255, 255)     # fondo blanco puro
MARGIN = 0.03            # margen lateral y superior/inferior (fracción del lienzo)
GAP = 0.04               # separación entre productos (fracción del ancho)
CENTER_Y = 0.52          # centro vertical de cada fila (fracción de la altura de su banda)
CELL_H = 0.80            # alto máximo de un producto (fracción de la altura de su banda)
SINGLE_W = 0.80          # ancho máximo de un producto cuando va solo en su fila
DIAGONAL_W = 0.46        # ancho de cada producto en la distribución diagonal (fracción del ancho)


# =====================================================================
# PIEZA: un recorte listo para ubicar
# =====================================================================
@dataclass
class Piece:
    img: Image.Image            # recorte RGBA del producto
    shadow: str = "ground"      # "ground" = apoyado en el piso | "drop" = plano con sombra proyectada

    @property
    def ground(self) -> bool:
        return self.shadow == "ground"


# Resultado de una distribución: lista de (pieza, imagen escalada, x, y) más la estructura en filas.
Placement = List[Tuple[Piece, Image.Image, int, int]]


# =====================================================================
# SOMBRAS
# =====================================================================
def shadow_ground(img: Image.Image, opacity: int = 60) -> Tuple[Image.Image, int, int]:
    """
    Sombra de contacto que sigue la huella REAL del producto (sirve para cualquier perspectiva):
      1. se toma la franja inferior de la silueta (10 % de la altura),
      2. se aplasta hasta dejarla como una banda delgada,
      3. se redondean los extremos con una elipse,
      4. se difumina y se atenúa según 'opacity'.
    Devuelve (capa en escala de grises, offset_x, offset_y) relativos a la esquina
    superior izquierda del producto; la sombra queda centrada en el borde inferior.
    """
    w, h = img.size
    alpha = np.array(img.getchannel("A"))

    # 1-2) franja inferior aplastada
    band = max(4, int(h * 0.10))
    foot = Image.fromarray(alpha[h - band:, :]).resize((w, max(6, int(w * 0.07))), Image.BILINEAR)

    # 3) extremos redondeados
    envelope = Image.new("L", foot.size, 0)
    ImageDraw.Draw(envelope).ellipse((0, 0, foot.width - 1, foot.height - 1), fill=255)
    foot = ImageChops.multiply(foot, envelope)

    # 4) margen para el difuminado, blur y opacidad
    pad = max(20, int(w * 0.08))
    layer = Image.new("L", (w + pad * 2, foot.height + pad * 2), 0)
    layer.paste(foot, (pad, pad))
    layer = layer.filter(ImageFilter.GaussianBlur(max(3.0, w * 0.02)))
    layer = layer.point(lambda v: int(v * opacity / 255))
    return layer, -pad, h - layer.height // 2


def shadow_drop(img: Image.Image, opacity: int = 55) -> Tuple[Image.Image, int, int]:
    """
    Sombra proyectada suave para productos planos / vista superior / prendas:
    la silueta completa, desplazada un poco hacia abajo y difuminada (sin sensación de piso).
    Devuelve (capa, offset_x, offset_y) relativos a la esquina superior izquierda del producto.
    """
    w, h = img.size
    big = max(w, h)
    pad = max(16, int(big * 0.06))
    layer = Image.new("L", (w + pad * 2, h + pad * 2), 0)
    layer.paste(img.getchannel("A"), (pad, pad))
    layer = layer.filter(ImageFilter.GaussianBlur(max(3.0, big * 0.012)))
    layer = layer.point(lambda v: int(v * opacity / 255))
    return layer, -pad + int(w * 0.008), -pad + int(big * 0.014)


def make_shadow(piece: Piece) -> Tuple[Image.Image, int, int]:
    """Elige el tipo de sombra según la perspectiva de la pieza."""
    return shadow_ground(piece.img) if piece.ground else shadow_drop(piece.img)


# =====================================================================
# DISTRIBUCIONES
# Cada una devuelve (placement, rows). 'rows' describe cuántos productos hay por fila.
# =====================================================================
def split_rows(n: int, layout: str = "auto") -> List[int]:
    """
    Cantidad de productos por fila.
      auto / fila:  hasta 3 productos en una fila (auto); 'fila' siempre una sola fila.
      cuadricula:   columnas = ceil(raíz de n)  ->  4 = 2x2, 5 = 3+2, 9 = 3x3 ...
      auto con 4 o más productos: cuadrícula.
    """
    if n <= 0:
        return []
    if layout == "fila" or (layout == "auto" and n <= 3):
        return [n]
    cols = math.ceil(math.sqrt(n))
    rows = []
    left = n
    while left > 0:
        rows.append(min(cols, left))
        left -= cols
    return rows


def _place_rows(pieces: List[Piece], canvas_w: int, canvas_h: int, layout: str,
                gap_px: int, item_w: Optional[int]) -> Tuple[Placement, List[int]]:
    """
    Distribución en filas centradas (fila única o cuadrícula).
      - Cada producto se escala para caber en su celda (ancho y alto).
      - Productos apoyados ("ground"): comparten línea de base dentro de la fila.
      - Productos planos o perspectivas mezcladas: se centran verticalmente.
    """
    avail_w = canvas_w * (1 - 2 * MARGIN)
    rows = split_rows(len(pieces), layout)
    band_h = canvas_h / len(rows)                 # altura de cada fila

    placed: Placement = []
    idx = 0
    for r, count in enumerate(rows):
        row_pieces = pieces[idx: idx + count]
        idx += count

        # Celda disponible para cada producto de la fila
        cell_w = (avail_w - gap_px * (count - 1)) / count
        if count == 1:
            cell_w = min(cell_w, canvas_w * SINGLE_W)   # un producto solo no ocupa todo el ancho
        if item_w:
            cell_w = min(cell_w, item_w)                # tope opcional pedido por el usuario
        cell_h = band_h * CELL_H

        scaled = [fit_box(p.img, cell_w, cell_h) for p in row_pieces]

        # Fila centrada horizontalmente
        row_w = sum(s.width for s in scaled) + gap_px * (count - 1)
        x = (canvas_w - row_w) // 2

        tallest = max(s.height for s in scaled)
        center_y = int((r + CENTER_Y) * band_h)
        all_ground = all(p.ground for p in row_pieces)

        for p, s in zip(row_pieces, scaled):
            if all_ground:
                y = center_y + tallest // 2 - s.height   # base común
            else:
                y = center_y - s.height // 2             # centrado vertical
            placed.append((p, s, x, y))
            x += s.width + gap_px
    return placed, rows


def _place_diagonal(pieces: List[Piece], canvas_w: int, canvas_h: int, layout: str,
                    gap_px: int, item_w: Optional[int]) -> Tuple[Placement, List[int]]:
    """
    Cascada escalonada de arriba-izquierda a abajo-derecha.
      - Todos los productos tienen el mismo ancho máximo (DIAGONAL_W del lienzo).
      - El alto se reparte en bandas iguales, una por producto, cada uno centrado en la suya.
      - El primero queda pegado al margen izquierdo y el último al derecho; el resto se
        reparte uniformemente entre ambos (los productos se solapan en horizontal).
    El orden de los códigos en la línea es el orden de arriba hacia abajo.
    """
    n = len(pieces)
    avail_w = canvas_w * (1 - 2 * MARGIN)
    avail_h = canvas_h * (1 - 2 * MARGIN)

    cell_w = canvas_w * DIAGONAL_W
    if item_w:
        cell_w = min(cell_w, item_w)
    cell_h = avail_h / n * 0.95                    # 5 % de aire entre bandas

    placed: Placement = []
    for i, p in enumerate(pieces):
        s = fit_box(p.img, cell_w, cell_h)
        if n > 1:
            x = round(canvas_w * MARGIN + (avail_w - s.width) * i / (n - 1))
        else:
            x = (canvas_w - s.width) // 2
        center_y = canvas_h * MARGIN + avail_h * (i + 0.5) / n
        placed.append((p, s, x, int(center_y - s.height / 2)))
    return placed, [1] * n


# Registro de distribuciones. Las que no estén aquí usan _place_rows (auto / fila / cuadricula).
PLACERS = {
    "diagonal": _place_diagonal,
}


# =====================================================================
# ENSAMBLADO
# =====================================================================
def assemble(
    pieces: List[Piece],
    add_shadow: bool = True,
    canvas_w: int = W,
    canvas_h: int = H,
    layout: str = "auto",
    gap: Optional[int] = None,
    item_w: Optional[int] = None,
) -> Tuple[Image.Image, Dict[str, Any]]:
    """
    Compone 1..N productos sobre un lienzo blanco (#FFFFFF).

      add_shadow: dibuja la sombra de cada producto (según su perspectiva).
      layout:     'auto', 'fila', 'cuadricula' o 'diagonal'.
      gap:        separación entre productos en px (por defecto 4 % del ancho).
      item_w:     ancho máximo de cada producto en px (por defecto lo decide la distribución).

    Devuelve (imagen RGB, geometría) donde la geometría la usa verify():
      {"canvas": (w, h), "boxes": [(x, y, w, h), ...], "rows": [productos por fila]}
    """
    if not pieces:
        raise ValueError("No hay productos para ensamblar.")

    canvas = Image.new("RGB", (canvas_w, canvas_h), BG)
    gap_px = gap if gap is not None and gap >= 0 else int(canvas_w * GAP)

    # 1) Posiciones según la distribución elegida
    placer = PLACERS.get(layout, _place_rows)
    placed, rows = placer(pieces, canvas_w, canvas_h, layout, gap_px, item_w)

    # 2) Sombras primero (así la sombra de un producto nunca tapa a otro)
    if add_shadow:
        for piece, scaled, x, y in placed:
            layer, off_x, off_y = make_shadow(Piece(scaled, piece.shadow))
            canvas.paste((0, 0, 0), (x + off_x, y + off_y), layer)

    # 3) Productos encima, usando su propio canal alfa como máscara
    for _, scaled, x, y in placed:
        canvas.paste(scaled, (x, y), scaled)

    geo = {
        "canvas": (canvas_w, canvas_h),
        "boxes": [(x, y, s.width, s.height) for _, s, x, y in placed],
        "rows": rows,
    }
    return canvas, geo


# =====================================================================
# VERIFICACIÓN
# =====================================================================
def verify(path: str, geo: Dict[str, Any]) -> List[str]:
    """
    Revisa el archivo generado y devuelve una lista de avisos (vacía = todo correcto):
      - tamaño y formato JPEG correctos,
      - esquinas de fondo en blanco puro,
      - ningún producto se sale del lienzo.
    """
    errs = []
    exp_w, exp_h = geo["canvas"]
    img = Image.open(path)
    if img.size != (exp_w, exp_h):
        errs.append(f"Tamano {img.size}, se esperaba {(exp_w, exp_h)}")
    if img.format != "JPEG":
        errs.append(f"Formato {img.format}, se esperaba JPEG")

    arr = np.array(img.convert("RGB"))
    for name, px in (("esq. sup-izq", arr[0, 0]), ("esq. sup-der", arr[0, -1]),
                     ("esq. inf-izq", arr[-1, 0]), ("esq. inf-der", arr[-1, -1])):
        if (px < 250).any():
            errs.append(f"Fondo no es blanco puro en {name}: {px.tolist()}")

    for i, (x, y, w, h) in enumerate(geo["boxes"], 1):
        if x < 0 or y < 0 or x + w > exp_w or y + h > exp_h:
            errs.append(f"El producto {i} se sale del lienzo")
    return errs
