"""
previa.py — Vista previa de la composición y comparación de configuraciones.

Dibuja la composición EN MEMORIA (no guarda ningún archivo) usando exactamente el mismo
camino que el proceso final:

    pipeline.prepare()  ->  composicion.assemble()  ->  imagen reducida para la pantalla

Por eso lo que se ve en la previa es lo que se obtiene al procesar. Para que sea rápida:
  - los recortes salen de la caché de imagen.process_image (la IA solo trabaja la primera vez),
  - la composición se dibuja a tamaño reducido (por defecto, lado mayor de 520 px).

Este módulo no usa la interfaz gráfica: se puede probar y usar desde consola.
"""
from typing import Any, Dict, List, Optional, Tuple

import pipeline
from catalogo import LAYOUTS
from composicion import assemble

PREVIEW_SIDE = 520       # lado mayor de la vista previa de una composición (px)
VARIANT_SIDE = 300       # lado mayor de cada recuadro al comparar (px)

# Valores de separación que se comparan (% del ancho del lienzo)
GAP_VARIANTS = (0, 4, 8, 12)

# Qué se puede comparar: clave -> texto para la interfaz
COMPARE_KINDS: Dict[str, str] = {
    "layout": "Distribución",
    "shadow": "Sombra",
    "gap": "Separación",
}

# Configuración por defecto de una vista previa (las mismas claves que usa la interfaz)
DEFAULT_SETTINGS: Dict[str, Any] = {
    "product": pipeline.DEFAULT_PRODUCT,
    "perspective": pipeline.DEFAULT_PERSPECTIVE,
    "layout": pipeline.DEFAULT_LAYOUT,
    "fmt": pipeline.DEFAULT_FORMAT,
    "canvas_w": 1080,
    "canvas_h": 1080,
    "add_shadow": True,
    "skip_cutout": False,
    "gap_pct": None,
}


def _preview_size(canvas_w: int, canvas_h: int, max_side: int) -> Tuple[int, int]:
    """Tamaño reducido (misma proporción que el lienzo real, lado mayor = max_side)."""
    scale = max_side / max(canvas_w, canvas_h)
    return max(1, round(canvas_w * scale)), max(1, round(canvas_h * scale))


def _draw(prep: "pipeline.Prepared", cfg: Dict[str, Any], max_side: int):
    """Dibuja una composición ya preparada con la configuración dada. Devuelve (imagen, geometría)."""
    pw, ph = _preview_size(cfg["canvas_w"], cfg["canvas_h"], max_side)
    return assemble(
        prep.pieces,
        add_shadow=cfg["add_shadow"],
        canvas_w=pw,
        canvas_h=ph,
        layout=cfg["layout"],
        gap=pipeline.gap_from_pct(pw, cfg["gap_pct"]),   # el % se calcula sobre el tamaño de la previa
    )


def _merge(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = dict(DEFAULT_SETTINGS)
    cfg.update(settings or {})
    return cfg


def render_preview(items, img_dir: str, settings: Optional[Dict[str, Any]] = None,
                   max_side: int = PREVIEW_SIDE) -> Dict[str, Any]:
    """
    Vista previa de UNA composición con la configuración indicada.

    Devuelve {"ok": True, "image": PIL.Image, "size": (w, h), "final_size": (w, h), "warnings": [...]}
    o       {"ok": False, "error": "mensaje", "warnings": [...]}.
    """
    cfg = _merge(settings)
    try:
        prep = pipeline.prepare(items, img_dir, cfg["skip_cutout"], cfg["product"], cfg["perspective"], cfg["fmt"])
        img, _ = _draw(prep, cfg, max_side)
    except pipeline.PrepareError as ex:
        return {"ok": False, "error": str(ex), "warnings": ex.warnings}
    except Exception as ex:                                    # cualquier otro fallo al dibujar
        return {"ok": False, "error": f"No se pudo dibujar la vista previa: {ex}", "warnings": []}
    return {
        "ok": True,
        "image": img,
        "size": img.size,
        "final_size": (cfg["canvas_w"], cfg["canvas_h"]),
        "warnings": prep.warnings,
        "products": len(prep.pieces),
    }


def variant_specs(kind: str, settings: Optional[Dict[str, Any]] = None) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Lista de (texto del recuadro, cambios de configuración) para comparar según 'kind':
      layout -> una variante por distribución,  shadow -> con / sin sombra,  gap -> varias separaciones.
    """
    if kind == "layout":
        return [(label, {"layout": key}) for key, label in LAYOUTS.items()]
    if kind == "shadow":
        return [("Con sombra", {"add_shadow": True}), ("Sin sombra", {"add_shadow": False})]
    if kind == "gap":
        return [(f"Separación {g} %", {"gap_pct": g}) for g in GAP_VARIANTS]
    raise ValueError(f"No se puede comparar '{kind}'. Opciones: {', '.join(COMPARE_KINDS)}")


def render_variants(items, img_dir: str, kind: str, settings: Optional[Dict[str, Any]] = None,
                    max_side: int = VARIANT_SIDE) -> Dict[str, Any]:
    """
    Dibuja la misma composición con varias configuraciones para compararlas.
    Las fotos se preparan UNA sola vez; solo se repite el ensamblado.

    Devuelve {"ok": True, "variants": [{"label", "changes", "image", "current"}, ...], "warnings": [...]}
    'changes' son los valores a aplicar a la configuración si el usuario elige esa variante;
    'current' indica cuál coincide con la configuración actual.
    """
    cfg = _merge(settings)
    try:
        specs = variant_specs(kind, cfg)
        prep = pipeline.prepare(items, img_dir, cfg["skip_cutout"], cfg["product"], cfg["perspective"], cfg["fmt"])
        variants = []
        for label, changes in specs:
            v_cfg = dict(cfg, **changes)
            img, _ = _draw(prep, v_cfg, max_side)
            current = all(cfg.get(k) == v for k, v in changes.items())
            if kind == "gap" and cfg.get("gap_pct") is None:      # sin valor elegido = el 4 % por defecto
                current = changes["gap_pct"] == 4
            variants.append({"label": label, "changes": changes, "image": img, "current": current})
    except pipeline.PrepareError as ex:
        return {"ok": False, "error": str(ex), "warnings": ex.warnings}
    except Exception as ex:
        return {"ok": False, "error": f"No se pudo comparar: {ex}", "warnings": []}
    return {"ok": True, "variants": variants, "warnings": prep.warnings, "products": len(prep.pieces)}
