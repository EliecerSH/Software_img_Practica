# 🛍️ Generador de imágenes de producto — Pack y Tripack

Software local en Python (Windows) con interfaz de escritorio que genera, de forma masiva, las imágenes de **pack (2 productos)** y **tripack (3 productos)** para un marketplace a partir de las fotos individuales que ya existen. Recorta el fondo y ensambla los productos sobre fondo blanco puro con sombra natural, con tamaño, compresión y nombre de archivo estandarizados. También admite composiciones libres de 1 o más productos. Funciona con **distintos tipos de producto** (calzado, bolsos, ropa, accesorios, otros) y con **distintas perspectivas** de la foto (lateral, 3/4, frontal, trasera, superior, inferior). Incluye búsqueda por códigos, dimensiones configurables y registro de aciertos y errores.

---

## ⚡ Inicio Rápido
- Haz doble clic en **`iniciar_software.bat`** (abre la interfaz).
- Primera vez: `pip install -r requirements.txt`.
- ⚠️ Si existe un `.exe` de una versión anterior, corresponde al código viejo. Para usar las nuevas funciones hay que volver a generarlo (ver al final) o usar `iniciar_software.bat`.

---

## 🆕 Novedades de esta versión

### 👁 Vista previa y comparación de configuraciones
La pestaña **Vista Previa** dibuja la composición **sin guardar nada**, con la misma configuración que se usará al procesar (el mismo código arma la previa y el archivo final).
- **Qué composición ver:** el selector de la pestaña, las flechas ◀ ▶ o simplemente poner el cursor en una línea del editor. El botón **👁 Previsualizar** del editor abre la pestaña directamente.
- **Se actualiza sola** al cambiar formato, tipo, perspectiva, distribución, separación, sombra, recorte o tamaño (se puede apagar con *Actualizar al cambiar opciones*).
- **Comparar** (barra superior de la pestaña): dibuja la misma composición con varias opciones lado a lado — *distribución* (automática, fila, cuadrícula, diagonal), *sombra* (con / sin) o *separación* (0, 4, 8 y 12 %). **Un clic en un recuadro aplica esa opción** a la configuración; el recuadro vigente aparece resaltado.
- Si falta una foto, está dañada o la línea no cumple el formato, la previa muestra el mismo mensaje que daría el proceso.
- Es rápida: el recorte con IA se hace una sola vez por foto y queda en memoria (caché), también durante el procesamiento por lotes.
- Desde consola: `previa.py` (`render_preview`, `render_variants`) no depende de la interfaz.

### 📦 Formato de salida: Libre, Pack o Tripack
Se elige en **Producto → Formato** (o `--formato libre|pack|tripack` en consola).

| Formato | Productos | Con un solo código | Nombre del archivo |
|---|---|---|---|
| Libre | los que tenga la línea | un producto | `30-CRU-65-CAF.jpg` |
| Pack | 2 | se repite el mismo producto | `30-CRU_pack.jpg` / `30-CRU-65-CAF_pack.jpg` |
| Tripack | 3 | se repite el mismo producto | `30-CRU_tripack.jpg` / `30-CRU-65-CAF-10-NEG_tripack.jpg` |

Si una línea no tiene la cantidad exigida (ej. 3 códigos en formato Pack) esa composición se informa como error y el resto del lote continúa.

### ✅ Otras mejoras
- **Validación de fotos de origen:** una foto dañada o con menos de 300 px por lado se informa como error y no detiene el lote.
- **Separación entre productos** configurable (0–15 % del ancho).
- **Archivos existentes:** el interruptor *Reemplazar si el archivo ya existe* (activo por defecto); apagado, se crea `nombre (2).jpg` en vez de sobrescribir (`--no-sobrescribir` en consola).

---

## 🆕 Qué cambió en versiones anteriores

### 1. 🧩 Tipos de producto
Se elige en la interfaz (**Producto → Tipo**) o con `--tipo` en consola. Cada tipo ajusta la limpieza del recorte y la sombra por defecto:

| Tipo | Clave | Sombra por defecto | Limpieza del recorte |
|---|---|---|---|
| Calzado | `calzado` | Apoyado en el piso | Conserva solo la pieza más grande |
| Bolso / Cartera / Mochila | `bolso` | Apoyado en el piso | Conserva piezas separadas (asas, correas) |
| Ropa / Prenda | `ropa` | Sombra proyectada suave | Conserva piezas separadas |
| Accesorio / Joyería | `accesorio` | Sombra proyectada suave | Conserva piezas separadas |
| Genérico | `generico` | Sombra proyectada suave | Conserva piezas separadas |

### 2. 🎥 Perspectivas
| Perspectiva | Clave (alias) | Comportamiento |
|---|---|---|
| Lateral / Perfil | `lateral` (`lat`, `side`, `perfil`) | Sombra de contacto, base común |
| 3/4 | `tres_cuartos` (`3q`, `angulo`) | Sombra de contacto, base común |
| Frontal | `frontal` (`front`, `frente`) | Sombra de contacto, base común |
| Trasera | `trasera` (`back`, `rear`) | Sombra de contacto, base común |
| Superior / Plano | `superior` (`top`, `plano`, `flat`) | Sombra proyectada, centrado vertical |
| Inferior / Suela | `inferior` (`suela`, `sole`) | Sombra proyectada, centrado vertical |
| Automática | `auto` | Se deduce del nombre del archivo; si no hay etiqueta, usa lo que corresponde al tipo |

La **sombra de contacto** ya no es una elipse fija: sigue la huella real de la silueta del producto, así que sirve para cualquier perspectiva. Con perspectivas mezcladas en una misma imagen, cada producto lleva su propia sombra.

### 3. 📝 Sintaxis de `codigos.txt` (una imagen por línea)
```text
30-CRU/65-CAF                              # dos productos lado a lado (como antes)
30-CRU/65-CAF/10-NEG                       # tres productos en una fila
30-CRU/65-CAF/10-NEG/15-ROJ                # cuatro: cuadrícula 2x2 automática
BOL-01                                     # un solo producto
30-CRU:lateral/30-CRU:3q/30-CRU:frontal    # mismo modelo en 3 perspectivas
BOL-01:bolso:frontal/BOL-02:frontal        # tipo y perspectiva por producto
CAM-01:ropa                                # tipo de producto en la línea
```
- Separadores válidos: `/`, `|`, `,`, `;` o ` - `.
- El tipo escrito en un producto se hereda al resto de la línea.
- La perspectiva que se elige en la interfaz (si no es "Automática") se aplica a los productos que no la indiquen en la línea.

### 4. 🔎 Varias fotos del mismo producto
Guarda cada perspectiva con una etiqueta en el nombre, en la carpeta `imagenes/`:
```text
30-CRU.jpg              <- foto "normal" (se usa si no se pide otra)
30-CRU_lateral.jpg
30-CRU_3q.png
30-CRU-frontal.webp
30-CRU_superior.jpg
```
Al pedir `30-CRU:frontal` se usa `30-CRU-frontal.webp`. Si el archivo etiquetado no existe, usa el que haya y deja un aviso en el log y en el CSV cuando el archivo parece de otra perspectiva.

### 5. 📐 Distribución
`Automática` (hasta 3 productos en una fila; 4 o más en cuadrícula), `Una fila`, `Cuadrícula` o `Diagonal escalonada` (cascada de arriba‑izquierda a abajo‑derecha, ideal para 3 o 4 colores del mismo modelo: `--layout diagonal`). Cada producto se escala para caber en su celda (ancho y alto), así que productos altos como bolsos o prendas ya no se salen del lienzo.

### 6. ⚪ Limpieza que respeta productos blancos
Antes, todo píxel blanco se borraba; un producto blanco quedaba con huecos. Ahora solo se elimina el blanco conectado al borde de la imagen (el fondo).

### Lo ya existente
Resoluciones 1000 / 1080 / 1200 / personalizada, calidad JPEG, modo oscuro/claro, contador en vivo, tabla de aciertos/errores con filtros, logs, vista previa y CSV automático en `resultados/registro_aciertos_errores.csv` (ahora con columnas de tipo, perspectiva y avisos).

