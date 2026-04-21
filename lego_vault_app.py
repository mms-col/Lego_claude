"""
Lego Vault OS Pro — con Supabase (PostgreSQL)
Base de datos persistente en la nube, gratis.
"""

import streamlit as st
import pandas as pd
import psycopg2
import psycopg2.extras
import requests
import plotly.express as px
import os

st.set_page_config(page_title="Lego Vault OS Pro", layout="centered", page_icon="🧱")

def get_api_key() -> str:
    try:
        return st.secrets["REBRICKABLE_API_KEY"]
    except Exception:
        return os.getenv("REBRICKABLE_API_KEY", "")

def get_database_url() -> str:
    try:
        return st.secrets["DATABASE_URL"]
    except Exception:
        return os.getenv("DATABASE_URL", "")

API_KEY = get_api_key()
DB_URL  = get_database_url()

def get_conn():
    return psycopg2.connect(DB_URL, sslmode="require")

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sets (
                    "Number"                TEXT PRIMARY KEY,
                    "SetName"               TEXT,
                    "YearFrom"              INTEGER,
                    "Theme"                 TEXT,
                    "USRetailPrice"         REAL DEFAULT 0,
                    "BrickLinkSoldPriceNew" REAL DEFAULT 0,
                    "ImageURL"              TEXT
                )
            """)
        conn.commit()

try:
    init_db()
except Exception as e:
    st.error(f"❌ No se pudo conectar a la base de datos: {e}")
    st.stop()

@st.cache_data(ttl=3600)
def get_trm_colombia() -> float:
    url = "https://www.datos.gov.co/resource/m97v-v6y7.json?$order=vigenciadesde DESC&$limit=1"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return float(resp.json()[0]["valor"])
    except Exception:
        pass
    return 3950.0

def get_rebrickable_info(set_num: str) -> dict | None:
    clean_num = str(set_num).split("-")[0]
    url = f"https://rebrickable.com/api/v3/lego/sets/{clean_num}-1/"
    headers = {"Authorization": f"key {API_KEY}"}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None

@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql('SELECT * FROM sets', conn)
    df["USRetailPrice"] = pd.to_numeric(df["USRetailPrice"], errors="coerce").fillna(0)
    df["BrickLinkSoldPriceNew"] = pd.to_numeric(df["BrickLinkSoldPriceNew"], errors="coerce").fillna(0)
    return df

def save_new_set(api_data: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO sets ("Number","SetName","YearFrom","Theme","USRetailPrice","ImageURL")
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT ("Number") DO NOTHING
            """, (api_data["set_num"], api_data["name"], api_data["year"],
                  "Nuevo Ingreso", 0, api_data.get("set_img_url","")))
        conn.commit()

