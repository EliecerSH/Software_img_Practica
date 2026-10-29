"""
pipeline.py — Orquestador y línea de comandos del Generador de imágenes de producto (pack y tripack).

Une los módulos del proyecto para convertir una línea de códigos en una imagen final:

    codigos.py      lee la línea y busca la foto de cada producto
    imagen.py       recorta el fondo, limpia y ajusta cada foto
    composicion.py  ubica los productos, dibuja sombras y guarda el lienzo
    catalogo.py     tipos de producto, perspectivas y distribuciones disponibles

Este archivo ofrece:
  - process_items():  la función principal (la usan la interfaz gráfica y la consola)
  - main():           la interfaz de línea de comandos

Uso por consola:
    python pipeline.py --pair 30-CRU/65-CAF
    python pipeline.py --pair 30-CRU --formato tripack        (30-CRU_tripack.jpg: mismo producto x3)
    python pipeline.py --pair "BOL-01:frontal/BOL-02:frontal" --tipo bolso
    python pipeline.py --pair "AZUL/CAFE/ESTAMPADO" --layout diagonal
    python pipeline.py --list codigos.txt --dir-in imagenes --dir-out resultados
    python pipeline.py foto1.jpg foto2.jpg -o resultado.jpg
"""
import argparse
import sys
from pathlib import Path
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

# Se reexportan para que la interfaz gráfica pueda usar todo desde "import pipeline".
from catalogo import (  # noqa: F401
    DEFAULT_FORMAT,
    DEFAULT_LAYOUT,
    DEFAULT_PERSPECTIVE,
    DEFAULT_PRODUCT,
    FORMAT_COUNT,
    FORMATS,
    LAYOUTS,
    PERSPECTIVES,
    PRODUCT_TYPES,
    ProductProfile,
    detect_perspective_from_name,
    resolve_format,
    resolve_layout,
    resolve_perspective,
    resolve_product,
)
from codigos import (  # noqa: F401
    DEFAULT_INPUT_DIR,
    Item,
    find_image_for_code,
    parse_code_line,
    parse_code_pair,
    parse_item,
    sanitize_filename,
)
from composicion import H, W, Piece, assemble, verify  # noqa: F401
from imagen import MIN_SIDE, process_image, validate_image  # noqa: F401

DEFAULT_OUTPUT_DIR = "resultados"
JPG_QUALITY = 95


# =====================================================================
# PROCESAMIENTO DE UNA COMPOSICIÓN
# =====================================================================
class PrepareError(Exception):
    """Una composición no se puede preparar (falta una foto, foto dañada, formato inválido...)."""

    def __init__(self, msg: str, files: Optional[List[str]] = None, warnings: Optional[List[str]] = None):
        super().__init__(msg)
        self.files = files or []
        self.warnings = warnings or []


@dataclass
class Prepared:
    """Todo lo necesario para ensamblar una composición, sin haberla dibujado todavía."""
    items: List[Item]                                  # productos finales (ya expandidos según el formato)
    files: List[str]                                   # foto elegida para cada producto
    resolved: List[Tuple[Item, Path, str, ProductProfile]]   # (producto, archivo, perspectiva, perfil)
    pieces: List[Piece]                                # recortes listos para ubicar
    warnings: List[str]


def _fail(items: List[Item], files: List[Optional[str]], msg: str,
          warnings: Optional[List[str]] = None) -> Dict[str, Any]:
    """Resultado estándar de una composición que no se pudo generar."""
    return {
        "ok": False,
        "codes": [i.code for i in items],
        "files": files,
        "out_path": None,
        "error": msg,
        "warnings": warnings or [],
    }


def expand_format(items: List[Item], fmt: str = DEFAULT_FORMAT) -> List[Item]:
    """
    Ajusta la lista de productos al formato de salida.
        libre    -> se deja tal cual.
        pack     -> exige 2 productos; con un solo código se repite el mismo producto.
        tripack  -> exige 3 productos; con un solo código se repite el mismo producto.
    """
    if fmt == "libre" or fmt not in FORMAT_COUNT:
        return list(items)
    n = FORMAT_COUNT[fmt]
    if len(items) == 1:
        return [replace(items[0]) for _ in range(n)]
    if len(items) != n:
        raise PrepareError(f"El formato {FORMATS[fmt]} requiere {n} productos (o un solo código para repetirlo) "
                           f"y la línea tiene {len(items)}")
    return list(items)


