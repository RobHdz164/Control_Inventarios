import csv
import sqlite3
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "inventario_immex.db"


class InventoryApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TEXCO | Control de inventarios IMMEX - Anexo 24")
        self.geometry("1220x760")
        self.minsize(1050, 650)
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()
        self._seed_data()
        self._build_style()
        self._build_ui()
        self.refresh_all()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _create_schema(self):
        self.conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS company (
                id INTEGER PRIMARY KEY CHECK (id = 1), legal_name TEXT NOT NULL,
                trade_name TEXT NOT NULL, rfc TEXT NOT NULL, immex_number TEXT,
                tax_address TEXT, plant_address TEXT, academic INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL, unit TEXT NOT NULL, tariff_fraction TEXT,
                supplier TEXT, active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
                movement_date TEXT NOT NULL, document TEXT NOT NULL, customs TEXT,
                pedimento_key TEXT, patent TEXT, material_id INTEGER NOT NULL,
                quantity REAL NOT NULL CHECK (quantity > 0), unit_value REAL NOT NULL DEFAULT 0,
                notes TEXT, FOREIGN KEY(material_id) REFERENCES materials(id)
            );
            CREATE TABLE IF NOT EXISTS allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, movement_id INTEGER NOT NULL,
                entry_id INTEGER NOT NULL, quantity REAL NOT NULL CHECK(quantity > 0),
                FOREIGN KEY(movement_id) REFERENCES movements(id),
                FOREIGN KEY(entry_id) REFERENCES movements(id)
            );
            """
        )
        self.conn.commit()

    def _seed_data(self):
        if self.conn.execute("SELECT COUNT(*) FROM company").fetchone()[0] == 0:
            self.conn.execute(
                "INSERT INTO company VALUES (1, ?, ?, ?, ?, ?, ?, 1)",
                ("Textiles y Confecciones del Centro, S.A. de C.V.", "TEXCO",
                 "TCC261001AB1", "POR AUTORIZAR - PRÁCTICA", "Puebla, Puebla, México",
                 "Planta y almacén académico: Puebla, Puebla, México"),
            )
        if self.conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 0:
            materials = [
                ("TELA-001", "Tela de algodón para playera", "Metro", "5208.52.01", "Proveedor textil extranjero"),
                ("HILO-001", "Hilo de poliéster", "Kilogramo", "5401.10.01", "Proveedor de insumos extranjero"),
                ("BOT-001", "Botón plástico", "Pieza", "9606.29.99", "Proveedor de accesorios extranjero"),
                ("CIE-001", "Cierre nylon", "Pieza", "9607.19.99", "Proveedor de accesorios extranjero"),
            ]
            self.conn.executemany(
                "INSERT INTO materials (sku, description, unit, tariff_fraction, supplier) VALUES (?, ?, ?, ?, ?)",
                materials,
            )
        self.conn.commit()

    def _build_style(self):
        style = ttk.Style(self)
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#12304a")
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground="#176b87")
        style.configure("Metric.TLabel", font=("Segoe UI", 22, "bold"), foreground="#12304a")
        style.configure("Treeview", rowheight=28)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.configure("Accent.TButton", foreground="#ffffff", background="#176b87")

    def _build_ui(self):
        header = ttk.Frame(self, padding=(22, 16, 22, 6))
        header.pack(fill="x")
        ttk.Label(header, text="TEXCO", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Control de inventarios IMMEX | Anexo 24 | EJERCICIO ACADÉMICO",
                  foreground="#7c4d12").pack(side="left", padx=18, pady=7)
        ttk.Button(header, text="Guía de uso", command=self.open_help).pack(side="right", padx=5)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=(4, 18))
        self.dashboard_tab = ttk.Frame(self.notebook, padding=16)
        self.company_tab = ttk.Frame(self.notebook, padding=16)
        self.material_tab = ttk.Frame(self.notebook, padding=16)
        self.entry_tab = ttk.Frame(self.notebook, padding=16)
        self.output_tab = ttk.Frame(self.notebook, padding=16)
        self.report_tab = ttk.Frame(self.notebook, padding=16)
        for tab, title in ((self.dashboard_tab, "Resumen"), (self.company_tab, "Empresa"),
                           (self.material_tab, "Materiales"), (self.entry_tab, "Entradas"),
                           (self.output_tab, "Consumos y salidas"), (self.report_tab, "Reportes")):
            self.notebook.add(tab, text=title)
        self._build_dashboard()
        self._build_company()
        self._build_materials()
        self._build_entries()
        self._build_outputs()
        self._build_reports()

    def _label_entry(self, parent, row, label, variable, column=0, width=28):
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=5, pady=4)
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row, column=column + 1, sticky="ew", padx=5, pady=4)
        return entry

    def _build_dashboard(self):
        ttk.Label(self.dashboard_tab, text="Estado del inventario", style="Title.TLabel").pack(anchor="w")
        self.metric_frame = ttk.Frame(self.dashboard_tab)
        self.metric_frame.pack(fill="x", pady=18)
        self.metrics = {}
        for key, title in (("materials", "Materiales"), ("entries", "Entradas"),
                           ("available", "Existencia disponible"), ("pending", "Pendiente de descargo")):
            box = ttk.LabelFrame(self.metric_frame, text=title, padding=14)
            box.pack(side="left", fill="both", expand=True, padx=5)
            value = ttk.Label(box, text="0", style="Metric.TLabel")
            value.pack(anchor="w")
            self.metrics[key] = value
        ttk.Label(self.dashboard_tab, text="Trazabilidad reciente", style="Section.TLabel").pack(anchor="w", pady=(10, 5))
        self.dashboard_tree = self._tree(self.dashboard_tab, ("fecha", "tipo", "documento", "sku", "cantidad"),
                                         ("Fecha", "Movimiento", "Documento", "SKU", "Cantidad"))
        self.dashboard_tree.pack(fill="both", expand=True)

    def _build_company(self):
        ttk.Label(self.company_tab, text="Datos generales del contribuyente", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.company_tab, text="Los datos del expediente se cargaron como información ficticia para fines académicos.",
                  foreground="#7c4d12").pack(anchor="w", pady=(2, 16))
        form = ttk.Frame(self.company_tab)
        form.pack(fill="x")
        self.company_vars = {key: tk.StringVar() for key in
                             ("legal_name", "trade_name", "rfc", "immex_number", "tax_address", "plant_address")}
        labels = (("legal_name", "Razón social"), ("trade_name", "Nombre comercial"),
                  ("rfc", "RFC"), ("immex_number", "Programa IMMEX"),
                  ("tax_address", "Domicilio fiscal"), ("plant_address", "Planta / almacén"))
        for index, (key, label) in enumerate(labels):
            self._label_entry(form, index, label, self.company_vars[key], width=62)
        ttk.Button(form, text="Guardar datos de empresa", command=self.save_company).grid(row=6, column=1, sticky="w", padx=5, pady=15)

    def _build_materials(self):
        ttk.Label(self.material_tab, text="Catálogo de materiales", style="Title.TLabel").pack(anchor="w")
        form = ttk.LabelFrame(self.material_tab, text="Alta de material", padding=10)
        form.pack(fill="x", pady=(14, 10))
        self.material_vars = {key: tk.StringVar() for key in ("sku", "description", "unit", "tariff_fraction", "supplier")}
        for col, (key, label) in enumerate((("sku", "Número de parte / SKU"), ("description", "Descripción"),
                                             ("unit", "Unidad"), ("tariff_fraction", "Fracción arancelaria"), ("supplier", "Proveedor extranjero"))):
            self._label_entry(form, 0, label, self.material_vars[key], col * 2, 24 if col != 1 else 30)
        ttk.Button(form, text="Registrar material", command=self.add_material).grid(row=1, column=1, padx=5, pady=7, sticky="w")
        self.material_tree = self._tree(self.material_tab, ("id", "sku", "description", "unit", "tariff", "supplier"),
                                        ("ID", "SKU", "Descripción", "Unidad", "Fracción", "Proveedor"))
        self.material_tree.pack(fill="both", expand=True)

    def _build_entries(self):
        ttk.Label(self.entry_tab, text="Información aduanera de entradas", style="Title.TLabel").pack(anchor="w")
        form = ttk.LabelFrame(self.entry_tab, text="Importación temporal", padding=10)
        form.pack(fill="x", pady=(14, 10))
        self.entry_vars = {key: tk.StringVar(value=date.today().isoformat()) if key == "date" else tk.StringVar()
                           for key in ("date", "document", "customs", "key", "patent", "quantity", "value", "notes")}
        self.entry_material = ttk.Combobox(form, state="readonly", width=30)
        fields = (("date", "Fecha de pago"), ("document", "Número de pedimento"), ("customs", "Aduana"),
                  ("key", "Clave de pedimento"), ("patent", "Patente / autorización"),
                  ("quantity", "Cantidad"), ("value", "Valor unitario"), ("notes", "Observaciones"))
        for col, (key, label) in enumerate(fields):
            self._label_entry(form, 0 if col < 4 else 1, label, self.entry_vars[key], (col % 4) * 2, 19)
        ttk.Label(form, text="Material").grid(row=1, column=8, sticky="w", padx=5, pady=4)
        self.entry_material.grid(row=1, column=9, sticky="w", padx=5, pady=4)
        ttk.Button(form, text="Registrar entrada temporal", command=self.add_entry).grid(row=2, column=1, sticky="w", padx=5, pady=8)
        self.entry_tree = self._tree(self.entry_tab, ("date", "document", "customs", "key", "sku", "quantity", "value"),
                                     ("Fecha", "Pedimento", "Aduana", "Clave", "SKU", "Cantidad", "Valor unit."))
        self.entry_tree.pack(fill="both", expand=True)

    def _build_outputs(self):
        ttk.Label(self.output_tab, text="Consumos, retornos y descargos", style="Title.TLabel").pack(anchor="w")
        form = ttk.LabelFrame(self.output_tab, text="Movimiento de salida", padding=10)
        form.pack(fill="x", pady=(14, 10))
        self.output_vars = {key: tk.StringVar(value=date.today().isoformat()) if key == "date" else tk.StringVar()
                            for key in ("date", "document", "quantity", "notes")}
        self.output_kind = ttk.Combobox(form, state="readonly", values=("Consumo en producción", "Retorno al extranjero",
                                                                          "Transferencia virtual", "Cambio de régimen",
                                                                          "Destrucción / donación"), width=24)
        self.output_kind.current(0)
        self.output_material = ttk.Combobox(form, state="readonly", width=30)
        for col, (key, label) in enumerate((("date", "Fecha"), ("document", "Documento de salida"), ("quantity", "Cantidad"), ("notes", "Observaciones"))):
            self._label_entry(form, 0, label, self.output_vars[key], col * 2, 22)
        ttk.Label(form, text="Tipo").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        self.output_kind.grid(row=1, column=1, sticky="w", padx=5, pady=4)
        ttk.Label(form, text="Material").grid(row=1, column=2, sticky="w", padx=5, pady=4)
        self.output_material.grid(row=1, column=3, sticky="w", padx=5, pady=4)
        ttk.Button(form, text="Registrar y ejecutar descargo", command=self.add_output).grid(row=1, column=5, padx=5, pady=8, sticky="w")
        tables = ttk.Frame(self.output_tab)
        tables.pack(fill="both", expand=True)
        consumption_box = ttk.LabelFrame(tables, text="Materiales utilizados en producción", padding=6)
        consumption_box.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.consumption_tree = self._tree(consumption_box, ("date", "document", "sku", "quantity", "allocation"),
                           ("Fecha", "Documento", "SKU", "Cantidad", "Entradas afectadas"))
        self.consumption_tree.pack(fill="both", expand=True)
        output_box = ttk.LabelFrame(tables, text="Salidas aduaneras", padding=6)
        output_box.pack(side="left", fill="both", expand=True, padx=(5, 0))
        self.output_tree = self._tree(output_box, ("date", "kind", "document", "sku", "quantity", "allocation"),
                          ("Fecha", "Tipo", "Documento", "SKU", "Cantidad", "Entradas afectadas"))
        self.output_tree.pack(fill="both", expand=True)

    def _build_reports(self):
        ttk.Label(self.report_tab, text="Reportes del Anexo 24", style="Title.TLabel").pack(anchor="w")
        ttk.Label(self.report_tab, text="Cada reporte puede exportarse a CSV para revisión académica o conciliación.", foreground="#555").pack(anchor="w", pady=(2, 15))
        for title, report in (("Entradas temporales", "entries"), ("Salidas y descargos", "outputs"), ("Saldos por material", "balances"), ("Materiales utilizados", "consumptions")):
            ttk.Button(self.report_tab, text=f"Exportar {title.lower()}", command=lambda r=report, t=title: self.export_report(r, t)).pack(anchor="w", pady=6)

    def open_help(self):
        help_window = tk.Toplevel(self)
        help_window.title("Guía de uso | TEXCO")
        help_window.geometry("900x680")
        help_window.minsize(720, 520)
        help_window.transient(self)

        container = ttk.Frame(help_window, padding=18)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="Guía de utilización", style="Title.TLabel").pack(anchor="w")
        ttk.Label(container, text="Control de inventarios IMMEX | Ejercicio académico", foreground="#7c4d12").pack(anchor="w", pady=(2, 14))

        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)
        steps_tab = ttk.Frame(notebook, padding=14)
        fields_tab = ttk.Frame(notebook, padding=14)
        notebook.add(steps_tab, text="Cómo utilizar la aplicación")
        notebook.add(fields_tab, text="Significado de los campos")

        steps = (
            "1. Empresa: revisa los datos de TEXCO y guarda cualquier modificación.",
            "2. Materiales: registra cada insumo con su SKU, descripción, unidad, fracción y proveedor.",
            "3. Entradas: captura la importación temporal respaldada por su pedimento y selecciona el material.",
            "4. Consumos y salidas: selecciona el movimiento, material, documento y cantidad; después ejecuta el descargo.",
            "5. Resumen: verifica las entradas, movimientos recientes y el saldo disponible.",
            "6. Reportes: exporta entradas, salidas, saldos o consumos a archivos CSV.",
        )
        for step in steps:
            ttk.Label(steps_tab, text=step, wraplength=780, justify="left").pack(anchor="w", pady=8)
        ttk.Label(steps_tab, text="Importante: esta aplicación es una simulación académica. Verifica siempre los datos del pedimento y la operación aduanera antes de utilizarlos en un caso real.", wraplength=780, justify="left", foreground="#7c4d12").pack(anchor="w", pady=(18, 8))

        fields = (
            ("Razón social", "Nombre legal completo de la empresa."),
            ("RFC", "Registro Federal de Contribuyentes de la empresa."),
            ("Programa IMMEX", "Número o estatus del programa IMMEX; en esta práctica aparece como pendiente de autorización."),
            ("SKU / número de parte", "Identificador único del material dentro del inventario."),
            ("Descripción", "Nombre detallado de la mercancía o insumo."),
            ("Unidad", "Unidad en la que se controla la cantidad: pieza, metro, kilogramo, etc."),
            ("Fracción arancelaria", "Clasificación arancelaria declarada para la mercancía."),
            ("Proveedor extranjero", "Proveedor que envía la mercancía desde el extranjero."),
            ("Fecha de pago", "Fecha en que se pagó el pedimento de importación temporal."),
            ("Número de pedimento", "Identificador del pedimento que respalda la entrada temporal."),
            ("Aduana", "Aduana de despacho de la operación."),
            ("Clave de pedimento", "Clave aduanera correspondiente al régimen y tipo de operación."),
            ("Patente / autorización", "Patente del agente aduanal o autorización aplicable."),
            ("Valor unitario", "Valor de una unidad de mercancía para la operación registrada."),
            ("Documento de salida", "Folio del documento que respalda el consumo, retorno, transferencia o cambio de régimen."),
            ("Cantidad", "Número de unidades que entran, se consumen o salen del inventario."),
            ("Tipo de movimiento", "Define si se trata de consumo en producción, retorno, transferencia, cambio de régimen o destrucción/donación."),
            ("Entradas afectadas", "Identifica las entradas temporales de las que se descuenta la cantidad mediante el método FIFO."),
        )
        field_text = tk.Text(fields_tab, wrap="word", height=20, font=("Segoe UI", 10), relief="flat", padx=8, pady=8)
        field_scroll = ttk.Scrollbar(fields_tab, orient="vertical", command=field_text.yview)
        field_text.configure(yscrollcommand=field_scroll.set)
        field_text.pack(side="left", fill="both", expand=True)
        field_scroll.pack(side="right", fill="y")
        for name, meaning in fields:
            field_text.insert("end", f"{name}\n", "field")
            field_text.insert("end", f"{meaning}\n\n")
        field_text.tag_configure("field", font=("Segoe UI", 10, "bold"), foreground="#176b87")
        field_text.configure(state="disabled")

    def _tree(self, parent, columns, headings):
        tree = ttk.Treeview(parent, columns=columns, show="headings")
        for column, heading in zip(columns, headings):
            tree.heading(column, text=heading)
            tree.column(column, width=max(100, min(230, len(heading) * 13)), anchor="w")
        scroll = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        return tree

    def save_company(self):
        self.conn.execute("UPDATE company SET legal_name=?, trade_name=?, rfc=?, immex_number=?, tax_address=?, plant_address=? WHERE id=1",
                          tuple(self.company_vars[key].get().strip() for key in ("legal_name", "trade_name", "rfc", "immex_number", "tax_address", "plant_address")))
        self.conn.commit()
        messagebox.showinfo("Guardado", "Los datos generales fueron actualizados.")

    def add_material(self):
        values = tuple(self.material_vars[key].get().strip() for key in ("sku", "description", "unit", "tariff_fraction", "supplier"))
        if not values[0] or not values[1] or not values[2]:
            return messagebox.showwarning("Datos incompletos", "SKU, descripción y unidad son obligatorios.")
        try:
            self.conn.execute("INSERT INTO materials (sku, description, unit, tariff_fraction, supplier) VALUES (?, ?, ?, ?, ?)", values)
            self.conn.commit()
        except sqlite3.IntegrityError:
            return messagebox.showerror("SKU duplicado", "Ya existe un material con ese número de parte.")
        for variable in self.material_vars.values(): variable.set("")
        self.refresh_all()

    def _selected_material(self, combo):
        value = combo.get()
        return self.conn.execute("SELECT id FROM materials WHERE sku=?", (value.split(" | ")[0],)).fetchone()

    def add_entry(self):
        material = self._selected_material(self.entry_material)
        try:
            quantity, value = float(self.entry_vars["quantity"].get()), float(self.entry_vars["value"].get() or 0)
        except ValueError:
            return messagebox.showwarning("Cantidad inválida", "Cantidad y valor deben ser números.")
        required = (self.entry_vars["date"].get(), self.entry_vars["document"].get().strip(), self.entry_vars["customs"].get().strip(), self.entry_vars["key"].get().strip(), material)
        if not all(required) or quantity <= 0:
            return messagebox.showwarning("Datos incompletos", "Captura fecha, pedimento, aduana, clave, material y cantidad positiva.")
        self.conn.execute("INSERT INTO movements (kind, movement_date, document, customs, pedimento_key, patent, material_id, quantity, unit_value, notes) VALUES ('Entrada temporal', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (self.entry_vars["date"].get(), self.entry_vars["document"].get().strip(), self.entry_vars["customs"].get().strip(), self.entry_vars["key"].get().strip(), self.entry_vars["patent"].get().strip(), material["id"], quantity, value, self.entry_vars["notes"].get().strip()))
        self.conn.commit()
        self.refresh_all()

    def add_output(self):
        material = self._selected_material(self.output_material)
        try: quantity = float(self.output_vars["quantity"].get())
        except ValueError: return messagebox.showwarning("Cantidad inválida", "La cantidad debe ser un número.")
        if not material or not self.output_vars["document"].get().strip() or quantity <= 0:
            return messagebox.showwarning("Datos incompletos", "Captura material, documento y una cantidad positiva.")
        available = self._available(material["id"])
        if quantity > available + 1e-9:
            return messagebox.showerror("Saldo insuficiente", f"El material solo tiene {available:g} unidades disponibles.")
        cursor = self.conn.execute("INSERT INTO movements (kind, movement_date, document, material_id, quantity, notes) VALUES (?, ?, ?, ?, ?, ?)",
                                   (self.output_kind.get(), self.output_vars["date"].get(), self.output_vars["document"].get().strip(), material["id"], quantity, self.output_vars["notes"].get().strip()))
        movement_id = cursor.lastrowid
        remaining = quantity
        entries = self.conn.execute("SELECT m.id, m.quantity - COALESCE((SELECT SUM(a.quantity) FROM allocations a WHERE a.entry_id=m.id), 0) AS available FROM movements m WHERE m.kind='Entrada temporal' AND m.material_id=? AND (m.quantity - COALESCE((SELECT SUM(a.quantity) FROM allocations a WHERE a.entry_id=m.id), 0)) > 0 ORDER BY m.movement_date, m.id", (material["id"],)).fetchall()
        for entry in entries:
            applied = min(remaining, entry["available"])
            if applied > 0:
                self.conn.execute("INSERT INTO allocations (movement_id, entry_id, quantity) VALUES (?, ?, ?)", (movement_id, entry["id"], applied))
                remaining -= applied
            if remaining <= 1e-9: break
        self.conn.commit()
        self.refresh_all()

    def _available(self, material_id):
        row = self.conn.execute("SELECT COALESCE(SUM(m.quantity - COALESCE((SELECT SUM(a.quantity) FROM allocations a WHERE a.entry_id=m.id), 0)), 0) AS balance FROM movements m WHERE m.kind='Entrada temporal' AND m.material_id=?", (material_id,)).fetchone()
        return row["balance"] or 0

    def refresh_all(self):
        company = self.conn.execute("SELECT * FROM company WHERE id=1").fetchone()
        if hasattr(self, "company_vars"):
            for key in self.company_vars: self.company_vars[key].set(company[key] or "")
        materials = self.conn.execute("SELECT * FROM materials WHERE active=1 ORDER BY sku").fetchall()
        choices = [f"{row['sku']} | {row['description']}" for row in materials]
        for combo in (getattr(self, "entry_material", None), getattr(self, "output_material", None)):
            if combo is not None:
                combo["values"] = choices
                if choices and not combo.get(): combo.current(0)
        if hasattr(self, "material_tree"):
            self._clear(self.material_tree)
            for row in materials: self.material_tree.insert("", "end", values=(row["id"], row["sku"], row["description"], row["unit"], row["tariff_fraction"], row["supplier"]))
        if hasattr(self, "entry_tree"):
            self._clear(self.entry_tree)
            for row in self.conn.execute("SELECT m.*, x.sku FROM movements m JOIN materials x ON x.id=m.material_id WHERE m.kind='Entrada temporal' ORDER BY m.id DESC"):
                self.entry_tree.insert("", "end", values=(row["movement_date"], row["document"], row["customs"], row["pedimento_key"], row["sku"], f"{row['quantity']:g}", f"{row['unit_value']:.2f}"))
        if hasattr(self, "output_tree"):
            self._clear(self.output_tree)
            for row in self.conn.execute("SELECT m.*, x.sku, GROUP_CONCAT(a.entry_id) AS affected FROM movements m JOIN materials x ON x.id=m.material_id LEFT JOIN allocations a ON a.movement_id=m.id WHERE m.kind!='Entrada temporal' GROUP BY m.id ORDER BY m.id DESC"):
                if row["kind"] != "Consumo en producción":
                    self.output_tree.insert("", "end", values=(row["movement_date"], row["kind"], row["document"], row["sku"], f"{row['quantity']:g}", row["affected"] or ""))
        if hasattr(self, "consumption_tree"):
            self._clear(self.consumption_tree)
            for row in self.conn.execute("SELECT m.*, x.sku, GROUP_CONCAT(a.entry_id) AS affected FROM movements m JOIN materials x ON x.id=m.material_id LEFT JOIN allocations a ON a.movement_id=m.id WHERE m.kind='Consumo en producción' GROUP BY m.id ORDER BY m.id DESC"):
                self.consumption_tree.insert("", "end", values=(row["movement_date"], row["document"], row["sku"], f"{row['quantity']:g}", row["affected"] or ""))
        if hasattr(self, "dashboard_tree"):
            self._clear(self.dashboard_tree)
            for row in self.conn.execute("SELECT m.movement_date, m.kind, m.document, x.sku, m.quantity FROM movements m JOIN materials x ON x.id=m.material_id ORDER BY m.id DESC LIMIT 12"):
                self.dashboard_tree.insert("", "end", values=(row["movement_date"], row["kind"], row["document"], row["sku"], f"{row['quantity']:g}"))
            total_available = sum(self._available(row["id"]) for row in materials)
            self.metrics["materials"].configure(text=str(len(materials)))
            self.metrics["entries"].configure(text=str(self.conn.execute("SELECT COUNT(*) FROM movements WHERE kind='Entrada temporal'").fetchone()[0]))
            self.metrics["available"].configure(text=f"{total_available:g}")
            self.metrics["pending"].configure(text=f"{total_available:g}")

    @staticmethod
    def _clear(tree):
        for item in tree.get_children(): tree.delete(item)

    def export_report(self, report, title):
        queries = {
            "entries": ("SELECT m.movement_date, m.document, m.customs, m.pedimento_key, x.sku, x.description, m.quantity, x.unit, m.unit_value FROM movements m JOIN materials x ON x.id=m.material_id WHERE m.kind='Entrada temporal' ORDER BY m.movement_date", "fecha,documento,aduana,clave_pedimento,sku,descripcion,cantidad,unidad,valor_unitario"),
            "outputs": ("SELECT m.movement_date, m.kind, m.document, x.sku, m.quantity, GROUP_CONCAT(a.entry_id) FROM movements m JOIN materials x ON x.id=m.material_id LEFT JOIN allocations a ON a.movement_id=m.id WHERE m.kind!='Entrada temporal' GROUP BY m.id ORDER BY m.movement_date", "fecha,tipo,documento,sku,cantidad,entradas_afectadas"),
            "balances": ("SELECT x.sku, x.description, x.unit, COALESCE(SUM(CASE WHEN m.kind='Entrada temporal' THEN m.quantity ELSE 0 END),0), COALESCE(SUM(CASE WHEN m.kind!='Entrada temporal' THEN m.quantity ELSE 0 END),0), COALESCE(SUM(CASE WHEN m.kind='Entrada temporal' THEN m.quantity ELSE -m.quantity END),0) FROM materials x LEFT JOIN movements m ON m.material_id=x.id GROUP BY x.id ORDER BY x.sku", "sku,descripcion,unidad,entradas,descargos,saldo"),
            "consumptions": ("SELECT m.movement_date, m.document, x.sku, x.description, m.quantity, m.notes FROM movements m JOIN materials x ON x.id=m.material_id WHERE m.kind='Consumo en producción' ORDER BY m.movement_date", "fecha,documento,sku,descripcion,cantidad,observaciones"),
        }
        query, headers = queries[report]
        path = filedialog.asksaveasfilename(title=f"Exportar {title}", defaultextension=".csv", filetypes=(("CSV", "*.csv"),))
        if not path: return
        rows = self.conn.execute(query).fetchall()
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file); writer.writerow(headers.split(",")); writer.writerows([tuple(row) for row in rows])
        messagebox.showinfo("Reporte generado", f"Se exportaron {len(rows)} registros a:\n{path}")

    def _close(self):
        self.conn.close()
        self.destroy()


if __name__ == "__main__":
    InventoryApp().mainloop()