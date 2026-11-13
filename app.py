from __future__ import annotations

import io
import re
import unicodedata

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Seguimiento de licencias medicas", page_icon=":material/monitor_heart:", layout="wide")

VALID_STATES = {"cotizacionpagada", "cotizacionpagadaparcialmente", "cotizacionpendientepago"}
ALERT_WEEKS = (40, 92, 103, 104)


def normalize_text(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    text = unicodedata.normalize("NFKD", text.replace("ï¿½", ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def read_uploaded_file(name: str, content: bytes) -> pd.DataFrame:
    if name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(content))
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            return pd.read_csv(io.BytesIO(content), encoding=encoding, low_memory=False)
        except UnicodeDecodeError:
            pass
    raise ValueError("No fue posible leer el CSV con las codificaciones esperadas.")


def standardize_columns(raw: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "folio": "folio", "ruttrabajador": "rut", "rut": "rut",
        "calidadtrabajador": "calidad", "calidad": "calidad",
        "region": "region", "regin": "region", "fechainicio": "fecha_inicio",
        "fechatermino": "fecha_termino", "dias": "dias", "diasautorizados": "dias",
        "cie10": "cie10", "estadolicencia": "estado", "estado": "estado",
        "idsiniestro": "siniestro", "siniestro": "siniestro",
    }
    rename = {c: aliases[normalize_text(c)] for c in raw.columns if normalize_text(c) in aliases}
    data = raw.rename(columns=rename).copy()
    required = {"rut": "RUT Trabajador", "calidad": "Calidad Trabajador", "region": "Region",
                "fecha_inicio": "Fecha Inicio", "fecha_termino": "Fecha Termino", "dias": "Dias",
                "cie10": "Cie10", "estado": "Estado Licencia", "siniestro": "Id Siniestro"}
    missing = [label for key, label in required.items() if key not in data.columns]
    if missing:
        raise ValueError("Faltan columnas obligatorias: " + ", ".join(missing))
    for column, fallback in (("calidad", "Sin informacion"), ("region", "Sin informacion"), ("cie10", "Sin informacion")):
        data[column] = data[column].astype("string").fillna(fallback).str.strip()
    data["rut"] = data["rut"].astype("string").str.strip()
    data["siniestro"] = data["siniestro"].astype("string").str.strip()
    data["estado_normalizado"] = data["estado"].map(normalize_text)
    data["fecha_inicio"] = pd.to_datetime(data["fecha_inicio"], errors="coerce")
    data["fecha_termino"] = pd.to_datetime(data["fecha_termino"], errors="coerce")
    data["dias"] = pd.to_numeric(data["dias"], errors="coerce")
    return data.dropna(subset=["rut", "siniestro", "fecha_inicio", "dias"])


def build_summary(data: pd.DataFrame) -> pd.DataFrame:
    valid = data[data["estado_normalizado"].isin(VALID_STATES)].copy()
    if valid.empty:
        return pd.DataFrame()
    keys = ["rut", "siniestro"]
    valid = valid.sort_values(keys + ["fecha_inicio"])
    grouped = valid.groupby(keys, dropna=False, sort=False)
    summary = grouped.agg(numero_licencias=("fecha_inicio", "size"), dias_autorizados=("dias", "sum"), inicio_primera_licencia=("fecha_inicio", "min")).reset_index()
    first = valid.loc[grouped["fecha_inicio"].idxmin(), keys + ["cie10"]].rename(columns={"cie10": "cie10_primera_licencia"})
    last = valid.loc[grouped["fecha_inicio"].idxmax(), keys + ["fecha_termino", "cie10", "region", "calidad"]].rename(columns={"fecha_termino": "termino_ultima_licencia", "cie10": "cie10_ultima_licencia", "calidad": "calidad_trabajador"})
    summary = summary.merge(first, on=keys, how="left").merge(last, on=keys, how="left")
    summary["semanas_autorizadas"] = summary["dias_autorizados"] / 7
    summary["alertas"] = summary["semanas_autorizadas"].map(lambda w: ", ".join(str(x) for x in ALERT_WEEKS if w >= x) + " semanas" if any(w >= x for x in ALERT_WEEKS) else "Sin alerta")
    return summary.rename(columns={"rut": "RUT trabajador", "siniestro": "ID siniestro", "numero_licencias": "N licencias", "dias_autorizados": "Dias autorizados", "semanas_autorizadas": "Semanas autorizadas", "inicio_primera_licencia": "Inicio primera licencia", "termino_ultima_licencia": "Termino ultima licencia", "cie10_primera_licencia": "CIE10 primera licencia", "cie10_ultima_licencia": "CIE10 ultima licencia", "calidad_trabajador": "Calidad trabajador", "region": "Region", "alertas": "Alertas"})


@st.cache_data(show_spinner=False)
def process_file(name: str, content: bytes) -> tuple[pd.DataFrame, int]:
    data = standardize_columns(read_uploaded_file(name, content))
    return build_summary(data), len(data)


if "upload_key" not in st.session_state:
    st.session_state.upload_key = 0
st.title("Seguimiento de licencias medicas")
st.caption("Cada usuario carga su propia base y el analisis se realiza dentro de su sesion.")
with st.container(border=True):
    st.subheader("Actualizar base de datos")
    uploaded = st.file_uploader("Selecciona un archivo Excel o CSV", type=["xlsx", "xls", "csv"], key=f"database_upload_{st.session_state.upload_key}", help="La base cargada no se guarda en GitHub ni en una base central.")
    st.info("Se consideran los estados Cotizacion pagada, Cotizacion pagada parcialmente y Cotizacion pendiente pago.", title="Regla de calculo")
if not uploaded:
    st.warning("Carga un archivo para comenzar.", title="Base de datos pendiente")
    st.stop()
try:
    with st.spinner("Procesando la base y calculando semanas..."):
        result, source_rows = process_file(uploaded.name, uploaded.getvalue())
except (ValueError, KeyError, OSError) as exc:
    st.error(str(exc), title="No se pudo procesar el archivo")
    st.stop()
if result.empty:
    st.error("No se encontraron registros con estados de cotizacion validos.", title="Sin registros utilizables")
    st.stop()
st.success(f"Base cargada: {uploaded.name} - {source_rows:,} registros validos para el analisis.")
with st.sidebar:
    st.header("Filtros")
    qualities = sorted(result["Calidad trabajador"].dropna().unique().tolist())
    selected_qualities = st.multiselect("Calidad del trabajador", qualities, default=qualities)
    rut_query = st.text_input("RUT", placeholder="Ejemplo: 12345678-9", type="search")
    week_data_min = float(result["Semanas autorizadas"].min())
    week_data_max = float(result["Semanas autorizadas"].max())
    st.markdown("**Rango de semanas autorizadas**")
    week_from = st.number_input(
        "Semanas desde",
        min_value=0.0,
        max_value=max(week_data_max, 0.0),
        value=max(0.0, min(week_data_min, week_data_max)),
        step=0.1,
        format="%.1f",
    )
    week_to = st.number_input(
        "Semanas hasta",
        min_value=0.0,
        max_value=max(week_data_max, 0.0),
        value=max(week_data_max, 0.0),
        step=0.1,
        format="%.1f",
    )
    weeks = (week_from, week_to)
    dates = st.date_input("Inicio de la primera licencia", value=(result["Inicio primera licencia"].min().date(), result["Inicio primera licencia"].max().date()))
    if st.button("Cargar otra base", icon=":material/upload_file:"):
        st.session_state.upload_key += 1
        st.rerun()
filtered = result[result["Calidad trabajador"].isin(selected_qualities)].copy()
if rut_query:
    filtered = filtered[filtered["RUT trabajador"].str.contains(rut_query.strip(), case=False, na=False)]
if weeks[0] > weeks[1]:
    st.warning("El valor de semanas desde no puede ser mayor que semanas hasta.")
    filtered = filtered.iloc[0:0]
else:
    filtered = filtered[filtered["Semanas autorizadas"].between(weeks[0], weeks[1])]
if isinstance(dates, tuple) and len(dates) == 2:
    filtered = filtered[filtered["Inicio primera licencia"].dt.date.between(dates[0], dates[1])]
with st.container(horizontal=True):
    st.metric("Siniestros analizados", f"{len(filtered):,}", border=True)
    st.metric("Trabajadores", f"{filtered['RUT trabajador'].nunique():,}", border=True)
    st.metric("Con alerta", f"{int(filtered['Alertas'].ne('Sin alerta').sum()):,}", border=True)
    st.metric("Semanas maximas", f"{filtered['Semanas autorizadas'].max():.1f}" if not filtered.empty else "0.0", border=True)
columns = ["RUT trabajador", "ID siniestro", "Calidad trabajador", "N licencias", "Dias autorizados", "Semanas autorizadas", "Inicio primera licencia", "Termino ultima licencia", "CIE10 primera licencia", "CIE10 ultima licencia", "Region", "Alertas"]
st.subheader("Resumen por trabajador y siniestro")
st.dataframe(filtered[columns].sort_values("Semanas autorizadas", ascending=False), hide_index=True, width="stretch", column_config={"Semanas autorizadas": st.column_config.NumberColumn(format="%.1f"), "Inicio primera licencia": st.column_config.DateColumn(format="DD/MM/YYYY"), "Termino ultima licencia": st.column_config.DateColumn(format="DD/MM/YYYY")}, alt="Resumen de licencias medicas agrupadas por RUT e ID de siniestro")
st.download_button("Descargar resultados filtrados", data=filtered[columns].to_csv(index=False).encode("utf-8-sig"), file_name="resumen_licencias_filtrado.csv", mime="text/csv", icon=":material/download:")