def prepare(
    items: List[Item],
    img_dir: str = DEFAULT_INPUT_DIR,
    skip_cutout: bool = False,
    product: str = DEFAULT_PRODUCT,
    perspective: str = DEFAULT_PERSPECTIVE,
    fmt: str = DEFAULT_FORMAT,
) -> Prepared:
    """
    Primera mitad del proceso (sin dibujar nada): valida la línea, encuentra y revisa la foto de
    cada producto, decide su tipo y perspectiva y obtiene los recortes limpios.
    Lo usan tanto process_items (para guardar el archivo) como la vista previa.
    Lanza PrepareError si algo impide armar la composición.

    Perspectiva de cada producto, en orden de prioridad:
        1) la escrita en la línea            ('COD:frontal')
        2) la global (parámetro perspective)
        3) la deducida del nombre del archivo ('COD_lateral.jpg')
        4) automática
    Tipo de producto: el de la línea si algún producto lo indica; si no, el global (parámetro product).
    """
    if not items:
        raise PrepareError("No hay productos en la composición.")

    # Una opción desconocida en la línea ('30-CRU:foo') se informa como error
    for it in items:
        if it.invalid:
            raise PrepareError(it.invalid)

    items = expand_format(items, fmt)
    line_product = next((i.product for i in items if i.product), None)
    files: List[str] = []
    resolved: List[Tuple[Item, Path, str, ProductProfile]] = []
    warnings: List[str] = []

    # --- 1. Encontrar y validar la foto de cada producto; decidir su tipo y perspectiva ---
    for n, it in enumerate(items, 1):
        profile = PRODUCT_TYPES.get(it.product or line_product or product, PRODUCT_TYPES[DEFAULT_PRODUCT])
        requested = it.perspective if it.perspective != "auto" else perspective

        f = it.path or find_image_for_code(it.code, img_dir, requested)
        if not f:
            raise PrepareError(f"No se encontró imagen para el código '{it.code}' (producto {n}) en '{img_dir}'",
                               files, warnings)
        files.append(str(f))

        problem = validate_image(f)
        if problem:
            raise PrepareError(problem, files, warnings)

        # Aviso si se pidió una perspectiva y el archivo está etiquetado con otra distinta
        from_name = detect_perspective_from_name(Path(f).stem, it.code)
        if requested != "auto" and from_name not in ("auto", requested):
            warnings.append(f"'{it.code}': se pidió perspectiva '{requested}' pero el archivo '{Path(f).name}' parece '{from_name}'")

        persp = requested if requested != "auto" else from_name
        resolved.append((it, Path(f), persp, profile))

    # --- 2. Recortes limpios (con caché) ---
    try:
        pieces = []
        for it, f, persp, profile in resolved:
            img = process_image(f, skip_cutout, profile.keep_parts)
            # La sombra la define la perspectiva; si no la define, el tipo de producto
            pieces.append(Piece(img, PERSPECTIVES[persp].shadow or profile.shadow))
    except Exception as ex:
        raise PrepareError(f"Fallo al procesar la imagen: {ex}", files, warnings)

    return Prepared(items, files, resolved, pieces, warnings)


def gap_from_pct(canvas_w: int, gap_pct: Optional[float]) -> Optional[int]:
    """Separación entre productos en px a partir de un porcentaje del ancho (None = valor por defecto)."""
    return None if gap_pct is None else max(0, round(canvas_w * gap_pct / 100))


def output_name(resolved, fmt: str = DEFAULT_FORMAT) -> str:
    """
    Nombre del archivo de salida (sin extensión).
      libre:         códigos unidos con '-'  ->  30-CRU-65-CAF
      pack/tripack:  códigos sin repetir + sufijo  ->  30-CRU_pack, 30-CRU-65-CAF_tripack
    Si la perspectiva se escribió en la línea se añade al nombre del producto, para que
    '30-CRU:lateral/30-CRU:frontal' no choque con '30-CRU/30-CRU'.
    """
    parts: List[str] = []
    for it, _, _, _ in resolved:
        tag = f"_{it.perspective}" if it.perspective != "auto" else ""
        part = sanitize_filename(it.code) + tag
        if fmt == "libre" or part not in parts:      # en pack/tripack un producto repetido aparece una vez
            parts.append(part)
    return "-".join(parts) + (f"_{fmt}" if fmt in FORMAT_COUNT else "")


def _unique_path(path: Path) -> Path:
    """'a.jpg' -> 'a (2).jpg' -> 'a (3).jpg' ... hasta encontrar un nombre libre."""
    if not path.exists():
        return path
    n = 2
    while True:
        cand = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not cand.exists():
            return cand
        n += 1


