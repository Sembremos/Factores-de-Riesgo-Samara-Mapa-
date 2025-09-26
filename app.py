# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import random, re, math

import gspread
from google.oauth2.service_account import Credentials

import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster, LocateControl, HeatMap

st.set_page_config(page_title="Microdespliegue Sámara – Encuestas", layout="wide")

# ========= CONFIG =========
SHEET_ID = "1_zL294hNTYo1naBNBGviSr8jVMMpUIsUCT96kTnnP1Y"   # tu hoja
WORKSHEET_NAME = "Hoja 1"                                    # pestaña de la hoja
TZ = ZoneInfo("America/Costa_Rica")

# Centro y radio destacado
SAMARA_CENTER = [9.8814, -85.5233]
DESTACAR_RADIO_KM = 4

# Factores y colores
FACTORES = [
    "Calles sin iluminación adecuada por la noche.",
    "Calles con poca visibilidad por vegetación, muros o abandono.",
    "Zonas con lotes baldíos o propiedades abandonadas.",
    "Presencia de personas desconocidas merodeando sin razón aparente.",
    "Personas consumiendo drogas o alcohol en la vía pública.",
    "Presencia constante de motocicletas sin placas o “sospechosas”.",
    "Ausencia de presencia policial visible o cercana.",
    "Accesos rápidos de escape desde la zona (calles, ríos, callejones).",
    "Espacios públicos deteriorados (parques, aceras, etc.).",
    "Ruido excesivo o escándalos a cualquier hora del día.",
    "Falta de cámaras de seguridad en la zona.",
    "Estacionamientos inseguros o sin control.",
    "Grafitis o pintas intimidantes (no artísticas).",
    "Ventas informales o con presencia agresiva.",
    "Frecuente presencia de menores de edad sin supervisión en la zona.",
    "Ingreso fácil a zonas no vigiladas (playas, callejones, senderos).",
    "Altos niveles de basura o suciedad en la zona.",
    "Zonas donde se han dado riñas o enfrentamientos recientemente.",
    "Personas en situación de calle vulnerables o con conductas agresivas.",
    "Negocios abandonados o cerrados de forma permanente.",
    "Vehículos sospechosos parqueados por tiempo prolongado.",
    "Otro: especificar.",
]
FACTOR_COLORS = {
    FACTORES[0]:"#e41a1c", FACTORES[1]:"#377eb8", FACTORES[2]:"#4daf4a",
    FACTORES[3]:"#984ea3", FACTORES[4]:"#ff7f00", FACTORES[5]:"#ffff33",
    FACTORES[6]:"#a65628", FACTORES[7]:"#f781bf", FACTORES[8]:"#999999",
    FACTORES[9]:"#1b9e77", FACTORES[10]:"#d95f02", FACTORES[11]:"#7570b3",
    FACTORES[12]:"#e7298a", FACTORES[13]:"#66a61e", FACTORES[14]:"#e6ab02",
    FACTORES[15]:"#a6761d", FACTORES[16]:"#1f78b4", FACTORES[17]:"#b2df8a",
    FACTORES[18]:"#fb9a99", FACTORES[19]:"#cab2d6", FACTORES[20]:"#fdbf6f",
    FACTORES[21]:"#b15928",
}

NEW_HEADERS = [
    "date","barrio","factores","delitos_relacionados",
    "ligado_estructura","nombre_estructura","observaciones","maps_link"
]

# ========= GSPREAD =========
@st.cache_resource(show_spinner=False)
def _ws():
    scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(WORKSHEET_NAME, rows=2000, cols=26)
        ws.append_row(NEW_HEADERS)
    if not ws.row_values(1):
        ws.append_row(NEW_HEADERS)
    _ensure_schema(ws)
    return ws

def _headers(ws): 
    return [h.strip() for h in ws.row_values(1)]

def _hex_to_rgb01(h):
    h = h.lstrip("#")
    return {"red": int(h[0:2],16)/255.0, "green": int(h[2:4],16)/255.0, "blue": int(h[4:6],16)/255.0}

def _ensure_schema(ws):
    headers = _headers(ws)
    for name in ["lat","lng"]:
        if name in headers:
            ws.delete_columns(headers.index(name)+1)
            headers = _headers(ws)
    if "maps_link" not in headers:
        ws.update_cell(1, len(headers)+1, "maps_link")

