"""
Lego Vault OS Pro — versión corregida y lista para producción
Correcciones aplicadas:
  1. Bug crítico: variable 'resultados' → 'results' en el buscador
  2. API key movida a st.secrets / variable de entorno
  3. Labels de métricas corregidos (sin duplicados)
  4. ALTER TABLE movido a función de inicialización separada
  5. Conexiones SQLite protegidas con context manager (with)
  6. row.get() reemplazado por acceso seguro con pandas
  7. Títulos de gráficas legibles
  8. init_db() crea la tabla si no existe (app corre desde cero)
"""

import streamlit as st
import pandas as pd
import sqlite3
import requests
import plotly.express as px
import os

# ──────────────────────────────────────────────
# 1. CONFIGURACIÓN DE PÁGINA
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Lego Vault OS Pro",
    layout="centered",
    page_icon="🧱",
)

# ──────────────────────────────────────────────
# 2. CREDENCIALES (seguras)
# ──────────────────────────────────────────────
# FIX: la API key ya NO está hardcodeada en el código.
# Colócala en .streamlit/secrets.toml:
#   REBRICKABLE_API_KEY = "tu_clave_aqui"
# O como variable de entorno: REBRICKABLE_API_KEY=...
def get_api_key() -> str:
    try:
        return st.secrets["REBRICKABLE_API_KEY"]
    except Exception:
        return os.getenv("REBRICKABLE_API_KEY", "")

API_KEY = get_api_key()
DB_PATH = os.getenv("LEGO_DB_PATH", "lego.db")