def process_items(
    items: List[Item],
    img_dir: str = DEFAULT_INPUT_DIR,
    out_dir: str = DEFAULT_OUTPUT_DIR,
    skip_cutout: bool = False,
    add_shadow: bool = True,
    canvas_w: int = W,
    canvas_h: int = H,
    quality: int = JPG_QUALITY,
    product: str = DEFAULT_PRODUCT,
    perspective: str = DEFAULT_PERSPECTIVE,
    layout: str = DEFAULT_LAYOUT,
    gap: Optional[int] = None,
    gap_pct: Optional[float] = None,
    item_w: Optional[int] = None,
    out_path: Optional[str] = None,
    fmt: str = DEFAULT_FORMAT,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """
    Genera la imagen de UNA composición (1..N productos) y la guarda como JPEG.

      fmt:       'libre', 'pack' (2 productos) o 'tripack' (3 productos).
      overwrite: False = si el archivo ya existe se crea 'nombre (2).jpg' en vez de reemplazarlo.
      gap:       separación entre productos en px;  gap_pct: lo mismo como % del ancho (gana gap).

    Devuelve un diccionario con:
        ok, codes, files, out_path, warnings   (siempre)
        error                                  (si ok es False)
        dimensions, products, perspectives, layout, format   (si ok es True)
    """
    try:
        prep = prepare(items, img_dir, skip_cutout, product, perspective, fmt)
    except PrepareError as ex:
        return _fail(items, ex.files, str(ex), ex.warnings)

    # --- Ruta de salida ---
    if out_path:
        final_path = Path(out_path)
        final_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_folder = Path(out_dir)
        out_folder.mkdir(parents=True, exist_ok=True)
        final_path = out_folder / (output_name(prep.resolved, fmt) + ".jpg")
        if not overwrite:
            final_path = _unique_path(final_path)

    # --- Ensamblar y guardar ---
    warnings = list(prep.warnings)
    try:
        canvas, geo = assemble(
            prep.pieces,
            add_shadow=add_shadow,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
            layout=layout,
            gap=gap if gap is not None else gap_from_pct(canvas_w, gap_pct),
            item_w=item_w,
        )
        canvas.save(final_path, "JPEG", quality=quality)
        warnings.extend(verify(str(final_path), geo))
        return {
            "ok": True,
            "codes": [i.code for i in prep.items],
            "files": prep.files,
            "out_path": str(final_path),
            "warnings": warnings,
            "dimensions": f"{canvas_w}x{canvas_h}",
            "products": [r[3].key for r in prep.resolved],
            "perspectives": [r[2] for r in prep.resolved],
            "layout": geo["rows"],
            "format": fmt,
        }
    except Exception as ex:
        return _fail(items, prep.files, f"Fallo al ensamblar la imagen: {ex}", warnings)


def process_pair_by_codes(code1: str, code2: str, img_dir: str = DEFAULT_INPUT_DIR,
                          out_dir: str = DEFAULT_OUTPUT_DIR, **kwargs) -> Dict[str, Any]:
    """Compatibilidad con la versión anterior: procesa una pareja de códigos."""
    return process_items([Item(code1), Item(code2)], img_dir, out_dir, **kwargs)


# =====================================================================
# LÍNEA DE COMANDOS
# =====================================================================
def _parse_size(text: str) -> Tuple[int, int]:
    """'1080' -> (1080, 1080);  '1200x800' -> (1200, 800)."""
    t = text.strip().lower()
    if "x" in t:
        a, b = t.split("x", 1)
        return int(a.strip()), int(b.strip())
    d = int(t)
    return d, d


def _choice(value: str, resolver, what: str) -> str:
    """Traduce una opción de consola a su clave interna o termina el programa con un error."""
    key = resolver(value)
    if key is None:
        print(f"Error: {what} desconocido '{value}'", file=sys.stderr)
        sys.exit(2)
    return key


def _print_warnings(res: Dict[str, Any], prefix: str = "    ") -> None:
    for w in res.get("warnings", []):
        print(f"{prefix}(aviso: {w})")


def main():
    ap = argparse.ArgumentParser(description="Composición de fotos de producto (varios tipos y perspectivas)")
    ap.add_argument("images", nargs="*", help="Rutas de imagen o códigos de 1 o más productos")
    ap.add_argument("-o", "--out", help="Archivo de salida (modos --pair y rutas/códigos posicionales)")
    ap.add_argument("--pair", help="Composición COD1/COD2[/COD3...] con opciones, ej: 30-CRU:lateral/65-CAF")
    ap.add_argument("--list", help="Ruta a un archivo .txt con una composición por línea")
    ap.add_argument("--size", "-s", default="1000", help="Tamaño de lienzo: ej. 1080 o 1080x1080 (por defecto 1000)")
    ap.add_argument("--tipo", default=DEFAULT_PRODUCT,
                    help="Tipo de producto: " + ", ".join(PRODUCT_TYPES) + f" (por defecto {DEFAULT_PRODUCT})")
    ap.add_argument("--perspectiva", default=DEFAULT_PERSPECTIVE,
                    help="Perspectiva por defecto: " + ", ".join(PERSPECTIVES) + " (auto = según nombre del archivo)")
    ap.add_argument("--layout", default=DEFAULT_LAYOUT, help="Distribución: " + ", ".join(LAYOUTS))
    ap.add_argument("--formato", default=DEFAULT_FORMAT,
                    help="Formato de salida: " + ", ".join(FORMATS) + " (pack = 2 productos, tripack = 3)")
    ap.add_argument("--separacion", type=float, default=None,
                    help="Separación entre productos, en %% del ancho (por defecto 4)")
    ap.add_argument("--no-sobrescribir", action="store_true",
                    help="Si el archivo ya existe, crear 'nombre (2).jpg' en vez de reemplazarlo")
    ap.add_argument("--quality", type=int, default=JPG_QUALITY, help="Calidad JPEG (por defecto 95)")
    ap.add_argument("--dir-in", default=DEFAULT_INPUT_DIR, help="Carpeta de imágenes de entrada")
    ap.add_argument("--dir-out", default=DEFAULT_OUTPUT_DIR, help="Carpeta de resultados")
    ap.add_argument("--skip-cutout", action="store_true", help="Omitir recorte de fondo (usar transparencia existente)")
    ap.add_argument("--no-shadow", action="store_true", help="Desactivar generación de sombra suave")
    args = ap.parse_args()

    canvas_w, canvas_h = _parse_size(args.size)

    # Opciones comunes a los tres modos de uso
    common = dict(
        skip_cutout=args.skip_cutout,
        add_shadow=not args.no_shadow,
        canvas_w=canvas_w,
        canvas_h=canvas_h,
        quality=args.quality,
        product=_choice(args.tipo, resolve_product, "tipo de producto"),
        perspective=_choice(args.perspectiva, resolve_perspective, "perspectiva"),
        layout=_choice(args.layout, resolve_layout, "distribución"),
        fmt=_choice(args.formato, resolve_format, "formato"),
        gap_pct=args.separacion,
        overwrite=not args.no_sobrescribir,
    )

    # --- Modo 1: lista de composiciones desde un archivo ---
    if args.list:
        list_file = Path(args.list)
        if not list_file.exists():
            print(f"Error: No existe el archivo de lista '{args.list}'", file=sys.stderr)
            sys.exit(1)

        with open(list_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total = 0
        success = 0
        for line in lines:
            items = parse_code_line(line)
            if not items:
                continue                                  # línea vacía o comentario
            total += 1
            print(f"[{total}] Procesando {' / '.join(i.label() for i in items)}...")
            res = process_items(items, args.dir_in, args.dir_out, **common)
            if res["ok"]:
                success += 1
                print(f"  OK -> {res['out_path']} ({res.get('dimensions', '')})")
            else:
                print(f"  ERROR: {res['error']}", file=sys.stderr)
            _print_warnings(res)

        print(f"\nFinalizado: {success}/{total} imágenes creadas en '{args.dir_out}'")
        sys.exit(0 if success == total else 1)

    # --- Modo 2: una composición indicada con --pair ---
    if args.pair:
        items = parse_code_line(args.pair)
        if not items:
            print("Error: Formato inválido para --pair. Use ej: 30-CRU/65-CAF", file=sys.stderr)
            sys.exit(1)
        res = process_items(items, args.dir_in, args.dir_out, out_path=args.out, **common)
        _print_warnings(res, prefix="")
        if res["ok"]:
            print(f"OK -> {res['out_path']} ({res.get('dimensions', '')})")
            sys.exit(0)
        print(f"ERROR: {res['error']}", file=sys.stderr)
        sys.exit(1)

    # --- Modo 3: rutas de archivo o códigos como argumentos (1 o más) ---
    if args.images:
        items = []
        for token in args.images:
            if Path(token).exists():
                items.append(Item(code=Path(token).stem, path=Path(token)))   # ruta directa
            else:
                it = parse_item(token)                                        # código (con opciones)
                if it:
                    items.append(it)
        res = process_items(items, args.dir_in, args.dir_out, out_path=args.out or "resultado.jpg", **common)
        _print_warnings(res, prefix="")
        if res["ok"]:
            print(f"OK -> {res['out_path']} ({canvas_w}x{canvas_h})")
            sys.exit(0)
        print(f"ERROR: {res['error']}", file=sys.stderr)
        sys.exit(1)

    ap.print_help()


if __name__ == "__main__":
    main()