def append_row(data: dict):
    ws = _ws()
    headers = _headers(ws)
    maps_url = f'https://www.google.com/maps?q={data["lat"]},{data["lng"]}'
    values = {
        "date": data.get("date",""), "barrio": data.get("barrio",""),
        "factores": data.get("factores",""), "delitos_relacionados": data.get("delitos_relacionados",""),
        "ligado_estructura": data.get("ligado_estructura",""), "nombre_estructura": data.get("nombre_estructura",""),
        "observaciones": data.get("observaciones",""), "maps_link": maps_url,
        "timestamp": data.get("date",""), "factor_riesgo": data.get("factores",""),
    }
    ws.append_row([values.get(c,"") for c in headers], value_input_option="USER_ENTERED")
    # colorear la celda del factor (si existe columna)
    col = None
    if "factores" in headers: col = headers.index("factores")+1
    elif "factor_riesgo" in headers: col = headers.index("factor_riesgo")+1
    if col:
        ws.format(gspread.utils.rowcol_to_a1(len(ws.get_all_values()), col),
                  {"backgroundColor": _hex_to_rgb01(FACTOR_COLORS.get(data.get("factores",""), "#ffffff"))})

@st.cache_data(ttl=30, show_spinner=False)
def read_df() -> pd.DataFrame:
    ws = _ws()
    records = ws.get_all_records()
    df_raw = pd.DataFrame(records)

    df = pd.DataFrame()
    df["date"] = df_raw["date"] if "date" in df_raw.columns else ""
    df["barrio"] = df_raw["barrio"] if "barrio" in df_raw.columns else ""
    df["factores"] = df_raw["factores"] if "factores" in df_raw.columns else ""
    for c in ["delitos_relacionados","ligado_estructura","nombre_estructura","observaciones"]:
        df[c] = df_raw[c] if c in df_raw.columns else ""
    df["maps_link"] = df_raw["maps_link"] if "maps_link" in df_raw.columns else ""

    # extraer lat/lng desde maps_link
    lats, lngs = [], []
    url_pat = re.compile(r"https?://.*maps\?q=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
    for link in df["maps_link"].fillna(""):
        m = url_pat.search(str(link))
        if m:
            lats.append(float(m.group(1))); lngs.append(float(m.group(2)))
        else:
            lats.append(None); lngs.append(None)
    df["lat"], df["lng"] = pd.to_numeric(lats, errors="coerce"), pd.to_numeric(lngs, errors="coerce")
    return df

# ========= MAP UTILS =========
def _jitter(idx: int, base: float = 0.00008) -> float:
    random.seed(idx)
    return (random.random() - 0.5) * base

def _add_panes(m):
    folium.map.CustomPane("mask", z_index=200).add_to(m)
    folium.map.CustomPane("markers", z_index=400).add_to(m)
    folium.map.CustomPane("heatmap", z_index=650).add_to(m)

def _inverse_mask_geojson(center_lat, center_lng, radius_km, npts=96):
    outer=[[-179.9,-89.9],[-179.9,89.9],[179.9,89.9],[179.9,-89.9],[-179.9,-89.9]]
    rlat=radius_km/110.574
    rlng=radius_km/(111.320*max(0.000001,math.cos(math.radians(center_lat))))
    inner=[[center_lng+rlng*math.cos(2*math.pi*i/npts),center_lat+rlat*math.sin(2*math.pi*i/npts)] for i in range(npts)]
    inner.append(inner[0])
    return folium.GeoJson(
        {"type":"FeatureCollection","features":[{
            "type":"Feature","geometry":{"type":"Polygon","coordinates":[outer,inner]}}]},
        name="Máscara 4 km",
        style_function=lambda x:{"fillColor":"#FFF","color":"#999","weight":1,"fillOpacity":0.70},
        overlay=True, control=True, pane="mask"
    )

# ========= UI =========
st.title("📍 Microdespliegue Sámara – Encuestas georreferenciadas")
tabs = st.tabs(["📝 Formulario","🗺️ Mapa & Datos"])

# ======= FORM =======
with tabs[0]:
    left, right = st.columns([0.55, 0.45], gap="large")

    with left:
        st.subheader("Selecciona un punto en el mapa")
        st.caption("Usa el ícono 🎯 (Localizar) para centrar el mapa y luego haz un clic para registrar el punto.")
        clicked = st.session_state.get("clicked") or {}
        center = [clicked.get("lat", SAMARA_CENTER[0]), clicked.get("lng", SAMARA_CENTER[1])]

        m = folium.Map(location=center, zoom_start=13, control_scale=True, tiles=None)
        _add_panes(m)
        folium.TileLayer("CartoDB positron", name="Base gris").add_to(m)
        folium.TileLayer("OpenStreetMap", name="Color local").add_to(m)
        _inverse_mask_geojson(*SAMARA_CENTER, DESTACAR_RADIO_KM).add_to(m)
        LocateControl(auto_start=False, flyTo=True).add_to(m)

        if clicked.get("lat") is not None and clicked.get("lng") is not None:
            folium.CircleMarker([clicked["lat"], clicked["lng"]],
                                radius=8, color="#000", weight=1,
                                fill=True, fill_color="#2dd4bf", fill_opacity=0.9,
                                tooltip="Ubicación seleccionada", pane="markers").add_to(m)

        folium.LayerControl(collapsed=False).add_to(m)
        map_ret = st_folium(m, height=520, use_container_width=True)
        if map_ret and map_ret.get("last_clicked"):
            st.session_state["clicked"] = {
                "lat": round(map_ret["last_clicked"]["lat"], 6),
                "lng": round(map_ret["last_clicked"]["lng"], 6),
            }
            clicked = st.session_state["clicked"]

        cols = st.columns(3)
        lat_val, lng_val = clicked.get("lat"), clicked.get("lng")
        cols[0].metric("Latitud", lat_val if lat_val is not None else "—")
        cols[1].metric("Longitud", lng_val if lng_val is not None else "—")
        if cols[2].button("Limpiar selección"):
            st.session_state.pop("clicked", None); st.rerun()

    with right:
        st.subheader("Formulario de encuesta")
        with st.form("form_encuesta", clear_on_submit=True):
            barrio = st.text_input("Barrio *")
            factor_sel = st.selectbox("Factor de riesgo *", options=FACTORES, index=None,
                                      placeholder="Selecciona un factor")
            delitos = st.text_area("Delitos relacionados al factor *", height=70)
            ligado = st.radio("Ligado a estructura criminal *", ["No", "Sí"], index=0, horizontal=True)
            nombre_estructura = st.text_input("Nombre de la estructura ligada (si aplica)")
            observ = st.text_area("Observaciones", height=90)
            submit = st.form_submit_button("Guardar en Google Sheets")

        if submit:
            errs = []
            if not barrio.strip(): errs.append("Indica el **Barrio**.")
            if not factor_sel: errs.append("Selecciona un **factor de riesgo**.")
            if not delitos.strip(): errs.append("Indica los **delitos relacionados**.")
            if lat_val is None or lng_val is None: errs.append("Selecciona un **punto en el mapa**.")
            if errs:
                st.error("• " + "\n• ".join(errs))
            else:
                data = {
                    "date": datetime.now(TZ).strftime("%d-%m-%Y"),
                    "barrio": barrio.strip(),
                    "factores": factor_sel,
                    "delitos_relacionados": delitos.strip(),
                    "ligado_estructura": ligado,
                    "nombre_estructura": nombre_estructura.strip(),
                    "observaciones": observ.strip(),
                    "lat": lat_val, "lng": lng_val,
                }
                try:
                    append_row(data)
                    st.success("✅ Respuesta guardada correctamente en Google Sheets.")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"❌ No se pudo guardar en Google Sheets.\n\n{e}")

