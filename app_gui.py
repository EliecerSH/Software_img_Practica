"""
Interfaz Gráfica de Usuario Moderna y Responsiva (CustomTkinter)
para el Generador de imágenes de producto (pack y tripack).
Incluye:
  - Formato de salida: Libre, Pack (2 productos) o Tripack (3 productos)
  - Configuración dinámica del tamaño del lienzo (1000px, 1080px, 1200px, Personalizado)
  - Tipo de producto (calzado, bolso, ropa, accesorio, genérico) y perspectiva (lateral, 3/4, frontal...)
  - Distribución (fila, cuadrícula, diagonal), separación entre productos y sombra
  - VISTA PREVIA de la composición antes de procesar y COMPARACIÓN de configuraciones
    (distribución, sombra y separación) lado a lado
  - Entrada de códigos interactiva con contador en vivo
  - Consola de logs con marcas de tiempo en tiempo real
  - Registro completo de aciertos y errores con filtros y exportación a CSV
  - Previsualización gráfica de alta calidad
  - Diseño responsivo con soporte para Modo Oscuro y Modo Claro
"""
import os
import sys
import csv
import threading
import subprocess
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageTk

import pipeline
import previa

# Configuración visual global
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Generador de imágenes de producto — Pack y Tripack")
        self.geometry("1240x920")
        self.minsize(1040, 780)

        # Variables de configuración
        self.input_dir_var = tk.StringVar(value=str(Path(pipeline.DEFAULT_INPUT_DIR).resolve()))
        self.output_dir_var = tk.StringVar(value=str(Path(pipeline.DEFAULT_OUTPUT_DIR).resolve()))
        
        # Tamaño de lienzo
        self.canvas_w_var = tk.StringVar(value="1080")
        self.canvas_h_var = tk.StringVar(value="1080")
        self.quality_var = tk.StringVar(value="95")

        # Tipo de producto, perspectiva y distribución (etiqueta visible -> clave interna)
        self.product_labels = {p.label: k for k, p in pipeline.PRODUCT_TYPES.items()}
        self.persp_labels = {p.label: k for k, p in pipeline.PERSPECTIVES.items()}
        self.layout_labels = {label: k for k, label in pipeline.LAYOUTS.items()}
        self.product_var = tk.StringVar(value=pipeline.PRODUCT_TYPES[pipeline.DEFAULT_PRODUCT].label)
        self.persp_var = tk.StringVar(value=pipeline.PERSPECTIVES[pipeline.DEFAULT_PERSPECTIVE].label)
        self.layout_var = tk.StringVar(value=pipeline.LAYOUTS["auto"])
        self.format_labels = {label: k for k, label in pipeline.FORMATS.items()}
        self.format_var = tk.StringVar(value=pipeline.FORMATS[pipeline.DEFAULT_FORMAT])
        self.gap_var = tk.DoubleVar(value=4)                 # separación entre productos (% del ancho)
        self.overwrite_var = tk.BooleanVar(value=True)       # reemplazar archivos que ya existen

        # Opciones
        self.cutout_var = tk.BooleanVar(value=True)
        self.shadow_var = tk.BooleanVar(value=True)
        self.is_processing = False

        # Datos de registros y filtros
        self.records = []
        self.current_filter = "ALL"
        self.last_generated_image = None
        self.preview_image_ctk = None

        # Vista previa
        self.auto_preview_var = tk.BooleanVar(value=True)    # actualizar sola al cambiar opciones
        self.comp_var = tk.StringVar(value="(sin composiciones)")
        self.compositions = []          # [(n.º de línea del editor, [Item], texto)] de las líneas válidas
        self._prev_job = None           # after() pendiente (retardo para no redibujar en cada tecla)
        self._prev_token = 0            # identifica la última solicitud; las respuestas viejas se descartan
        self._prev_dirty = True         # hay cambios que aún no se reflejan en la vista previa
        self._prev_images = []          # referencias para que Tk no libere las imágenes mostradas

        self._build_ui()
        self._load_default_codes()
        for var in (self.product_var, self.persp_var, self.layout_var, self.format_var, self.canvas_w_var,
                    self.canvas_h_var, self.gap_var, self.cutout_var, self.shadow_var):
            var.trace_add("write", self._on_setting_changed)

    def _build_ui(self):
        # Configurar grid principal responsivo
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ---------------- 1. ENCABEZADO MODERNO ----------------
        header = ctk.CTkFrame(self, corner_radius=0, fg_color=("#E2E8F0", "#111827"), height=64)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        # Título y subtítulo
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        title_lbl = ctk.CTkLabel(
            title_box,
            text="🛍️ Generador de imágenes de producto",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_lbl.pack(anchor="w")

        sub_lbl = ctk.CTkLabel(
            title_box,
            text="Pack y tripack para marketplace | Tamaño, compresión y nombre estandarizados | Fondo blanco puro #FFFFFF | Búsqueda por códigos | Vista previa",
            font=ctk.CTkFont(size=12),
            text_color=("gray50", "gray70")
        )
        sub_lbl.pack(anchor="w")

        # Selector de Tema (Oscuro / Claro)
        theme_box = ctk.CTkFrame(header, fg_color="transparent")
        theme_box.grid(row=0, column=2, padx=20, pady=10, sticky="e")

        self.theme_switch = ctk.CTkSwitch(
            theme_box,
            text="Modo Oscuro",
            command=self._toggle_theme,
            onvalue="Dark",
            offvalue="Light",
            font=ctk.CTkFont(size=12)
        )
        self.theme_switch.select()
        self.theme_switch.pack()

        # ---------------- 2. PANEL DE CONFIGURACIÓN Y TAMAÑO ----------------
        config_card = ctk.CTkFrame(self, corner_radius=12, fg_color=("#F8FAFC", "#1F2937"))
        config_card.grid(row=1, column=0, padx=16, pady=(12, 6), sticky="ew")
        config_card.grid_columnconfigure(1, weight=1)
        config_card.grid_columnconfigure(3, weight=1)

        # Fila 1: Tamaño de Lienzo (Resolución)
        size_lbl = ctk.CTkLabel(config_card, text="📐 Resolución Lienzo:", font=ctk.CTkFont(size=12, weight="bold"))
        size_lbl.grid(row=0, column=0, padx=(16, 8), pady=8, sticky="w")

        self.size_preset = ctk.CTkSegmentedButton(
            config_card,
            values=["1000 x 1000", "1080 x 1080", "1200 x 1200", "Personalizado"],
            command=self._on_preset_change,
            font=ctk.CTkFont(size=11, weight="bold")
        )
        self.size_preset.set("1080 x 1080")
        self.size_preset.grid(row=0, column=1, padx=6, pady=8, sticky="w")

        # Inputs Ancho x Alto
        dims_box = ctk.CTkFrame(config_card, fg_color="transparent")
        dims_box.grid(row=0, column=2, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(dims_box, text="Ancho:", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT, padx=(0, 4))
        self.entry_w = ctk.CTkEntry(dims_box, textvariable=self.canvas_w_var, width=64, font=ctk.CTkFont(size=11))
        self.entry_w.pack(side=tk.LEFT, padx=(0, 8))

        ctk.CTkLabel(dims_box, text="Alto:", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT, padx=(0, 4))
        self.entry_h = ctk.CTkEntry(dims_box, textvariable=self.canvas_h_var, width=64, font=ctk.CTkFont(size=11))
        self.entry_h.pack(side=tk.LEFT, padx=(0, 8))

        ctk.CTkLabel(dims_box, text="px  |  Calidad:", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT, padx=(0, 4))
        self.entry_q = ctk.CTkEntry(dims_box, textvariable=self.quality_var, width=48, font=ctk.CTkFont(size=11))
        self.entry_q.pack(side=tk.LEFT, padx=(0, 4))
        ctk.CTkLabel(dims_box, text="%", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT)

        # Fila 2: Carpetas de Trabajo
        # Origen
        in_lbl = ctk.CTkLabel(config_card, text="📁 Carpeta Imágenes:", font=ctk.CTkFont(size=12, weight="bold"))
        in_lbl.grid(row=1, column=0, padx=(16, 8), pady=(0, 8), sticky="w")

        in_box = ctk.CTkFrame(config_card, fg_color="transparent")
        in_box.grid(row=1, column=1, columnspan=2, padx=6, pady=(0, 8), sticky="ew")
        in_box.grid_columnconfigure(0, weight=1)

        in_entry = ctk.CTkEntry(in_box, textvariable=self.input_dir_var, font=ctk.CTkFont(size=11))
        in_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(in_box, text="Examinar", width=80, command=self._browse_input_dir, font=ctk.CTkFont(size=11)).grid(row=0, column=1, padx=3)
        ctk.CTkButton(in_box, text="Abrir", width=65, fg_color="gray40", hover_color="gray30", command=lambda: self._open_dir(self.input_dir_var.get()), font=ctk.CTkFont(size=11)).grid(row=0, column=2, padx=(3, 0))

        # Destino
        out_lbl = ctk.CTkLabel(config_card, text="💾 Carpeta Resultados:", font=ctk.CTkFont(size=12, weight="bold"))
        out_lbl.grid(row=2, column=0, padx=(16, 8), pady=(0, 8), sticky="w")

        out_box = ctk.CTkFrame(config_card, fg_color="transparent")
        out_box.grid(row=2, column=1, columnspan=2, padx=6, pady=(0, 8), sticky="ew")
        out_box.grid_columnconfigure(0, weight=1)

        out_entry = ctk.CTkEntry(out_box, textvariable=self.output_dir_var, font=ctk.CTkFont(size=11))
        out_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(out_box, text="Examinar", width=80, command=self._browse_output_dir, font=ctk.CTkFont(size=11)).grid(row=0, column=1, padx=3)
        ctk.CTkButton(out_box, text="Abrir", width=65, fg_color="gray40", hover_color="gray30", command=lambda: self._open_dir(self.output_dir_var.get()), font=ctk.CTkFont(size=11)).grid(row=0, column=2, padx=(3, 0))

        # Fila 3: Tipo de producto, perspectiva y distribución
        prod_lbl = ctk.CTkLabel(config_card, text="🧩 Producto:", font=ctk.CTkFont(size=12, weight="bold"))
        prod_lbl.grid(row=3, column=0, padx=(16, 8), pady=(0, 10), sticky="w")

        prod_box = ctk.CTkFrame(config_card, fg_color="transparent")
        prod_box.grid(row=3, column=1, columnspan=3, padx=6, pady=(0, 10), sticky="w")

        ctk.CTkLabel(prod_box, text="Formato:", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT, padx=(0, 4))
        ctk.CTkOptionMenu(
            prod_box, variable=self.format_var, values=list(self.format_labels),
            width=190, font=ctk.CTkFont(size=11)
        ).pack(side=tk.LEFT, padx=(0, 14))

        ctk.CTkLabel(prod_box, text="Tipo:", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT, padx=(0, 4))
        ctk.CTkOptionMenu(
            prod_box, variable=self.product_var, values=list(self.product_labels),
            width=180, font=ctk.CTkFont(size=11)
        ).pack(side=tk.LEFT, padx=(0, 14))

        ctk.CTkLabel(prod_box, text="Perspectiva:", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT, padx=(0, 4))
        ctk.CTkOptionMenu(
            prod_box, variable=self.persp_var, values=list(self.persp_labels),
            width=230, font=ctk.CTkFont(size=11)
        ).pack(side=tk.LEFT)

        # Fila 4: distribución, separación y archivos existentes
        lay_lbl = ctk.CTkLabel(config_card, text="🧱 Composición:", font=ctk.CTkFont(size=12, weight="bold"))
        lay_lbl.grid(row=4, column=0, padx=(16, 8), pady=(0, 10), sticky="w")

        lay_box = ctk.CTkFrame(config_card, fg_color="transparent")
        lay_box.grid(row=4, column=1, columnspan=3, padx=6, pady=(0, 10), sticky="w")

        ctk.CTkLabel(lay_box, text="Distribución:", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT, padx=(0, 4))
        ctk.CTkOptionMenu(
            lay_box, variable=self.layout_var, values=list(self.layout_labels),
            width=170, font=ctk.CTkFont(size=11)
        ).pack(side=tk.LEFT, padx=(0, 14))

        ctk.CTkLabel(lay_box, text="Separación:", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT, padx=(0, 4))
        ctk.CTkSlider(lay_box, from_=0, to=15, number_of_steps=15, variable=self.gap_var, width=130).pack(side=tk.LEFT)
        self.gap_lbl = ctk.CTkLabel(lay_box, text="4 %", width=36, font=ctk.CTkFont(size=11))
        self.gap_lbl.pack(side=tk.LEFT, padx=(4, 14))
        self.gap_var.trace_add("write", lambda *_: self.gap_lbl.configure(text=f"{self.gap_var.get():.0f} %"))

        ctk.CTkSwitch(
            lay_box, text="Reemplazar si el archivo ya existe", variable=self.overwrite_var,
            font=ctk.CTkFont(size=11)
        ).pack(side=tk.LEFT)

        # ---------------- 3. CUERPO PRINCIPAL (2 COLUMNAS RESPONSIVAS) ----------------
        main_panes = ctk.CTkFrame(self, fg_color="transparent")
        main_panes.grid(row=2, column=0, padx=16, pady=6, sticky="nsew")
        main_panes.grid_rowconfigure(0, weight=1)
        main_panes.grid_columnconfigure(0, weight=4, minsize=340)  # Columna Códigos
        main_panes.grid_columnconfigure(1, weight=6, minsize=520)  # Columna Tabs

        # COLUMNA IZQUIERDA: ENTRADA DE CÓDIGOS
        left_card = ctk.CTkFrame(main_panes, corner_radius=12, fg_color=("#F8FAFC", "#1F2937"))
        left_card.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="nsew")
        left_card.grid_rowconfigure(2, weight=1)
        left_card.grid_columnconfigure(0, weight=1)

        # Header de la tarjeta izquierda
        left_header = ctk.CTkFrame(left_card, fg_color="transparent")
        left_header.grid(row=0, column=0, padx=14, pady=(12, 6), sticky="ew")

        ctk.CTkLabel(
            left_header,
            text="📝 Listado de Códigos",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side=tk.LEFT)

        # Barra de botones del editor
        tools_row = ctk.CTkFrame(left_card, fg_color="transparent")
        tools_row.grid(row=1, column=0, padx=14, pady=4, sticky="ew")

        ctk.CTkButton(tools_row, text="📂 Cargar .txt", width=85, command=self._load_txt_file, font=ctk.CTkFont(size=11)).pack(side=tk.LEFT, padx=(0, 4))
        ctk.CTkButton(tools_row, text="📋 Pegar", width=65, fg_color="gray40", hover_color="gray30", command=self._paste_clipboard, font=ctk.CTkFont(size=11)).pack(side=tk.LEFT, padx=4)
        ctk.CTkButton(tools_row, text="💾 Guardar", width=70, fg_color="gray40", hover_color="gray30", command=self._save_txt_file, font=ctk.CTkFont(size=11)).pack(side=tk.LEFT, padx=4)
        ctk.CTkButton(tools_row, text="👁 Previsualizar", width=105, fg_color="#7C3AED", hover_color="#6D28D9", command=self._preview_from_editor, font=ctk.CTkFont(size=11, weight="bold")).pack(side=tk.LEFT, padx=4)
        ctk.CTkButton(tools_row, text="🧹 Limpiar", width=65, fg_color="#DC2626", hover_color="#B91C1C", command=self._clear_codes, font=ctk.CTkFont(size=11)).pack(side=tk.RIGHT)

        # Editor de texto multilínea
        self.codes_box = ctk.CTkTextbox(
            left_card,
            font=ctk.CTkFont(family="Consolas", size=13),
            corner_radius=8,
            wrap="none"
        )
        self.codes_box.grid(row=2, column=0, padx=14, pady=6, sticky="nsew")
        self.codes_box.bind("<KeyRelease>", self._on_codes_change)
        self.codes_box.bind("<ButtonRelease-1>", self._sync_cursor_comp)

        # Opciones y contador inferior
        left_footer = ctk.CTkFrame(left_card, fg_color="transparent")
        left_footer.grid(row=3, column=0, padx=14, pady=(4, 12), sticky="ew")

        self.codes_count_lbl = ctk.CTkLabel(
            left_footer,
            text="🔢 0 composiciones detectadas",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#2563EB", "#60A5FA")
        )
        self.codes_count_lbl.pack(anchor="w", pady=(0, 2))

        ctk.CTkLabel(
            left_footer,
            text="Una línea = una imagen: COD1/COD2/COD3 ...  (Pack/Tripack: un solo código se repite)\n"
                 "Opciones por producto: COD:lateral  COD:3q  COD:frontal  COD:trasera  COD:superior\n"
                 "Tipo en la línea: COD:bolso  COD:ropa  COD:accesorio  COD:generico",
            font=ctk.CTkFont(size=10),
            justify="left",
            text_color=("gray40", "gray65")
        ).pack(anchor="w", pady=(0, 6))

        switches_box = ctk.CTkFrame(left_footer, fg_color="transparent")
        switches_box.pack(fill=tk.X)

        self.sw_cutout = ctk.CTkSwitch(
            switches_box,
            text="Quitar fondo con IA (rembg)",
            variable=self.cutout_var,
            font=ctk.CTkFont(size=11)
        )
        self.sw_cutout.pack(side=tk.LEFT, padx=(0, 10))

        self.sw_shadow = ctk.CTkSwitch(
            switches_box,
            text="Sombra difusa",
            variable=self.shadow_var,
            font=ctk.CTkFont(size=11)
        )
        self.sw_shadow.pack(side=tk.LEFT)

        # COLUMNA DERECHA: TABVIEW RESPONSIVO
        self.tabview = ctk.CTkTabview(main_panes, corner_radius=12, fg_color=("#F8FAFC", "#1F2937"),
                                      command=self._on_tab_changed)
        self.tabview.grid(row=0, column=1, padx=(8, 0), pady=0, sticky="nsew")

        # Pestañas
        self.tab_records = self.tabview.add("📊 Registro de Aciertos y Errores")
        self.tab_logs = self.tabview.add("📜 Consola de Logs")
        self.tab_preview = self.tabview.add("🖼️ Vista Previa")

        self._build_tab_records()
        self._build_tab_logs()
        self._build_tab_preview()

        # ---------------- 4. BARRA DE ACCIÓN Y PROGRESO (INFERIOR) ----------------
        bottom_bar = ctk.CTkFrame(self, corner_radius=12, fg_color=("#F8FAFC", "#1F2937"))
        bottom_bar.grid(row=3, column=0, padx=16, pady=(6, 14), sticky="ew")
        bottom_bar.grid_columnconfigure(0, weight=1)

        # Barra de progreso
        self.prog_bar = ctk.CTkProgressBar(bottom_bar, height=12, corner_radius=6)
        self.prog_bar.set(0)
        self.prog_bar.grid(row=0, column=0, columnspan=2, padx=16, pady=(12, 8), sticky="ew")

        # Fila de Estado y Botón de Inicio
        status_box = ctk.CTkFrame(bottom_bar, fg_color="transparent")
        status_box.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="w")

        self.status_lbl = ctk.CTkLabel(
            status_box,
            text="Listo para procesar",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("gray20", "gray85")
        )
        self.status_lbl.pack(anchor="w")

        actions_box = ctk.CTkFrame(bottom_bar, fg_color="transparent")
        actions_box.grid(row=1, column=1, padx=16, pady=(0, 10), sticky="e")

        ctk.CTkButton(
            actions_box,
            text="📂 Abrir Resultados",
            width=130,
            height=38,
            fg_color="gray40",
            hover_color="gray30",
            command=lambda: self._open_dir(self.output_dir_var.get()),
            font=ctk.CTkFont(size=12)
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.btn_run = ctk.CTkButton(
            actions_box,
            text="▶ INICIAR PROCESAMIENTO",
            width=210,
            height=38,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_processing
        )
        self.btn_run.pack(side=tk.LEFT)

    # ---------------- CONSTRUCCIÓN DE PESTAÑAS ----------------
    def _build_tab_records(self):
        self.tab_records.grid_rowconfigure(2, weight=1)
        self.tab_records.grid_columnconfigure(0, weight=1)

        # 1. Tarjetas Métricas
        metrics_bar = ctk.CTkFrame(self.tab_records, fg_color="transparent")
        metrics_bar.grid(row=0, column=0, pady=(4, 8), sticky="ew")
        metrics_bar.grid_columnconfigure((0, 1, 2), weight=1)

        # Card Aciertos
        c_acc = ctk.CTkFrame(metrics_bar, corner_radius=8, fg_color=("#DCFCE7", "#064E3B"))
        c_acc.grid(row=0, column=0, padx=4, sticky="ew")
        ctk.CTkLabel(c_acc, text="ACIERTOS", font=ctk.CTkFont(size=10, weight="bold"), text_color=("#166534", "#A7F3D0")).pack(pady=(4, 0))
        self.lbl_acc_val = ctk.CTkLabel(c_acc, text="0", font=ctk.CTkFont(size=18, weight="bold"), text_color=("#166534", "#FFFFFF"))
        self.lbl_acc_val.pack(pady=(0, 4))

        # Card Errores
        c_err = ctk.CTkFrame(metrics_bar, corner_radius=8, fg_color=("#FEE2E2", "#7F1D1D"))
        c_err.grid(row=0, column=1, padx=4, sticky="ew")
        ctk.CTkLabel(c_err, text="ERRORES", font=ctk.CTkFont(size=10, weight="bold"), text_color=("#991B1B", "#FECACA")).pack(pady=(4, 0))
        self.lbl_err_val = ctk.CTkLabel(c_err, text="0", font=ctk.CTkFont(size=18, weight="bold"), text_color=("#991B1B", "#FFFFFF"))
        self.lbl_err_val.pack(pady=(0, 4))

        # Card Total
        c_tot = ctk.CTkFrame(metrics_bar, corner_radius=8, fg_color=("#E0E7FF", "#1E1B4B"))
        c_tot.grid(row=0, column=2, padx=4, sticky="ew")
        ctk.CTkLabel(c_tot, text="TOTAL", font=ctk.CTkFont(size=10, weight="bold"), text_color=("#3730A3", "#C7D2FE")).pack(pady=(4, 0))
        self.lbl_tot_val = ctk.CTkLabel(c_tot, text="0", font=ctk.CTkFont(size=18, weight="bold"), text_color=("#3730A3", "#FFFFFF"))
        self.lbl_tot_val.pack(pady=(0, 4))

        # 2. Barra de Filtros y Exportación
        filter_bar = ctk.CTkFrame(self.tab_records, fg_color="transparent")
        filter_bar.grid(row=1, column=0, pady=(0, 6), sticky="ew")

        ctk.CTkLabel(filter_bar, text="Filtro:", font=ctk.CTkFont(size=11, weight="bold")).pack(side=tk.LEFT, padx=(0, 6))

        self.seg_filter = ctk.CTkSegmentedButton(
            filter_bar,
            values=["Todos (0)", "✅ Aciertos (0)", "❌ Errores (0)"],
            command=self._on_filter_changed,
            font=ctk.CTkFont(size=11)
        )
        self.seg_filter.set("Todos (0)")
        self.seg_filter.pack(side=tk.LEFT)

        ctk.CTkButton(
            filter_bar,
            text="📊 Exportar CSV",
            width=110,
            command=self._export_csv,
            fg_color="#0284C7",
            hover_color="#0369A1",
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(side=tk.RIGHT)

        # 3. Tabla Treeview Moderna
        tree_frame = ctk.CTkFrame(self.tab_records, corner_radius=8, fg_color=("#FFFFFF", "#111827"))
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        columns = ("id", "pair", "status", "detail", "time")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("id", text="#")
        self.tree.heading("pair", text="Composición")
        self.tree.heading("status", text="Estado")
        self.tree.heading("detail", text="Detalle / Archivo Generado")
        self.tree.heading("time", text="Hora")

        self.tree.column("id", width=38, anchor="center")
        self.tree.column("pair", width=170, anchor="w")
        self.tree.column("status", width=95, anchor="center")
        self.tree.column("detail", width=310, anchor="w")
        self.tree.column("time", width=75, anchor="center")

        tree_scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll_y.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")

        self.tree.tag_configure("ok_tag", foreground="#059669")
        self.tree.tag_configure("error_tag", foreground="#DC2626")

        self.tree.bind("<Double-1>", self._on_tree_double_click)

        hint = ctk.CTkLabel(
            self.tab_records,
            text="💡 Doble clic en una fila para abrir la imagen resultante o examinar el motivo de error.",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color=("gray50", "gray60")
        )
        hint.grid(row=3, column=0, pady=(4, 0), sticky="w")

    def _build_tab_logs(self):
        self.tab_logs.grid_rowconfigure(1, weight=1)
        self.tab_logs.grid_columnconfigure(0, weight=1)

        log_tools = ctk.CTkFrame(self.tab_logs, fg_color="transparent")
        log_tools.grid(row=0, column=0, pady=(0, 6), sticky="ew")

        ctk.CTkLabel(log_tools, text="Consola de Eventos y Registro Técnico:", font=ctk.CTkFont(size=12, weight="bold")).pack(side=tk.LEFT)

        ctk.CTkButton(log_tools, text="Limpiar", width=65, fg_color="gray40", hover_color="gray30", command=self._clear_logs, font=ctk.CTkFont(size=11)).pack(side=tk.RIGHT)
        ctk.CTkButton(log_tools, text="Copiar Logs", width=85, command=self._copy_logs, font=ctk.CTkFont(size=11)).pack(side=tk.RIGHT, padx=4)

        self.log_box = ctk.CTkTextbox(
            self.tab_logs,
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8,
            fg_color=("#0F172A", "#030712"),
            text_color="#F8FAFC",
            wrap="word"
        )
        self.log_box.grid(row=1, column=0, sticky="nsew")

    def _build_tab_preview(self):
        """
        Vista previa: dibuja la composición elegida con la configuración actual SIN guardar nada.
        Tiene dos vistas: la composición sola, o la misma composición con varias configuraciones
        (distribución, sombra o separación) lado a lado; un clic en un recuadro aplica esa opción.
        """
        t = self.tab_preview
        t.grid_rowconfigure(2, weight=1)
        t.grid_columnconfigure(0, weight=1)

        # Fila 0: qué composición ver
        sel = ctk.CTkFrame(t, fg_color="transparent")
        sel.grid(row=0, column=0, pady=(0, 4), sticky="ew")
        ctk.CTkLabel(sel, text="Composición:", font=ctk.CTkFont(size=12, weight="bold")).pack(side=tk.LEFT, padx=(0, 6))
        ctk.CTkButton(sel, text="◀", width=30, command=lambda: self._step_comp(-1)).pack(side=tk.LEFT)
        self.comp_menu = ctk.CTkOptionMenu(sel, variable=self.comp_var, values=["(sin composiciones)"],
                                           width=250, command=self._on_comp_selected, font=ctk.CTkFont(size=11))
        self.comp_menu.pack(side=tk.LEFT, padx=4)
        ctk.CTkButton(sel, text="▶", width=30, command=lambda: self._step_comp(1)).pack(side=tk.LEFT)
        ctk.CTkButton(sel, text="🔄 Actualizar", width=95, command=self._refresh_preview_now,
                      font=ctk.CTkFont(size=11, weight="bold")).pack(side=tk.LEFT, padx=(10, 0))

        # Fila 1: qué mostrar
        mode = ctk.CTkFrame(t, fg_color="transparent")
        mode.grid(row=1, column=0, pady=(0, 6), sticky="ew")
        self.view_seg = ctk.CTkSegmentedButton(
            mode,
            values=["Composición", "Comparar distribución", "Comparar sombra", "Comparar separación"],
            command=lambda _v: self._request_preview(0),
            font=ctk.CTkFont(size=11)
        )
        self.view_seg.set("Composición")
        self.view_seg.pack(side=tk.LEFT)
        ctk.CTkSwitch(mode, text="Actualizar al cambiar opciones", variable=self.auto_preview_var,
                      font=ctk.CTkFont(size=11)).pack(side=tk.RIGHT)

        # Fila 2: zona de imágenes (con desplazamiento, porque al comparar hay varios recuadros)
        self.prev_area = ctk.CTkScrollableFrame(t, corner_radius=8, fg_color=("#FFFFFF", "#111827"))
        self.prev_area.grid(row=2, column=0, sticky="nsew")
        self.prev_area.grid_columnconfigure(0, weight=1)
        self._show_message("Escribe códigos y elige una composición para ver cómo quedará.")

        # Fila 3: estado y acciones
        foot = ctk.CTkFrame(t, fg_color="transparent")
        foot.grid(row=3, column=0, pady=(6, 0), sticky="ew")
        foot.grid_columnconfigure(0, weight=1)
        self.prev_title = ctk.CTkLabel(foot, text="", font=ctk.CTkFont(size=11), justify="left",
                                       anchor="w", wraplength=430)
        self.prev_title.grid(row=0, column=0, sticky="w")
        self.btn_last = ctk.CTkButton(foot, text="🖼 Último resultado", width=125, command=self._show_last_result,
                                      font=ctk.CTkFont(size=11), state="disabled")
        self.btn_last.grid(row=0, column=1, padx=4)
        self.btn_open_full = ctk.CTkButton(foot, text="🔍 Abrir tamaño completo", width=150,
                                           command=self._open_current_preview,
                                           font=ctk.CTkFont(size=11), state="disabled")
        self.btn_open_full.grid(row=0, column=2)

    # ---------------- INTERACCIÓN Y PRESETS ----------------
    def _on_preset_change(self, choice):
        if choice == "1000 x 1000":
            self.canvas_w_var.set("1000")
            self.canvas_h_var.set("1000")
        elif choice == "1080 x 1080":
            self.canvas_w_var.set("1080")
            self.canvas_h_var.set("1080")
        elif choice == "1200 x 1200":
            self.canvas_w_var.set("1200")
            self.canvas_h_var.set("1200")

    def _toggle_theme(self):
        mode = self.theme_switch.get()
        ctk.set_appearance_mode(mode)

    def _browse_input_dir(self):
        d = filedialog.askdirectory(initialdir=self.input_dir_var.get())
        if d:
            self.input_dir_var.set(d)

    def _browse_output_dir(self):
        d = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if d:
            self.output_dir_var.set(d)

    def _open_dir(self, path_str):
        p = Path(path_str)
        p.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(p))
        else:
            subprocess.run(["xdg-open", str(p)])

    def _open_current_preview(self):
        if self.last_generated_image and os.path.exists(self.last_generated_image):
            if sys.platform == "win32":
                os.startfile(self.last_generated_image)
            else:
                subprocess.run(["xdg-open", self.last_generated_image])

    def _on_codes_change(self, event=None):
        """Actualiza el contador en vivo: una composición por cada línea válida (sin comentarios)."""
        text = self.codes_box.get("1.0", tk.END)
        count = sum(1 for line in text.splitlines() if pipeline.parse_code_line(line))
        self.codes_count_lbl.configure(text=f"🔢 {count} composiciones detectadas")
        self._refresh_compositions()
        self._sync_cursor_comp()                 # la vista previa sigue a la línea del cursor
        self._on_setting_changed()

    def _load_default_codes(self):
        sample = Path("codigos.txt")
        if sample.exists():
            try:
                with open(sample, "r", encoding="utf-8") as f:
                    self.codes_box.insert(tk.END, f.read())
            except Exception:
                pass
        self._on_codes_change()

    def _load_txt_file(self):
        f = filedialog.askopenfilename(filetypes=[("Archivos de texto", "*.txt"), ("Todos los archivos", "*.*")])
        if f:
            try:
                with open(f, "r", encoding="utf-8") as file:
                    self.codes_box.delete("1.0", tk.END)
                    self.codes_box.insert(tk.END, file.read())
                self._on_codes_change()
                self._log_msg(f"Archivo de códigos cargado: {f}")
            except Exception as e:
                messagebox.showerror("Error al leer archivo", str(e))

    def _save_txt_file(self):
        f = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Archivos de texto", "*.txt")])
        if f:
            try:
                with open(f, "w", encoding="utf-8") as file:
                    file.write(self.codes_box.get("1.0", tk.END))
                self._log_msg(f"Archivo guardado: {f}")
            except Exception as e:
                messagebox.showerror("Error al guardar archivo", str(e))

    def _paste_clipboard(self):
        try:
            clip = self.clipboard_get()
            self.codes_box.insert(tk.INSERT, clip)
            self._on_codes_change()
        except Exception:
            pass

    def _clear_codes(self):
        self.codes_box.delete("1.0", tk.END)
        self._on_codes_change()

    def _copy_logs(self):
        self.clipboard_clear()
        self.clipboard_append(self.log_box.get("1.0", tk.END))
        messagebox.showinfo("Copiado", "Los logs han sido copiados al portapapeles.")

    def _clear_logs(self):
        self.log_box.delete("1.0", tk.END)

    def _log_msg(self, msg: str):
        now = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{now}] {msg}\n")
        self.log_box.see(tk.END)

    # ---------------- VISTA PREVIA ----------------
    PREVIEW_TAB = "🖼️ Vista Previa"

    def _gather_settings(self):
        """Configuración actual de la pantalla en el formato que usa previa.py. ValueError si es inválida."""
        try:
            w = int(self.canvas_w_var.get().strip())
            h = int(self.canvas_h_var.get().strip())
        except ValueError:
            raise ValueError("Ancho y alto del lienzo deben ser números enteros.")
        if not (100 <= w <= 6000 and 100 <= h <= 6000):
            raise ValueError("Ancho y alto del lienzo deben estar entre 100 y 6000 px.")
        return {
            "product": self.product_labels.get(self.product_var.get(), pipeline.DEFAULT_PRODUCT),
            "perspective": self.persp_labels.get(self.persp_var.get(), pipeline.DEFAULT_PERSPECTIVE),
            "layout": self.layout_labels.get(self.layout_var.get(), "auto"),
            "fmt": self.format_labels.get(self.format_var.get(), pipeline.DEFAULT_FORMAT),
            "canvas_w": w,
            "canvas_h": h,
            "add_shadow": self.shadow_var.get(),
            "skip_cutout": not self.cutout_var.get(),
            "gap_pct": float(self.gap_var.get()),
        }

    def _refresh_compositions(self):
        """Recalcula la lista de composiciones válidas del editor y actualiza el selector de la vista previa."""
        text = self.codes_box.get("1.0", tk.END)
        self.compositions = []
        for n, line in enumerate(text.splitlines(), 1):
            items = pipeline.parse_code_line(line)
            if items:
                self.compositions.append((n, items, "/".join(it.label() for it in items)))

        values = [f"{i}. {txt}" if len(txt) <= 34 else f"{i}. {txt[:33]}…"
                  for i, (_, _, txt) in enumerate(self.compositions, 1)]
        current = self.comp_var.get()
        if values:
            self.comp_menu.configure(values=values)
            if current not in values:
                self.comp_var.set(values[0])
                self._prev_dirty = True
        else:
            self.comp_menu.configure(values=["(sin composiciones)"])
            self.comp_var.set("(sin composiciones)")

    def _selected_index(self):
        values = list(self.comp_menu.cget("values"))
        cur = self.comp_var.get()
        return values.index(cur) if (self.compositions and cur in values) else None

    def _on_comp_selected(self, _choice=None):
        self._request_preview(0)

    def _step_comp(self, delta):
        idx = self._selected_index()
        if idx is None:
            return
        values = list(self.comp_menu.cget("values"))
        self.comp_var.set(values[(idx + delta) % len(values)])
        self._request_preview(0)

    def _sync_cursor_comp(self, _event=None):
        """La vista previa sigue a la línea donde está el cursor del editor."""
        try:
            line_no = int(self.codes_box.index(tk.INSERT).split(".")[0])
        except Exception:
            return
        for i, (n, _, _) in enumerate(self.compositions):
            if n == line_no:
                values = list(self.comp_menu.cget("values"))
                if self.comp_var.get() != values[i]:
                    self.comp_var.set(values[i])
                    self._on_setting_changed()
                break

    def _preview_visible(self):
        return self.tabview.get() == self.PREVIEW_TAB

    def _on_tab_changed(self):
        if self._preview_visible() and self._prev_dirty:
            self._request_preview(0)

    def _on_setting_changed(self, *_):
        """Una opción cambió: se redibuja sola (con retardo) si la vista previa está abierta."""
        self._prev_dirty = True
        if self._preview_visible() and self.auto_preview_var.get():
            self._request_preview(350)

    def _preview_from_editor(self):
        """Botón 'Previsualizar' del editor: abre la pestaña con la composición de la línea actual."""
        self._sync_cursor_comp()
        self.tabview.set(self.PREVIEW_TAB)
        self._request_preview(0)

    def _refresh_preview_now(self):
        self._request_preview(0)

    def _request_preview(self, delay_ms=0):
        if self._prev_job is not None:
            self.after_cancel(self._prev_job)
        self._prev_job = self.after(delay_ms, self._start_preview_render)

    def _start_preview_render(self):
        self._prev_job = None
        idx = self._selected_index()
        if idx is None:
            self._show_message("No hay composiciones. Escribe al menos una línea de códigos, ej: 30-CRU/65-CAF")
            return
        try:
            settings = self._gather_settings()
        except ValueError as ex:
            self._show_message(str(ex))
            return

        items = self.compositions[idx][1]
        view = self.view_seg.get()
        self._prev_token += 1
        token = self._prev_token
        self._prev_dirty = False
        self.prev_title.configure(text="⏳ Generando vista previa… (la primera vez puede tardar por el recorte con IA)")
        threading.Thread(
            target=self._preview_worker,
            args=(token, items, settings, view, self.input_dir_var.get(), self._single_side()),
            daemon=True
        ).start()

    def _single_side(self):
        """Lado de la vista previa: lo más grande que quepa en la zona visible (sin necesidad de desplazar)."""
        try:
            return max(260, min(480, self.tabview.winfo_height() - 215))   # alto de la pestaña menos controles
        except Exception:
            return 400

    def _preview_worker(self, token, items, settings, view, in_dir, single_side=430):
        """Hilo secundario: dibuja la vista previa y devuelve el resultado a la ventana con after()."""
        kinds = {"Comparar distribución": "layout", "Comparar sombra": "shadow", "Comparar separación": "gap"}
        if view in kinds:
            res = previa.render_variants(items, in_dir, kinds[view], settings, max_side=240)
        else:
            res = previa.render_preview(items, in_dir, settings, max_side=single_side)
        self.after(0, self._preview_done, token, view, settings, res)

    def _preview_done(self, token, view, settings, res):
        if token != self._prev_token:
            return                                   # llegó una respuesta vieja: ya hay una solicitud más nueva
        if not res["ok"]:
            self._show_message("⚠️ " + res["error"], error=True)
            self.prev_title.configure(text="No se pudo generar la vista previa.")
            return

        warn = ("  |  ⚠️ " + " · ".join(res["warnings"])) if res.get("warnings") else ""
        if view == "Composición":
            w, h = res["final_size"]
            self._show_single(res["image"])
            self.prev_title.configure(text=f"Vista previa — se guardará a {w}x{h} px, JPG.{warn}")
        else:
            self._show_variants(res["variants"])
            self.prev_title.configure(text=f"Haz clic en un recuadro para aplicar esa opción.{warn}")

    # --- dibujo de la zona de imágenes ---
    def _clear_area(self):
        for child in self.prev_area.winfo_children():
            child.destroy()
        self._prev_images = []

    def _tk_image(self, pil_img):
        img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
        self._prev_images.append(img)
        return img

    def _show_message(self, text, error=False):
        self._clear_area()
        ctk.CTkLabel(self.prev_area, text=text, wraplength=420, justify="center",
                     text_color=("#B91C1C", "#FCA5A5") if error else ("gray40", "gray65"),
                     font=ctk.CTkFont(size=12)).grid(row=0, column=0, pady=40, padx=10)

    def _show_single(self, pil_img):
        self._clear_area()
        frame = ctk.CTkFrame(self.prev_area, fg_color="#FFFFFF", border_width=1, border_color="#CBD5E1", corner_radius=0)
        frame.grid(row=0, column=0, pady=6)
        ctk.CTkLabel(frame, text="", image=self._tk_image(pil_img)).pack()

    def _show_variants(self, variants, cols=2):
        self._clear_area()
        for c in range(cols):
            self.prev_area.grid_columnconfigure(c, weight=1)
        for i, v in enumerate(variants):
            current = v["current"]
            tile = ctk.CTkFrame(self.prev_area, corner_radius=8, border_width=3 if current else 1,
                                border_color="#2563EB" if current else "#CBD5E1", fg_color=("#F8FAFC", "#1F2937"))
            tile.grid(row=i // cols, column=i % cols, padx=6, pady=6)
            img_lbl = ctk.CTkLabel(tile, text="", image=self._tk_image(v["image"]), cursor="hand2")
            img_lbl.pack(padx=6, pady=(6, 2))
            cap = ctk.CTkLabel(tile, text=("✔ " if current else "") + v["label"] + ("  (actual)" if current else ""),
                               font=ctk.CTkFont(size=11, weight="bold"))
            cap.pack(pady=(0, 6))
            for widget in (tile, img_lbl, cap):
                widget.bind("<Button-1>", lambda _e, ch=v["changes"]: self._apply_changes(ch))

    def _apply_changes(self, changes):
        """Aplica a la configuración de la pantalla la variante elegida en la comparación."""
        if "layout" in changes:
            self.layout_var.set(pipeline.LAYOUTS[changes["layout"]])
        if "add_shadow" in changes:
            self.shadow_var.set(changes["add_shadow"])
        if "gap_pct" in changes:
            self.gap_var.set(changes["gap_pct"])
        self._request_preview(0)                       # redibuja para marcar la opción actual

    def _show_last_result(self):
        """Muestra el último archivo generado por el proceso (no la previa)."""
        path = self.last_generated_image
        if not (path and os.path.exists(path)):
            return
        try:
            im = Image.open(path)
            side = self._single_side()
            im.thumbnail((side, side), Image.LANCZOS)
            self._show_single(im.copy())
            self.prev_title.configure(text=f"Último resultado guardado: {Path(path).name}")
        except Exception as ex:
            self._show_message(f"No se pudo abrir el resultado: {ex}", error=True)

    # ---------------- PROCESAMIENTO Y TRABAJADOR ----------------
    def _start_processing(self):
        """
        Botón "INICIAR PROCESAMIENTO": valida los datos de la pantalla y lanza el lote.
        Lee las líneas de códigos, el tipo/perspectiva/distribución elegidos, el tamaño del
        lienzo y las carpetas; luego procesa en un hilo aparte para no congelar la ventana.
        """
        if self.is_processing:
            return

        text = self.codes_box.get("1.0", tk.END)
        compositions = []
        for line in text.splitlines():
            items = pipeline.parse_code_line(line)
            if items:
                compositions.append(items)

        if not compositions:
            messagebox.showwarning("Atención", "No hay códigos válidos para procesar.\nEscribe una composición por línea, ej: '30-CRU/65-CAF' o 'BOL-01:frontal'.")
            return

        settings = {
            "product": self.product_labels.get(self.product_var.get(), pipeline.DEFAULT_PRODUCT),
            "perspective": self.persp_labels.get(self.persp_var.get(), pipeline.DEFAULT_PERSPECTIVE),
            "layout": self.layout_labels.get(self.layout_var.get(), "auto"),
            "fmt": self.format_labels.get(self.format_var.get(), pipeline.DEFAULT_FORMAT),
            "gap_pct": float(self.gap_var.get()),
            "overwrite": self.overwrite_var.get(),
        }

        in_dir = self.input_dir_var.get()
        out_dir = self.output_dir_var.get()

        if not Path(in_dir).exists():
            messagebox.showerror("Error", f"La carpeta de imágenes no existe:\n{in_dir}")
            return

        # Dimensiones del lienzo
        try:
            canvas_w = int(self.canvas_w_var.get().strip())
            canvas_h = int(self.canvas_h_var.get().strip())
            quality = int(self.quality_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Las dimensiones y calidad deben ser números enteros válidos.")
            return

        # Limpiar registros previos
        self.records.clear()
        self._refresh_tree()
        self.lbl_acc_val.configure(text="0")
        self.lbl_err_val.configure(text="0")
        self.lbl_tot_val.configure(text=str(len(compositions)))

        self.is_processing = True
        self.btn_run.configure(state="disabled", fg_color="gray40")
        self.prog_bar.set(0)

        self._log_msg("=" * 60)
        self._log_msg(f"🚀 INICIANDO LOTE: {len(compositions)} composiciones | Lienzo: {canvas_w}x{canvas_h} px | Calidad: {quality}%")
        self._log_msg(f"Formato: {self.format_var.get()} | Producto: {self.product_var.get()} | Perspectiva: {self.persp_var.get()} | Distribución: {self.layout_var.get()} | Separación: {self.gap_var.get():.0f} %")
        self._log_msg(f"Origen: {in_dir}")
        self._log_msg(f"Destino: {out_dir}")
        self._log_msg("=" * 60)

        # Cambiar a pestaña de registro para ver avance
        self.tabview.set("📊 Registro de Aciertos y Errores")

        thread = threading.Thread(
            target=self._run_batch_worker,
            args=(compositions, settings, in_dir, out_dir, not self.cutout_var.get(), self.shadow_var.get(), canvas_w, canvas_h, quality),
            daemon=True
        )
        thread.start()

    def _run_batch_worker(self, compositions, settings, in_dir, out_dir, skip_cutout, add_shadow, canvas_w, canvas_h, quality):
        """
        Se ejecuta en un hilo secundario. Procesa cada composición con pipeline.process_items()
        y guarda un registro por línea (self.records). Tkinter no es seguro entre hilos, por eso
        toda actualización de la pantalla se encola con self.after(0, ...) en vez de hacerse directo.
        """
        success_count = 0
        error_count = 0
        total = len(compositions)

        for i, items in enumerate(compositions, 1):
            pair_str = "/".join(it.label() for it in items)
            time_str = datetime.now().strftime("%H:%M:%S")

            self.after(0, self._update_progress, f"Procesando [{i}/{total}]: {pair_str} ({canvas_w}x{canvas_h})...", (i - 1) / total)
            self.after(0, self._log_msg, f"[{i}/{total}] Buscando {', '.join(repr(it.code) for it in items)}...")

            res = pipeline.process_items(
                items,
                img_dir=in_dir,
                out_dir=out_dir,
                skip_cutout=skip_cutout,
                add_shadow=add_shadow,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                quality=quality,
                **settings
            )

            record = {
                "id": i,
                "pair": pair_str,
                "codes": res.get("codes", [it.code for it in items]),
                "products": res.get("products", []),
                "perspectives": res.get("perspectives", []),
                "ok": res["ok"],
                "files": [f for f in res.get("files", []) if f],
                "out_path": res.get("out_path"),
                "error": res.get("error", ""),
                "warnings": res.get("warnings", []),
                "time": time_str
            }
            self.records.append(record)

            for w in record["warnings"]:
                self.after(0, self._log_msg, f"  ⚠️ {w}")

            if res["ok"]:
                success_count += 1
                out_name = Path(res["out_path"]).name
                self.after(0, self._add_record_to_tree, record)
                persp_txt = ", ".join(record["perspectives"])
                self.after(0, self._log_msg, f"  ✅ ÉXITO: Generado '{out_name}' ({canvas_w}x{canvas_h}) | perspectivas: {persp_txt}")
                self.after(0, self._remember_result, res["out_path"])
            else:
                error_count += 1
                self.after(0, self._add_record_to_tree, record)
                self.after(0, self._log_msg, f"  ❌ ERROR: {res['error']}")

            self.after(0, self._update_metrics, success_count, error_count, total)

        self.after(0, self._finish_batch, success_count, error_count, total, out_dir)

    def _update_progress(self, msg, fraction):
        self.status_lbl.configure(text=msg)
        self.prog_bar.set(fraction)

    def _update_metrics(self, success, errors, total):
        self.lbl_acc_val.configure(text=str(success))
        self.lbl_err_val.configure(text=str(errors))
        self.lbl_tot_val.configure(text=str(total))
        self._update_filter_labels()

    def _add_record_to_tree(self, rec):
        status_text = "✅ ÉXITO" if rec["ok"] else "❌ ERROR"
        detail_text = Path(rec["out_path"]).name if rec["ok"] else rec["error"]
        tag = "ok_tag" if rec["ok"] else "error_tag"

        if self.current_filter == "ALL" or (self.current_filter == "SUCCESS" and rec["ok"]) or (self.current_filter == "ERROR" and not rec["ok"]):
            self.tree.insert("", tk.END, values=(rec["id"], rec["pair"], status_text, detail_text, rec["time"]), tags=(tag,))

    def _update_filter_labels(self):
        total = len(self.records)
        success = sum(1 for r in self.records if r["ok"])
        errors = total - success
        vals = [f"Todos ({total})", f"✅ Aciertos ({success})", f"❌ Errores ({errors})"]
        self.seg_filter.configure(values=vals)

    def _on_filter_changed(self, choice):
        if "Aciertos" in choice:
            self.current_filter = "SUCCESS"
        elif "Errores" in choice:
            self.current_filter = "ERROR"
        else:
            self.current_filter = "ALL"
        self._refresh_tree()

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for rec in self.records:
            if self.current_filter == "ALL" or (self.current_filter == "SUCCESS" and rec["ok"]) or (self.current_filter == "ERROR" and not rec["ok"]):
                status_text = "✅ ÉXITO" if rec["ok"] else "❌ ERROR"
                detail_text = Path(rec["out_path"]).name if rec["ok"] else rec["error"]
                tag = "ok_tag" if rec["ok"] else "error_tag"
                self.tree.insert("", tk.END, values=(rec["id"], rec["pair"], status_text, detail_text, rec["time"]), tags=(tag,))

    def _on_tree_double_click(self, event):
        item_id = self.tree.focus()
        if not item_id:
            return
        vals = self.tree.item(item_id, "values")
        if not vals:
            return
        idx = int(vals[0]) - 1
        if 0 <= idx < len(self.records):
            rec = self.records[idx]
            if rec["ok"] and rec["out_path"] and os.path.exists(rec["out_path"]):
                if sys.platform == "win32":
                    os.startfile(rec["out_path"])
                else:
                    subprocess.run(["xdg-open", rec["out_path"]])
            else:
                msg = f"Composición: {rec['pair']}\n\nDetalle del error:\n{rec['error']}"
                for n, f in enumerate(rec.get("files", []), 1):
                    msg += f"\nImagen encontrada para el producto {n}: {f}"
                messagebox.showwarning("Detalle del Error", msg)

    def _remember_result(self, path: str):
        """Guarda la ruta del último archivo generado y habilita sus botones en la vista previa."""
        self.last_generated_image = path
        self.btn_last.configure(state="normal")
        self.btn_open_full.configure(state="normal")

    def _finish_batch(self, success, errors, total, out_dir):
        self.is_processing = False
        self.btn_run.configure(state="normal", fg_color="#2563EB")
        self.prog_bar.set(1.0)

        summary_msg = f"Finalizado: {success} aciertos, {errors} errores (Total: {total})"
        self.status_lbl.configure(text=summary_msg)
        self._log_msg("=" * 60)
        self._log_msg(f"🎉 {summary_msg}")
        self._log_msg("=" * 60)

        self._auto_save_csv(out_dir)

        if success > 0:
            if messagebox.askyesno("Proceso finalizado", f"{summary_msg}\n\n¿Deseas abrir la carpeta de resultados ahora?"):
                self._open_dir(out_dir)

    def _write_csv(self, csv_path):
        """Escribe el registro de la sesión en CSV (UTF-8 con BOM para que Excel respete las tildes)."""
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["#", "Composicion", "Codigos", "Tipos", "Perspectivas", "Estado",
                             "Archivo_Generado", "Avisos", "Error", "Hora"])
            for r in self.records:
                writer.writerow([
                    r["id"],
                    r["pair"],
                    " | ".join(r.get("codes", [])),
                    " | ".join(r.get("products", [])),
                    " | ".join(r.get("perspectives", [])),
                    "ÉXITO" if r["ok"] else "ERROR",
                    r.get("out_path", "") or "",
                    " | ".join(r.get("warnings", [])),
                    r.get("error", "") or "",
                    r["time"]
                ])

    def _auto_save_csv(self, out_dir: str):
        try:
            csv_path = Path(out_dir) / "registro_aciertos_errores.csv"
            self._write_csv(csv_path)
            self._log_msg(f"Reporte CSV guardado automáticamente en: {csv_path.name}")
        except Exception as e:
            self._log_msg(f"No se pudo guardar CSV: {e}")

    def _export_csv(self):
        if not self.records:
            messagebox.showinfo("Exportar", "Aún no hay registros de procesamiento para exportar.")
            return

        f = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Archivos CSV", "*.csv")],
            initialfile=f"registro_imagenes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        if f:
            try:
                self._write_csv(f)
                messagebox.showinfo("Exportación Exitosa", f"Registro exportado a:\n{f}")
            except Exception as e:
                messagebox.showerror("Error al exportar", str(e))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
