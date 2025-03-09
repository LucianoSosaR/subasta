import ssl
import os
import psycopg2
import nltk
import streamlit as st
import pandas as pd
import re
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.manifold import TSNE

# ========================
# CONFIGURACIÓN INICIAL
# ========================
st.set_page_config(
    page_title="Dashboard de Subastas",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========================
# CONFIGURACIÓN SSL
# ========================
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# ========================
# CONFIGURACIÓN STOPWORDS
# ========================
try:
    from nltk.corpus import stopwords
    spanish_stopwords = stopwords.words('spanish')
except LookupError:
    nltk.download('stopwords', quiet=True)
    from nltk.corpus import stopwords
    spanish_stopwords = stopwords.words('spanish')

# ========================
# CONFIGURACIÓN CSS
# ========================
st.markdown("""
    <style>
    html, body, [class*="css"] { font-family: 'Segoe UI', Tahoma, sans-serif; }
    .title-h1 { font-size: 2.0rem !important; font-weight: 700 !important; }
    .title-h2 { font-size: 1.5rem !important; font-weight: 600 !important; }
    .title-h3 { font-size: 1.2rem !important; font-weight: 600 !important; color: #444444; }
    </style>
""", unsafe_allow_html=True)

# ========================
# CONEXIÓN A LA BASE DE DATOS
# ========================
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    st.error("❌ No se encontró la variable de entorno DATABASE_URL. Verifica la configuración en Render.")
    st.stop()

def get_db_connection():
    """Crea una conexión segura a la base de datos PostgreSQL."""
    try:
        return psycopg2.connect(DATABASE_URL, sslmode="require")
    except Exception as e:
        st.error(f"❌ Error de conexión a la base de datos: {e}")
        st.stop()

# ========================
# CARGAR DATOS DESDE LA DB
# ========================
@st.cache_data(ttl=300)
def load_data():
    conn = get_db_connection()
    df_ = pd.read_sql_query("SELECT * FROM subastas", conn)
    conn.close()

    if 'timestamp' in df_.columns:
        df_['timestamp'] = pd.to_datetime(df_['timestamp'], errors='coerce')
    else:
        df_['timestamp'] = None

    # Convertir la columna 'precio' a valores numéricos
    df_['precio_num'] = df_['precio'].apply(lambda x: int(re.sub("[^0-9]", "", x)) if isinstance(x, str) else None)
    return df_

@st.cache_data(ttl=300)
def load_historial():
    conn = get_db_connection()
    df_hist_ = pd.read_sql_query("SELECT * FROM historial_subastas", conn)
    conn.close()

    if 'timestamp' in df_hist_.columns:
        df_hist_['timestamp'] = pd.to_datetime(df_hist_['timestamp'], errors='coerce')
    else:
        df_hist_['timestamp'] = None

    df_hist_['precio_num'] = df_hist_['precio'].apply(lambda x: int(re.sub("[^0-9]", "", x)) if isinstance(x, str) else None)
    return df_hist_

# ========================
# CARGAR DATOS
# ========================
with st.spinner("Cargando datos..."):
    df = load_data()
    df_hist = load_historial()

# ========================
# INTERFAZ DEL DASHBOARD
# ========================
tabs = st.tabs(["Inicio", "Datos & Análisis", "Historial", "Clustering", "Predicciones"])

# ======= TAB: INICIO =======
with tabs[0]:
    st.markdown("<h2 class='title-h2'>Datos Actuales</h2>", unsafe_allow_html=True)
    st.dataframe(df)

# ======= TAB: ANÁLISIS =======
with tabs[1]:
    st.markdown("<h2 class='title-h2'>Análisis de Datos Actuales</h2>", unsafe_allow_html=True)

    # DISTRIBUCIÓN DE PRECIOS
    st.markdown("<h3 class='title-h3'>1. Distribución de Precios</h3>", unsafe_allow_html=True)
    if df['precio_num'].notnull().sum() > 0:
        fig_hist = px.histogram(df, x="precio_num", nbins=30, title="Distribución de Precios")
        st.plotly_chart(fig_hist, use_container_width=True)

# ======= TAB: HISTORIAL =======
with tabs[2]:
    st.markdown("<h2 class='title-h2'>Historial de Actualizaciones</h2>", unsafe_allow_html=True)
    article_options = df_hist['enlace'].unique()
    selected_article = st.selectbox("Selecciona un artículo", article_options)
    article_hist = df_hist[df_hist['enlace'] == selected_article].sort_values(by="timestamp")
    st.dataframe(article_hist)

# ======= TAB: CLUSTERING =======
with tabs[3]:
    st.markdown("<h2 class='title-h2'>Clustering de Artículos</h2>", unsafe_allow_html=True)

    df_clust = df.copy()
    df_clust["descripcion"].fillna("", inplace=True)

    # Vectorización y reducción de dimensionalidad
    vectorizer = TfidfVectorizer(stop_words=spanish_stopwords, max_features=1000)
    X_text = vectorizer.fit_transform(df_clust["descripcion"])
    svd = TruncatedSVD(n_components=50, random_state=42)
    X_text_reduced = svd.fit_transform(X_text)

    # Características numéricas
    X_numeric = df_clust[["precio_num", "ofertas"]].fillna(0)
    scaler = StandardScaler()
    X_numeric_scaled = scaler.fit_transform(X_numeric)

    # Combinar características
    X_combined = np.hstack((X_text_reduced, X_numeric_scaled))
    kmeans = KMeans(n_clusters=4, random_state=42, n_init="auto")
    df_clust["cluster"] = kmeans.fit_predict(X_combined)

    # Visualización con t-SNE
    tsne = TSNE(n_components=2, random_state=42)
    X_embedded = tsne.fit_transform(X_combined)
    df_clust["tsne_1"] = X_embedded[:, 0]
    df_clust["tsne_2"] = X_embedded[:, 1]

    fig_cluster = px.scatter(df_clust, x="tsne_1", y="tsne_2", color="cluster",
                             hover_data=["lote", "descripcion", "precio", "ofertas"],
                             title="Clusters de Artículos")
    st.plotly_chart(fig_cluster, use_container_width=True)

# ======= TAB: PREDICCIONES =======
with tabs[4]:
    st.markdown("<h2 class='title-h2'>Predicciones</h2>", unsafe_allow_html=True)
    st.write("Esta sección estará dedicada a modelos de predicción en futuras versiones.")

# ========================
# BOTÓN DE REFRESCO
# ========================
st.sidebar.header("Opciones")
if st.sidebar.button("Refrescar Datos"):
    st.rerun()
