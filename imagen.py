"""
imagen.py — Preparación de cada foto individual.

Convierte una foto cualquiera en un recorte limpio y ajustado del producto (RGBA):

    foto  ->  cutout()  ->  clean()  ->  trim()  ->  recorte listo para ensamblar
              quita fondo   quita restos  ajusta al
              (IA rembg)    y halos       borde del producto

Aquí no se decide nada sobre la composición final (eso está en composicion.py).
"""
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image

MIN_SIDE = 300           # lado menor mínimo (px) para aceptar una foto de origen


# =====================================================================
# 1. RECORTE DE FONDO (IA)
# =====================================================================
_session = None   # la sesión del modelo se crea una sola vez (cargarlo es lento)


def get_rembg_session():
    """Devuelve la sesión compartida del modelo de recorte, creándola la primera vez."""
    global _session
    if _session is None:
        from rembg import new_session          # import tardío: rembg tarda en cargar
        _session = new_session("isnet-general-use")
    return _session


def cutout(img: Image.Image) -> Image.Image:
    """Quita el fondo con rembg. Devuelve RGBA con el producto sobre transparencia."""
    from rembg import remove
    return remove(
        img.convert("RGB"),
        session=get_rembg_session(),
        alpha_matting=False,
    ).convert("RGBA")


# =====================================================================
# 2. LIMPIEZA DEL RECORTE
# =====================================================================
def clean(img: Image.Image, keep_parts: float = 1.0) -> Image.Image:
    """
    Limpia el recorte en dos pasos:

    a) Fondo blanco residual: se elimina SOLO el blanco conectado al borde de la imagen.
       Los blancos interiores (productos blancos, cordones, estampados) se conservan.
         - Imagen opaca (JPG sin recortar): el blanco del borde es el fondo -> se borra.
         - Imagen ya recortada: solo se limpian halos semitransparentes.

    b) Piezas sueltas: se etiquetan las zonas conectadas y se conservan las que midan
       >= keep_parts * la más grande.
         keep_parts = 1.0  -> solo la pieza principal (calzado: elimina piernas, sombras sueltas)
         keep_parts = 0.02 -> también piezas separadas (asa de un bolso, correa, accesorios)

    Si scipy no está disponible o algo falla, devuelve la imagen sin limpiar.
    """
    try:
        from scipy import ndimage
        arr = np.array(img.convert("RGBA"))
        rgb = arr[:, :, :3]
        alpha = arr[:, :, 3].copy()

        # --- a) fondo blanco conectado al borde ---
        is_white = (rgb > 252).all(axis=2)
        lab, n = ndimage.label(is_white)                      # zonas blancas conectadas
        if n:
            # zonas blancas que tocan alguno de los 4 bordes de la imagen
            border_ids = np.unique(np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]]))
            border_ids = border_ids[border_ids > 0]
            edge_white = np.isin(lab, border_ids)
            if alpha.min() == 255:
                alpha[edge_white] = 0                         # imagen opaca
            else:
                alpha[edge_white & (alpha < 255)] = 0         # ya recortada: solo halos

        # --- b) piezas sueltas ---
        mask = alpha > 20
        labeled, num = ndimage.label(mask)
        if num > 1:
            sizes = ndimage.sum(mask, labeled, range(1, num + 1))
            threshold = keep_parts * float(sizes.max())
            keep_ids = [i + 1 for i, s in enumerate(sizes) if s >= threshold]
            alpha = np.where(np.isin(labeled, keep_ids), alpha, 0).astype("uint8")

        arr[:, :, 3] = alpha
        return Image.fromarray(arr)
    except Exception:
        return img.convert("RGBA")


# =====================================================================
# 3. RECORTE AJUSTADO Y ESCALADO
# =====================================================================
def trim(img: Image.Image, alpha_cut: int = 10) -> Image.Image:
    """Recorta la imagen al borde del producto, ignorando píxeles casi transparentes (halos)."""
    a = np.array(img.getchannel("A"))
    a = np.where(a < alpha_cut, 0, a).astype("uint8")
    img = img.copy()
    img.putalpha(Image.fromarray(a))
    bbox = img.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("El recorte quedo vacio: no se detecto producto.")
    return img.crop(bbox)


def fit_box(img: Image.Image, box_w: float, box_h: float) -> Image.Image:
    """Escala proporcionalmente la imagen para que quepa dentro de box_w x box_h."""
    r = min(box_w / img.width, box_h / img.height)
    return img.resize((max(1, round(img.width * r)), max(1, round(img.height * r))), Image.LANCZOS)


# =====================================================================
# VALIDACIÓN DE LA FOTO DE ORIGEN
# =====================================================================
def validate_image(path: "str | Path", min_side: int = MIN_SIDE) -> Optional[str]:
    """
    Revisa que la foto se pueda abrir y tenga resolución suficiente.
    Devuelve un mensaje de error, o None si la foto es válida.
    """
    p = Path(path)
    try:
        with Image.open(p) as im:
            im.load()                          # fuerza la lectura completa: detecta archivos dañados
            w, h = im.size
    except Exception as ex:
        return f"La imagen '{p.name}' está dañada o no se puede abrir ({ex.__class__.__name__})"
    if min(w, h) < min_side:
        return f"La imagen '{p.name}' tiene resolución insuficiente ({w}x{h} px; mínimo {min_side} px por lado)"
    return None


# =====================================================================
# PROCESAMIENTO COMPLETO DE UNA FOTO (con caché)
# =====================================================================
# Recortar con IA es lo más lento del proceso. Una misma foto suele repetirse en muchas
# composiciones (y en cada vista previa), así que el recorte se guarda en memoria.
# La clave incluye la fecha de modificación: si la foto cambia, se vuelve a procesar.
_CACHE: Dict[Tuple, Image.Image] = {}
_CACHE_MAX = 24


def clear_cache() -> None:
    """Vacía la caché de recortes (libera memoria)."""
    _CACHE.clear()


def process_image(path: "str | Path", skip_cutout: bool = False, keep_parts: float = 1.0) -> Image.Image:
    """
    Abre la foto y devuelve el recorte limpio del producto.
    No se vuelve a recortar con IA si la foto ya trae transparencia (PNG recortado)
    o si skip_cutout es True.
    El resultado es de solo lectura: se comparte entre composiciones.
    """
    p = Path(path)
    key = (str(p.resolve()), p.stat().st_mtime_ns, bool(skip_cutout), float(keep_parts))
    if key in _CACHE:
        return _CACHE[key]

    img = Image.open(p)
    ya_recortada = img.mode == "RGBA" and np.array(img.getchannel("A")).min() < 200
    if skip_cutout or ya_recortada:
        img = img.convert("RGBA")
    else:
        img = cutout(img)
    result = trim(clean(img, keep_parts))

    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))         # descarta la entrada más antigua
    _CACHE[key] = result
    return result