---

## 📁 Estructura

```text
Software_img_Practica/
├── imagenes/               <-- Fotos de entrada (ej: 30-CRU.jpg, 30-CRU_lateral.jpg, BOL-01_frontal.png)
├── resultados/             <-- JPG combinados y reporte CSV
├── codigos.txt             <-- Listado de composiciones
├── main.py                 <-- Punto de entrada (GUI o CLI)
├── app_gui.py              <-- Interfaz gráfica (CustomTkinter)
├── pipeline.py             <-- Orquestador y consola: junta los módulos de abajo
├── previa.py               <-- Vista previa y comparación de configuraciones (sin guardar archivos)
├── catalogo.py             <-- Tipos de producto, perspectivas y distribuciones (tablas editables)
├── codigos.py              <-- Lectura de líneas de códigos y búsqueda de fotos
├── imagen.py               <-- Recorte de fondo, limpieza y ajuste de cada foto
├── composicion.py          <-- Distribuciones, sombras, ensamblado y verificación
├── iniciar_software.bat    <-- Abre la interfaz
└── procesar_lista.bat      <-- Procesa codigos.txt por consola
```

---

## 💻 Línea de comandos

```bash
# Un par de calzado (como antes)
python main.py --pair 30-CRU/65-CAF --size 1080

# Bolsos, vista frontal
python main.py --pair BOL-01/BOL-02 --tipo bolso --perspectiva frontal

# Perspectivas distintas del mismo producto en una sola imagen
python main.py --pair "30-CRU:lateral/30-CRU:3q/30-CRU:frontal"

# Pack y tripack (con un solo código se repite el mismo producto)
python main.py --pair 30-CRU --formato pack
python main.py --pair 30-CRU/65-CAF/10-NEG --formato tripack

# Lista completa, cuadrícula forzada
python main.py --list codigos.txt --size 1080 --layout cuadricula

# Rutas directas (1 o más imágenes)
python main.py foto1.jpg foto2.jpg -o resultado.jpg --tipo accesorio --perspectiva superior
```
Opciones: `--formato {libre,pack,tripack}`, `--separacion %`, `--no-sobrescribir`, `--tipo`, `--perspectiva`, `--layout {auto,fila,cuadricula,diagonal}`, `--size`, `--quality`, `--dir-in`, `--dir-out`, `--skip-cutout`, `--no-shadow`.

---

## 🧱 Cómo extender el programa
- **Nuevo tipo de producto o perspectiva:** agrega una entrada en `PRODUCT_TYPES` o `PERSPECTIVES` (`catalogo.py`). La interfaz, la consola y la búsqueda de archivos la reconocen sola.
- **Nueva distribución:** escribe una función `_place_xxx` en `composicion.py` (copia la forma de `_place_diagonal`), regístrala en `PLACERS` y agrega su nombre en `LAYOUTS` (`catalogo.py`).
- Flujo completo de una línea: `codigos.py` (leer y buscar) → `imagen.py` (validar, recortar y limpiar) → `composicion.py` (ubicar y sombrear), coordinado por `pipeline.prepare()` + `process_items()` (guarda) o `previa.py` (solo dibuja en memoria).
- **Nueva comparación en la vista previa:** agrega una entrada en `previa.COMPARE_KINDS` y su caso en `variant_specs()`.

## 🛠️ Volver a generar el .exe
El `.exe` empaqueta el código viejo. Para actualizarlo, en Windows:
```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name GeneradorImagenes --collect-all customtkinter --collect-all rembg main.py
```

## ⚠️ Límites conocidos
- La primera vez que se usa el recorte con IA, `rembg` descarga su modelo (requiere Internet una sola vez); después funciona sin conexión.
- El recorte lo hace `rembg` (modelo general). En ropa puesta sobre modelo o en productos muy brillantes/transparentes puede necesitar fotos con fondo liso.
- Cuando se mezclan productos de formas muy distintas en una imagen, cada uno se ajusta a su celda; no se conserva la escala real entre ellos.