# ──────────────────────────────────────────────
# 3. INICIALIZACIÓN DE BASE DE DATOS
# FIX: ALTER TABLE separado de load_data();
#      tabla creada si no existe (primer arranque)
# ──────────────────────────────────────────────
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sets (
                Number          TEXT PRIMARY KEY,
                SetName         TEXT,
                YearFrom        INTEGER,
                Theme           TEXT,
                USRetailPrice   REAL DEFAULT 0,
                BrickLinkSoldPriceNew REAL DEFAULT 0,
                ImageURL        TEXT
            )
        """)
        # Agrega columna ImageURL solo si no existe todavía
        existing = [row[1] for row in conn.execute("PRAGMA table_info(sets)")]
        if "ImageURL" not in existing:
            conn.execute("ALTER TABLE sets ADD COLUMN ImageURL TEXT")
        conn.commit()

init_db()

# ──────────────────────────────────────────────
# 4. FUNCIONES DE DATOS
# ──────────────────────────────────────────────
@st.cache_data(ttl=3600)
def get_trm_colombia() -> float:
    url = (
        "https://www.datos.gov.co/resource/m97v-v6y7.json"
        "?$order=vigenciadesde DESC&$limit=1"
    )
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return float(resp.json()[0]["valor"])
    except Exception:
        pass
    return 3950.0  # Valor de respaldo


def get_rebrickable_info(set_num: str) -> dict | None:
    clean_num = str(set_num).split("-")[0]
    url = f"https://rebrickable.com/api/v3/lego/sets/{clean_num}-1/"
    headers = {"Authorization": f"key {API_KEY}"}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        return resp.json() if resp.status_code == 200 else None
    except Exception:
        return None


@st.cache_data(ttl=300)
def load_data() -> pd.DataFrame:
    # FIX: solo lectura — ALTER TABLE ya no está aquí
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql("SELECT * FROM sets", conn)
    df["USRetailPrice"] = pd.to_numeric(df["USRetailPrice"], errors="coerce").fillna(0)
    df["BrickLinkSoldPriceNew"] = pd.to_numeric(
        df["BrickLinkSoldPriceNew"], errors="coerce"
    ).fillna(0)
    return df


def save_new_set(api_data: dict):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT OR IGNORE INTO sets
               (Number, SetName, YearFrom, Theme, USRetailPrice, ImageURL)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                api_data["set_num"],
                api_data["name"],
                api_data["year"],
                "Nuevo Ingreso",
                0,
                api_data.get("set_img_url", ""),
            ),
        )
        conn.commit()


def repair_image_url(number: str, img_url: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE sets SET ImageURL = ? WHERE Number = ?",
            (img_url, number),
        )
        conn.commit()


# ──────────────────────────────────────────────
# 5. CSS
# ──────────────────────────────────────────────
st.markdown(
    """
    <style>
        .stApp { background-color: white; }

        [data-testid="stSidebar"] {
            background-color: #1e2030;
            color: white;
        }
        [data-testid="stSidebar"] * { color: white !important; }

        div[data-testid="metric-container"] {
            background-color: #f0f2f6;
            border: 1px solid #e0e3eb;
            padding: 15px;
            border-radius: 10px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────
# 6. DATOS GLOBALES
# ──────────────────────────────────────────────
df = load_data()
trm_hoy = get_trm_colombia()

# ──────────────────────────────────────────────
# 7. BARRA LATERAL
# ──────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div style='display:flex;align-items:center;gap:10px;margin-bottom:5px;'>
            <span style='font-size:25px;'>🧱</span>
            <h1 style='margin:0;font-size:22px;'>Lego Vault OS Pro</h1>
        </div>
        <p style='color:#a3a8b4;font-size:14px;margin-bottom:20px;'>
            Colección personal · Medellín, Colombia
        </p>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"**TRM Oficial Hoy:**<br>"
        f"<span style='font-size:20px;'>${trm_hoy:,.0f} COP</span>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    st.markdown("**Agregar set por número**")
    new_set_input = st.text_input(
        "", placeholder="Ej: 10305", label_visibility="collapsed"
    )

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

    # Imagen decorativa opcional
    st.markdown("<br>" * 6, unsafe_allow_html=True)
    if os.path.exists("explorer.png"):
        st.image("explorer.png", use_container_width=True)

# ──────────────────────────────────────────────
# 8. DASHBOARD PRINCIPAL
# ──────────────────────────────────────────────
st.title("📊 Métricas")
st.caption(f"Datos en tiempo real | TRM: ${trm_hoy:,.0f} COP/USD")

total_inv_usd  = df["USRetailPrice"].sum()
total_mkt_usd  = df["BrickLinkSoldPriceNew"].sum()
total_mkt_cop  = total_mkt_usd * trm_hoy
roi = ((total_mkt_usd - total_inv_usd) / total_inv_usd * 100) if total_inv_usd > 0 else 0

# FIX: labels únicos y correctos en las 4 métricas
m1, m2, m3, m4 = st.columns(4)
with m1: st.metric("Inversión (USD)",        f"${total_inv_usd:,.2f}")
with m2: st.metric("Valor Mercado (USD)",    f"${total_mkt_usd:,.2f}")
with m3: st.metric("Valor Mercado (COP)",    f"${total_mkt_cop / 1_000_000:.2f}M")
with m4: st.metric("ROI",                   f"{roi:.1f}%")

st.markdown("---")

# ──────────────────────────────────────────────
# 9. BUSCADOR
# FIX: variable unificada como 'results' en todo el bloque
# ──────────────────────────────────────────────
st.subheader("🔍 Inventario local")
search = st.text_input(
    "Busca por nombre o número en tu colección:",
    placeholder="Ej: Millennium Falcon",
)

if search:
    term = search.strip().lower()
    mask = df["Number"].astype(str).str.lower().str.contains(term) | \
           df["SetName"].str.lower().str.contains(term, na=False)
    results = df[mask]   # ← FIX: definida y usada con el mismo nombre

    if not results.empty:
        for _, row in results.iterrows():
            with st.container():
                c_img, c_txt = st.columns([1, 4])

                # FIX: acceso seguro a ImageURL con pandas (no .get())
                img_url = row["ImageURL"] if pd.notna(row["ImageURL"]) else ""

                if not img_url:
                    with st.spinner(f"Buscando imagen de {row['Number']}..."):
                        api_fixed = get_rebrickable_info(row["Number"])
                        if api_fixed:
                            img_url = api_fixed.get("set_img_url", "")
                            repair_image_url(row["Number"], img_url)

                with c_img:
                    if img_url.startswith("http"):
                        st.image(img_url, use_container_width=True)
                    else:
                        st.image(
                            "https://placehold.co/150x150?text=Sin+Foto",
                            use_container_width=True,
                        )

                with c_txt:
                    st.markdown(
                        f"""
                        <div style='margin-left:15px;'>
                            <h3 style='margin-bottom:0;'>
                                {row['Number']} — {row['SetName']}
                            </h3>
                            <p style='color:grey;margin-top:0;'>
                                📅 Año: {row['YearFrom']} &nbsp;|&nbsp; 📂 Tema: {row['Theme']}
                            </p>
                            <p style='font-size:18px;font-weight:bold;'>
                                💰 Retail: ${row['USRetailPrice']:,.2f} USD &nbsp;|&nbsp;
                                🇨🇴 ${row['USRetailPrice'] * trm_hoy:,.0f} COP
                            </p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                st.markdown("---")
    else:
        st.warning("No se encontraron resultados para esa búsqueda.")

else:
    st.write("Tu colección (primeros 10 sets):")
    st.dataframe(
        df[["Number", "SetName", "Theme", "YearFrom", "USRetailPrice"]].head(10),
        use_container_width=True,
    )

# ──────────────────────────────────────────────
# 10. GRÁFICAS
# FIX: títulos legibles
# ──────────────────────────────────────────────
st.markdown("---")
if not df.empty and df["USRetailPrice"].sum() > 0:
    g1, g2 = st.columns(2)

    with g1:
        st.markdown("### Distribución por Tema (USD)")
        fig_pie = px.pie(
            df.groupby("Theme")["USRetailPrice"].sum().reset_index(),
            values="USRetailPrice",
            names="Theme",
            hole=0.4,
        )
        fig_pie.update_layout(
            showlegend=False,
            margin=dict(t=10, b=0, l=0, r=0),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with g2:
        st.markdown("### Top 5 Temas por Inversión (USD)")
        df_bar = (
            df.groupby("Theme")["USRetailPrice"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
            .head(5)
        )
        fig_bar = px.bar(
            df_bar,
            x="USRetailPrice",
            y="Theme",
            orientation="h",
            color="USRetailPrice",
            color_continuous_scale="Blues",
            labels={"USRetailPrice": "USD", "Theme": "Tema"},
        )
        fig_bar.update_layout(
            showlegend=False,
            yaxis={"categoryorder": "total ascending"},
            margin=dict(t=10, b=0, l=0, r=0),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

with st.expander("📂 Base de datos completa"):
    st.dataframe(df, use_container_width=True)
