import csv
import io
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st


DB_PATH = Path(__file__).resolve().parent / "inventario_immex.db"


@st.cache_resource
def get_connection():
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    create_schema(connection)
    seed_data(connection)
    return connection


def create_schema(connection):
    connection.executescript(
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
    connection.commit()


def seed_data(connection):
    if connection.execute("SELECT COUNT(*) FROM company").fetchone()[0] == 0:
        connection.execute(
            "INSERT INTO company VALUES (1, ?, ?, ?, ?, ?, ?, 1)",
            (
                "Textiles y Confecciones del Centro, S.A. de C.V.",
                "TEXCO",
                "TCC261001AB1",
                "POR AUTORIZAR - PRÁCTICA",
                "Puebla, Puebla, México",
                "Planta y almacén académico: Puebla, Puebla, México",
            ),
        )
    if connection.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 0:
        connection.executemany(
            "INSERT INTO materials (sku, description, unit, tariff_fraction, supplier) VALUES (?, ?, ?, ?, ?)",
            [
                ("TELA-001", "Tela de algodón para playera", "Metro", "5208.52.01", "Proveedor textil extranjero"),
                ("HILO-001", "Hilo de poliéster", "Kilogramo", "5401.10.01", "Proveedor de insumos extranjero"),
                ("BOT-001", "Botón plástico", "Pieza", "9606.29.99", "Proveedor de accesorios extranjero"),
                ("CIE-001", "Cierre nylon", "Pieza", "9607.19.99", "Proveedor de accesorios extranjero"),
            ],
        )
    connection.commit()


def query_frame(connection, query, params=()):
    return pd.read_sql_query(query, connection, params=params)


def materials(connection):
    return connection.execute("SELECT * FROM materials WHERE active=1 ORDER BY sku").fetchall()


def available(connection, material_id):
    row = connection.execute(
        """
        SELECT COALESCE(SUM(m.quantity - COALESCE(
            (SELECT SUM(a.quantity) FROM allocations a WHERE a.entry_id = m.id), 0
        )), 0) AS balance
        FROM movements m
        WHERE m.kind = 'Entrada temporal' AND m.material_id = ?
        """,
        (material_id,),
    ).fetchone()
    return float(row["balance"] or 0)


def add_entry(connection, values):
    connection.execute(
        """INSERT INTO movements
        (kind, movement_date, document, customs, pedimento_key, patent,
         material_id, quantity, unit_value, notes)
        VALUES ('Entrada temporal', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        values,
    )
    connection.commit()


def add_output(connection, values):
    movement_date, kind, document, material_id, quantity, notes = values
    if quantity > available(connection, material_id) + 1e-9:
        raise ValueError("La cantidad supera el saldo disponible del material.")
    cursor = connection.execute(
        "INSERT INTO movements (kind, movement_date, document, material_id, quantity, notes) VALUES (?, ?, ?, ?, ?, ?)",
        values,
    )
    movement_id = cursor.lastrowid
    entries = connection.execute(
        """SELECT m.id, m.quantity - COALESCE(
            (SELECT SUM(a.quantity) FROM allocations a WHERE a.entry_id = m.id), 0
        ) AS remaining
        FROM movements m
        WHERE m.kind = 'Entrada temporal' AND m.material_id = ?
          AND m.quantity - COALESCE((SELECT SUM(a.quantity) FROM allocations a WHERE a.entry_id = m.id), 0) > 0
        ORDER BY m.movement_date, m.id""",
        (material_id,),
    ).fetchall()
    pending = quantity
    for entry in entries:
        applied = min(pending, entry["remaining"])
        if applied > 0:
            connection.execute(
                "INSERT INTO allocations (movement_id, entry_id, quantity) VALUES (?, ?, ?)",
                (movement_id, entry["id"], applied),
            )
            pending -= applied
        if pending <= 1e-9:
            break
    connection.commit()


def movement_frames(connection):
    entries = query_frame(
        connection,
        """SELECT m.movement_date AS Fecha, m.document AS Pedimento, m.customs AS Aduana,
        m.pedimento_key AS Clave, x.sku AS SKU, x.description AS Descripción,
        m.quantity AS Cantidad, x.unit AS Unidad, m.unit_value AS Valor_unitario
        FROM movements m JOIN materials x ON x.id=m.material_id
        WHERE m.kind='Entrada temporal' ORDER BY m.id DESC""",
    )
    outputs = query_frame(
        connection,
        """SELECT m.movement_date AS Fecha, m.kind AS Tipo, m.document AS Documento,
        x.sku AS SKU, m.quantity AS Cantidad, GROUP_CONCAT(a.entry_id) AS Entradas_afectadas
        FROM movements m JOIN materials x ON x.id=m.material_id
        LEFT JOIN allocations a ON a.movement_id=m.id
        WHERE m.kind!='Entrada temporal' GROUP BY m.id ORDER BY m.id DESC""",
    )
    consumptions = outputs[outputs["Tipo"] == "Consumo en producción"].copy()
    outputs = outputs[outputs["Tipo"] != "Consumo en producción"].copy()
    balances = query_frame(
        connection,
        """SELECT x.sku AS SKU, x.description AS Descripción, x.unit AS Unidad,
        COALESCE(SUM(CASE WHEN m.kind='Entrada temporal' THEN m.quantity ELSE 0 END),0) AS Entradas,
        COALESCE(SUM(CASE WHEN m.kind!='Entrada temporal' THEN m.quantity ELSE 0 END),0) AS Descargos,
        COALESCE(SUM(CASE WHEN m.kind='Entrada temporal' THEN m.quantity ELSE -m.quantity END),0) AS Saldo
        FROM materials x LEFT JOIN movements m ON m.material_id=x.id
        GROUP BY x.id ORDER BY x.sku""",
    )
    recent = query_frame(
        connection,
        """SELECT m.movement_date AS Fecha, m.kind AS Movimiento, m.document AS Documento,
        x.sku AS SKU, m.quantity AS Cantidad
        FROM movements m JOIN materials x ON x.id=m.material_id ORDER BY m.id DESC LIMIT 12""",
    )
    return entries, outputs, consumptions, balances, recent


def csv_bytes(frame):
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, encoding="utf-8-sig")
    return buffer.getvalue().encode("utf-8-sig")


def show_help():
    with st.expander("Guía de utilización y significado de campos"):
        st.markdown(
            """
            **Cómo utilizar la aplicación**

            1. Revisa los datos de **Empresa**.
            2. Da de alta los insumos en **Materiales**.
            3. Registra una importación temporal en **Entradas**.
            4. Registra un consumo, retorno o salida en **Movimientos**.
            5. Revisa el saldo y descarga los reportes en **Reportes**.

            **Campos principales**

            - **SKU:** identificador único del material.
            - **Unidad:** pieza, metro, kilogramo u otra unidad de control.
            - **Fracción arancelaria:** clasificación declarada de la mercancía.
            - **Fecha de pago:** fecha de pago del pedimento.
            - **Número de pedimento:** documento que respalda la entrada temporal.
            - **Documento de salida:** folio que respalda consumo, retorno, transferencia o cambio de régimen.
            - **Entradas afectadas:** entradas temporales descontadas mediante FIFO.

            Esta aplicación es una simulación académica y no sustituye el pedimento ni la validación de un especialista.
            """
        )


def main():
    st.set_page_config(page_title="TEXCO | Anexo 24", page_icon="📦", layout="wide")
    connection = get_connection()
    st.title("TEXCO")
    st.caption("Control de inventarios IMMEX | Anexo 24 | EJERCICIO ACADÉMICO")
    show_help()

    entries, outputs, consumptions, balances, recent = movement_frames(connection)
    material_rows = materials(connection)
    total_available = float(balances["Saldo"].sum()) if not balances.empty else 0

    metric_columns = st.columns(4)
    metric_columns[0].metric("Materiales", len(material_rows))
    metric_columns[1].metric("Entradas", len(entries))
    metric_columns[2].metric("Existencia disponible", f"{total_available:g}")
    metric_columns[3].metric("Pendiente de descargo", f"{total_available:g}")

    tabs = st.tabs(["Resumen", "Empresa", "Materiales", "Entradas", "Consumos y salidas", "Reportes"])
    with tabs[0]:
        st.subheader("Estado del inventario")
        st.dataframe(recent, use_container_width=True, hide_index=True)
        st.subheader("Saldos por material")
        st.dataframe(balances, use_container_width=True, hide_index=True)

    with tabs[1]:
        st.subheader("Datos generales del contribuyente")
        company = connection.execute("SELECT * FROM company WHERE id=1").fetchone()
        with st.form("company_form"):
            legal_name = st.text_input("Razón social", company["legal_name"])
            trade_name = st.text_input("Nombre comercial", company["trade_name"])
            rfc = st.text_input("RFC", company["rfc"])
            immex_number = st.text_input("Programa IMMEX", company["immex_number"])
            tax_address = st.text_input("Domicilio fiscal", company["tax_address"])
            plant_address = st.text_input("Planta / almacén", company["plant_address"])
            if st.form_submit_button("Guardar datos de empresa"):
                connection.execute(
                    "UPDATE company SET legal_name=?, trade_name=?, rfc=?, immex_number=?, tax_address=?, plant_address=? WHERE id=1",
                    (legal_name, trade_name, rfc, immex_number, tax_address, plant_address),
                )
                connection.commit()
                st.success("Datos de empresa actualizados.")

    with tabs[2]:
        st.subheader("Catálogo de materiales")
        with st.form("material_form", clear_on_submit=True):
            columns = st.columns(2)
            sku = columns[0].text_input("SKU / número de parte")
            description = columns[1].text_input("Descripción")
            unit = columns[0].text_input("Unidad")
            tariff = columns[1].text_input("Fracción arancelaria")
            supplier = st.text_input("Proveedor extranjero")
            if st.form_submit_button("Registrar material"):
                if not sku or not description or not unit:
                    st.error("SKU, descripción y unidad son obligatorios.")
                else:
                    try:
                        connection.execute(
                            "INSERT INTO materials (sku, description, unit, tariff_fraction, supplier) VALUES (?, ?, ?, ?, ?)",
                            (sku.strip(), description.strip(), unit.strip(), tariff.strip(), supplier.strip()),
                        )
                        connection.commit()
                        st.success("Material registrado.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Ya existe un material con ese SKU.")
        st.dataframe(query_frame(connection, "SELECT sku AS SKU, description AS Descripción, unit AS Unidad, tariff_fraction AS Fracción, supplier AS Proveedor FROM materials WHERE active=1 ORDER BY sku"), use_container_width=True, hide_index=True)

    with tabs[3]:
        st.subheader("Información aduanera de entradas")
        material_options = {f"{row['sku']} | {row['description']}": row["id"] for row in material_rows}
        with st.form("entry_form", clear_on_submit=True):
            columns = st.columns(3)
            entry_date = columns[0].date_input("Fecha de pago", date.today())
            document = columns[1].text_input("Número de pedimento")
            customs = columns[2].text_input("Aduana")
            pedimento_key = columns[0].text_input("Clave de pedimento")
            patent = columns[1].text_input("Patente / autorización")
            quantity = columns[2].number_input("Cantidad", min_value=0.01, value=1.0)
            value = columns[0].number_input("Valor unitario", min_value=0.0, value=0.0)
            material_label = columns[1].selectbox("Material", list(material_options))
            notes = columns[2].text_input("Observaciones")
            if st.form_submit_button("Registrar entrada temporal"):
                if not document or not customs or not pedimento_key:
                    st.error("Pedimento, aduana y clave son obligatorios.")
                else:
                    add_entry(connection, (entry_date.isoformat(), document.strip(), customs.strip(), pedimento_key.strip(), patent.strip(), material_options[material_label], quantity, value, notes.strip()))
                    st.success("Entrada temporal registrada.")
                    st.rerun()
        st.dataframe(movement_frames(connection)[0], use_container_width=True, hide_index=True)

    with tabs[4]:
        st.subheader("Consumos, retornos y descargos")
        output_options = ["Consumo en producción", "Retorno al extranjero", "Transferencia virtual", "Cambio de régimen", "Destrucción / donación"]
        with st.form("output_form", clear_on_submit=True):
            columns = st.columns(3)
            output_date = columns[0].date_input("Fecha", date.today())
            output_kind = columns[1].selectbox("Tipo de movimiento", output_options)
            output_document = columns[2].text_input("Documento de salida")
            output_material_label = columns[0].selectbox("Material", list(material_options), key="output_material")
            output_quantity = columns[1].number_input("Cantidad", min_value=0.01, value=1.0, key="output_quantity")
            output_notes = columns[2].text_input("Observaciones", key="output_notes")
            st.caption(f"Saldo disponible del material seleccionado: {available(connection, material_options[output_material_label]):g}")
            if st.form_submit_button("Registrar y ejecutar descargo"):
                if not output_document.strip():
                    st.error("El documento de salida es obligatorio.")
                else:
                    try:
                        add_output(connection, (output_date.isoformat(), output_kind, output_document.strip(), material_options[output_material_label], output_quantity, output_notes.strip()))
                        st.success("Movimiento registrado y descargo ejecutado.")
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
        current_entries, current_outputs, current_consumptions, _, _ = movement_frames(connection)
        st.subheader("Materiales utilizados en producción")
        st.dataframe(current_consumptions, use_container_width=True, hide_index=True)
        st.subheader("Salidas aduaneras")
        st.dataframe(current_outputs, use_container_width=True, hide_index=True)

    with tabs[5]:
        st.subheader("Reportes del Anexo 24")
        report_data = {
            "Entradas temporales": entries,
            "Salidas aduaneras": outputs,
            "Saldos por material": balances,
            "Materiales utilizados": consumptions,
        }
        for name, frame in report_data.items():
            st.download_button(
                f"Descargar {name.lower()}",
                data=csv_bytes(frame),
                file_name=f"{name.lower().replace(' ', '_')}.csv",
                mime="text/csv",
                key=f"download_{name}",
            )
            st.dataframe(frame, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