def repair_image_url(number: str, img_url: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('UPDATE sets SET "ImageURL"=%s WHERE "Number"=%s', (img_url, number))
        conn.commit()

st.markdown("""
<style>
    .stApp { background-color: white; }
    [data-testid="stSidebar"] { background-color: #1e2030; color: white; }
    [data-testid="stSidebar"] * { color: white !important; }
    div[data-testid="metric-container"] {
        background-color: #f0f2f6; border: 1px solid #e0e3eb;
        padding: 15px; border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

df      = load_data()
trm_hoy = get_trm_colombia()

with st.sidebar:
    st.markdown("""
        <div style='display:flex;align-items:center;gap:10px;margin-bottom:5px;'>
            <span style='font-size:25px;'>🧱</span>
            <h1 style='margin:0;font-size:22px;'>Lego Vault OS Pro</h1>
        </div>
        <p style='color:#a3a8b4;font-size:14px;margin-bottom:20px;'>
            Colección personal · Medellín, Colombia
        </p>
    """, unsafe_allow_html=True)
    st.markdown(f"**TRM Oficial Hoy:**<br><span style='font-size:20px;'>${trm_hoy:,.0f} COP</span>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**Agregar set por número**")
    new_set_input = st.text_input("", placeholder="Ej: 10305", label_visibility="collapsed")
    if new_set_input:
        api_data = get_rebrickable_info(new_set_input.strip())
        if api_data:
            st.image(api_data["set_img_url"], caption=api_data["name"])
            if st.button("✅ Confirmar y Guardar"):
                save_new_set(api_data)
                st.success("¡Set añadido!")
                st.cache_data.clear()
                st.rerun()
        else:
            st.error("Set no encontrado en Rebrickable.")
    if os.path.exists("explorer.png"):
        st.markdown("<br>"*6, unsafe_allow_html=True)
        st.image("explorer.png", use_container_width=True)

st.title("📊 Métricas")
st.caption(f"Base de datos en la nube · TRM: ${trm_hoy:,.0f} COP/USD")

total_inv_usd = df["USRetailPrice"].sum()
total_mkt_usd = df["BrickLinkSoldPriceNew"].sum()
total_mkt_cop = total_mkt_usd * trm_hoy
roi = ((total_mkt_usd - total_inv_usd) / total_inv_usd * 100) if total_inv_usd > 0 else 0

m1,m2,m3,m4 = st.columns(4)
with m1: st.metric("Inversión (USD)",     f"${total_inv_usd:,.2f}")
with m2: st.metric("Valor Mercado (USD)", f"${total_mkt_usd:,.2f}")
with m3: st.metric("Valor Mercado (COP)", f"${total_mkt_cop/1_000_000:.2f}M")
with m4: st.metric("ROI",                f"{roi:.1f}%")

st.markdown("---")
st.subheader("🔍 Inventario local")
search = st.text_input("Busca por nombre o número en tu colección:", placeholder="Ej: Millennium Falcon")

if search:
    term = search.strip().lower()
    mask = (df["Number"].astype(str).str.lower().str.contains(term) |
            df["SetName"].str.lower().str.contains(term, na=False))
    results = df[mask]
    if not results.empty:
        for _, row in results.iterrows():
            with st.container():
                c_img, c_txt = st.columns([1, 4])
                img_url = row["ImageURL"] if pd.notna(row["ImageURL"]) else ""
                if not img_url:
                    with st.spinner(f"Buscando imagen de {row['Number']}..."):
                        api_fixed = get_rebrickable_info(row["Number"])
                        if api_fixed:
                            img_url = api_fixed.get("set_img_url","")
                            repair_image_url(row["Number"], img_url)
                with c_img:
                    st.image(img_url if img_url.startswith("http") else "https://placehold.co/150x150?text=Sin+Foto", use_container_width=True)
                with c_txt:
                    st.markdown(f"""
                        <div style='margin-left:15px;'>
                            <h3 style='margin-bottom:0;'>{row['Number']} — {row['SetName']}</h3>
                            <p style='color:grey;margin-top:0;'>📅 Año: {row['YearFrom']} &nbsp;|&nbsp; 📂 Tema: {row['Theme']}</p>
                            <p style='font-size:18px;font-weight:bold;'>
                                💰 Retail: ${row['USRetailPrice']:,.2f} USD &nbsp;|&nbsp;
                                🇨🇴 ${row['USRetailPrice']*trm_hoy:,.0f} COP
                            </p>
                        </div>
                    """, unsafe_allow_html=True)
                st.markdown("---")
    else:
        st.warning("No se encontraron resultados.")
else:
    st.write("Tu colección (primeros 10 sets):")
    st.dataframe(df[["Number","SetName","Theme","YearFrom","USRetailPrice"]].head(10), use_container_width=True)

st.markdown("---")
if not df.empty and df["USRetailPrice"].sum() > 0:
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("### Distribución por Tema (USD)")
        fig_pie = px.pie(df.groupby("Theme")["USRetailPrice"].sum().reset_index(), values="USRetailPrice", names="Theme", hole=0.4)
        fig_pie.update_layout(showlegend=False, margin=dict(t=10,b=0,l=0,r=0))
        st.plotly_chart(fig_pie, use_container_width=True)
    with g2:
        st.markdown("### Top 5 Temas por Inversión (USD)")
        df_bar = df.groupby("Theme")["USRetailPrice"].sum().sort_values(ascending=False).reset_index().head(5)
        fig_bar = px.bar(df_bar, x="USRetailPrice", y="Theme", orientation="h", color="USRetailPrice", color_continuous_scale="Blues", labels={"USRetailPrice":"USD","Theme":"Tema"})
        fig_bar.update_layout(showlegend=False, yaxis={"categoryorder":"total ascending"}, margin=dict(t=10,b=0,l=0,r=0))
        st.plotly_chart(fig_bar, use_container_width=True)

with st.expander("📂 Base de datos completa"):
    st.dataframe(df, use_container_width=True)
