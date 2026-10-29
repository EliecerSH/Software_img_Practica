"""
catalogo.py — Catálogo de opciones del programa.

Aquí viven las "tablas de datos" que describen QUÉ se puede elegir:
  - Tipos de producto (calzado, bolso, ropa...)         -> PRODUCT_TYPES
  - Perspectivas de la foto (lateral, 3/4, frontal...)  -> PERSPECTIVES
  - Distribuciones de la composición (fila, diagonal...) -> LAYOUTS
  - Formatos de salida (libre, pack, tripack)            -> FORMATS

Para agregar un tipo de producto o una perspectiva nueva basta con sumar una entrada
a la tabla correspondiente: el resto del programa (interfaz, consola, búsqueda de archivos)
la reconoce automáticamente.

También contiene los "traductores" de texto a clave interna (resolve_*), que aceptan
alias en español e inglés ("lat", "side", "perfil" -> "lateral").
"""
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


# =====================================================================
# TIPOS DE PRODUCTO
# =====================================================================
@dataclass(frozen=True)
class ProductProfile:
    """Parámetros que dependen del tipo de producto."""
    key: str                      # clave interna ("calzado")
    label: str                    # texto que se muestra en la interfaz
    shadow: str                   # sombra por defecto si la perspectiva no la define:
                                  #   "ground" = apoyado en el piso | "drop" = plano con sombra proyectada
    keep_parts: float             # limpieza del recorte: 1.0 = solo la pieza más grande;
                                  #   0.02 = conserva piezas separadas >= 2 % de la mayor (asas, correas)
    aliases: Tuple[str, ...] = ()  # otros nombres aceptados al escribir ("zapato" -> calzado)


PRODUCT_TYPES: Dict[str, ProductProfile] = {
    "calzado": ProductProfile("calzado", "Calzado", "ground", 1.0,
                              ("zapato", "zapatilla", "alpargata", "sandalia", "bota", "shoe")),
    "bolso": ProductProfile("bolso", "Bolso / Cartera / Mochila", "ground", 0.03,
                            ("cartera", "bolsa", "mochila", "bag", "maleta")),
    "ropa": ProductProfile("ropa", "Ropa / Prenda", "drop", 0.02,
                           ("prenda", "camiseta", "polera", "pantalon", "chaqueta", "clothing")),
    "accesorio": ProductProfile("accesorio", "Accesorio / Joyería", "drop", 0.02,
                                ("accesorios", "joya", "joyeria", "reloj", "gorra", "cinturon")),
    "generico": ProductProfile("generico", "Genérico (otro producto)", "drop", 0.02,
                               ("general", "otro", "producto", "objeto")),
}

# Tipo que se usa si el usuario no elige ninguno (mantiene el comportamiento original del programa).
DEFAULT_PRODUCT = "calzado"


# =====================================================================
# PERSPECTIVAS
# =====================================================================
@dataclass(frozen=True)
class Perspective:
    """Parámetros que dependen de desde dónde se tomó la foto."""
    key: str                      # clave interna ("lateral")
    label: str                    # texto que se muestra en la interfaz
    shadow: Optional[str]         # "ground" | "drop" | None (None = usar el valor del tipo de producto)
    aliases: Tuple[str, ...] = ()  # alias aceptados, también como etiqueta en el nombre del archivo


PERSPECTIVES: Dict[str, Perspective] = {
    "auto": Perspective("auto", "Automática (según nombre del archivo)", None),
    "lateral": Perspective("lateral", "Lateral / Perfil", "ground", ("lat", "side", "perfil")),
    "tres_cuartos": Perspective("tres_cuartos", "3/4 (en ángulo)", "ground",
                                ("3q", "3-4", "tres cuartos", "angulo", "angle", "three quarter")),
    "frontal": Perspective("frontal", "Frontal", "ground", ("front", "frente")),
    "trasera": Perspective("trasera", "Trasera", "ground", ("back", "rear", "atras")),
    "superior": Perspective("superior", "Superior / Plano (vista cenital)", "drop",
                            ("top", "sup", "arriba", "plano", "flat", "cenital")),
    "inferior": Perspective("inferior", "Inferior / Suela", "drop", ("suela", "sole", "bottom")),
}
DEFAULT_PERSPECTIVE = "auto"