# ======= MAPA & DATOS =======
with tabs[1]:
    st.subheader("Mapa interactivo + Tabla y mapa de calor")
    df = read_df()
    if df.empty:
        st.info("Aún no hay registros.")
    else:
        c1, c2, c3 = st.columns([0.45, 0.25, 0.30])
        with c1:
            factores_unicos = sorted([f for f in df["factores"].dropna().unique() if f])
            filtro = st.selectbox("Filtrar por factor", options=["(Todos)"] + factores_unicos, index=0)
        with c2:
            show_heat = st.checkbox("Mostrar HeatMap", value=True)
        with c3:
            show_clusters = st.checkbox("Mostrar clusters", value=False)

        m2 = folium.Map(location=SAMARA_CENTER, zoom_start=13, control_scale=True, tiles=None)
        _add_panes(m2)
        folium.TileLayer("CartoDB positron", name="Base gris").add_to(m2)
        folium.TileLayer("OpenStreetMap", name="Color local").add_to(m2)
        _inverse_mask_geojson(*SAMARA_CENTER, DESTACAR_RADIO_KM).add_to(m2)
        LocateControl(auto_start=False).add_to(m2)

        # Leyenda
        items = "".join(
            f'<div style="display:flex;align-items:flex-start;margin-bottom:6px">'
            f'<span style="width:12px;height:12px;background:{FACTOR_COLORS.get(f,"#555")};'
            f'display:inline-block;margin-right:8px;border:1px solid #333;"></span>'
            f'<span style="font-size:12px;color:#000;line-height:1.2;">{f}</span></div>'
            for f in FACTORES
        )
        legend_html = (
            '<div style="position: fixed; bottom: 20px; right: 20px; z-index:9999; '
            'background: rgba(255,255,255,0.98); padding:10px; border:1px solid #666; '
            'border-radius:6px; max-height:320px; overflow:auto; width:340px; color:#000;">'
            '<div style="font-weight:700; margin-bottom:6px; color:#000;">Leyenda – Factores</div>'
            f'{items}</div>'
        )
        m2.get_root().html.add_child(folium.Element(legend_html))

        # Marcadores / cluster
        cluster = (MarkerCluster(name="Marcadores", overlay=True, control=True, pane="markers")
                   if show_clusters else folium.FeatureGroup(name="Marcadores", overlay=True, control=True))
        cluster.add_to(m2)

        heat_points = []
        idx = 0
        omitidos = 0

        for _, r in df.iterrows():
            lat, lng = r.get("lat"), r.get("lng")
            if pd.isna(lat) or pd.isna(lng):
                omitidos += 1
                continue
            if filtro != "(Todos)" and r.get("factores","") != filtro:
                continue

            color = FACTOR_COLORS.get(r.get("factores",""), "#555555")
            jlat = float(lat) + _jitter(idx); jlng = float(lng) + _jitter(idx+101)
            folium.CircleMarker([jlat, jlng], radius=7, color="#000", weight=1,
                                fill=True, fill_color=color, fill_opacity=0.9,
                                popup=(f"<b>Fecha:</b> {r.get('date','')}<br>"
                                       f"<b>Barrio:</b> {r.get('barrio','')}<br>"
                                       f"<b>Factor:</b> {r.get('factores','')}<br>"
                                       f"<b>Delitos:</b> {r.get('delitos_relacionados','')}<br>"
                                       f"<b>Estructura:</b> {r.get('ligado_estructura','')} {r.get('nombre_estructura','')}<br>"
                                       f"<b>Obs:</b> {r.get('observaciones','')}"),
                                pane="markers").add_to(cluster)
            heat_points.append([float(lat), float(lng), 1.0])
            idx += 1

        # === HEATMAP SOLO EN ROJOS ===
        if show_heat and heat_points:
            # Gradiente en rojos: pink -> red -> darkred
            red_gradient = {0.2: "pink", 0.5: "red", 1.0: "darkred"}
            HeatMap(heat_points,
                    radius=18, blur=22, max_zoom=16, min_opacity=0.25,
                    gradient=red_gradient).add_to(folium.FeatureGroup(name="Mapa de calor", overlay=True, control=True, pane="heatmap").add_to(m2))

        folium.LayerControl(collapsed=False).add_to(m2)
        st_folium(m2, height=540, use_container_width=True)

        if omitidos:
            st.caption(f"({omitidos} registro(s) omitidos por coordenadas inválidas)")

        # ===== Tabla =====
        st.markdown("#### Tabla de respuestas")
        show_df = df[["date","barrio","factores","delitos_relacionados",
                      "ligado_estructura","nombre_estructura","observaciones","maps_link"]]
        st.dataframe(show_df, use_container_width=True)
        st.download_button("⬇️ Descargar CSV",
                           data=show_df.to_csv(index=False).encode("utf-8"),
                           file_name="encuestas_samara.csv", mime="text/csv")