# =====================================================================
# DISTRIBUCIONES (cómo se acomodan varios productos en el lienzo)
# La lógica de cada una está en composicion.py.
# =====================================================================
LAYOUTS: Dict[str, str] = {
    "auto": "Automática",                  # hasta 3 productos en una fila; 4 o más en cuadrícula
    "fila": "Una fila",
    "cuadricula": "Cuadrícula",
    "diagonal": "Diagonal escalonada",     # cascada de arriba-izquierda a abajo-derecha
}
DEFAULT_LAYOUT = "auto"

# Alias aceptados para cada distribución
_LAYOUT_ALIASES = {
    "auto": "auto",
    "fila": "fila", "row": "fila",
    "cuadricula": "cuadricula", "grid": "cuadricula",
    "diagonal": "diagonal", "escalonado": "diagonal", "cascada": "diagonal",
}


# =====================================================================
# FORMATOS DE SALIDA (cuántos productos lleva la imagen)
# =====================================================================
FORMATS: Dict[str, str] = {
    "libre": "Libre (según cada línea)",   # tantos productos como códigos tenga la línea
    "pack": "Pack (2 productos)",
    "tripack": "Tripack (3 productos)",
}
FORMAT_COUNT: Dict[str, int] = {"pack": 2, "tripack": 3}   # productos exigidos por cada formato
DEFAULT_FORMAT = "libre"

_FORMAT_ALIASES = {
    "libre": "libre", "free": "libre",
    "pack": "pack", "duo": "pack", "par": "pack",
    "tripack": "tripack", "tri_pack": "tripack", "trio": "tripack", "triple": "tripack",
}


# =====================================================================
# TRADUCTORES: texto escrito por el usuario -> clave interna
# =====================================================================
def _norm(text: str) -> str:
    """Normaliza una opción: minúsculas y espacios, '/' o '-' unificados a '_' ("3/4" -> "3_4")."""
    return re.sub(r"[\s/\-]+", "_", text.strip().lower())


def resolve_perspective(token: str) -> Optional[str]:
    """'lat' -> 'lateral'. Devuelve None si no es una perspectiva conocida."""
    n = _norm(token)
    for key, p in PERSPECTIVES.items():
        if n == key or n in {_norm(a) for a in p.aliases}:
            return key
    return None


def resolve_product(token: str) -> Optional[str]:
    """'zapato' -> 'calzado'. Devuelve None si no es un tipo conocido."""
    n = _norm(token)
    for key, p in PRODUCT_TYPES.items():
        if n == key or n in {_norm(a) for a in p.aliases}:
            return key
    return None


def resolve_layout(token: str) -> Optional[str]:
    """'cascada' -> 'diagonal'. Devuelve None si no es una distribución conocida."""
    return _LAYOUT_ALIASES.get(_norm(token))


def resolve_format(token: str) -> Optional[str]:
    """'tri-pack' -> 'tripack'. Devuelve None si no es un formato conocido."""
    return _FORMAT_ALIASES.get(_norm(token))


def detect_perspective_from_name(stem: str, code: str = "") -> str:
    """
    Deduce la perspectiva a partir del nombre del archivo (sin extensión).
        '30-CRU_lateral'  -> 'lateral'
        '30-CRU 3q'       -> 'tres_cuartos'
        '30-CRU'          -> 'auto' (sin etiqueta)
    Se quita primero el código del producto para que no se confunda con una etiqueta
    (por ejemplo, un código que contenga 'sup' o 'top').
    """
    s = stem.lower()
    if code:
        s = s.replace(code.lower(), " ")
    for key, p in PERSPECTIVES.items():
        if key == "auto":
            continue
        for alias in (key,) + p.aliases:
            # El alias debe aparecer como palabra completa; '_' equivale a '-', '_' o espacio.
            body = re.escape(_norm(alias)).replace("_", "[-_ ]")
            if re.search(rf"(?<![a-z0-9]){body}(?![a-z0-9])", s):
                return key
    return "auto"
