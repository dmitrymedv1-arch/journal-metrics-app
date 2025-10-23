import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np
from datetime import date
import time
import os
from journal_analyzer import (
    calculate_metrics_fast, calculate_metrics_enhanced, 
    calculate_metrics_dynamic, on_clear_cache_clicked
)

# ==================== КОНФИГУРАЦИЯ ====================
st.set_page_config(
    page_title="Журнальный Анализатор ИФ/CS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CSS ====================
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
    .dynamic-mode {background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);}
    .fast-mode {background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);}
    .precise-mode {background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);}
    .stMetric > label {font-size: 1.2rem !important; color: white !important;}
    .stMetric > div > div {font-size: 2.5rem !important; color: white !important;}
</style>
""", unsafe_allow_html=True)

# ==================== SIDEBAR ====================
st.sidebar.title("🔧 НАСТРОЙКИ")
st.sidebar.markdown("---")

issn = st.sidebar.text_input("📖 ISSN", value="2411-1414")
journal_name = st.sidebar.text_input("📚 Название", value="Журнал прикладной информатики")

st.sidebar.markdown("### 🎯 РЕЖИМ")
mode = st.sidebar.radio("", 
    [("⚡ Быстрый (10-30 сек)", "fast"), 
     ("🎯 Точный (2-5 мин)", "enhanced"), 
     ("🔄 Динамический (3-6 сек)", "dynamic")],
    index=0, format_func=lambda x: x[0])

st.sidebar.markdown("---")
if st.sidebar.button("🧹 Очистить кэш"):
    result = on_clear_cache_clicked(None)
    st.sidebar.success(result)

st.sidebar.markdown("---")
st.sidebar.markdown("**xAI Grok v2.0**")

# ==================== ГЛАВНАЯ ПАНЕЛЬ ====================
st.title("📊 ЖУРНАЛЬНЫЙ АНАЛИЗАТОР")
st.markdown("**Импакт-Фактор & CiteScore в реальном времени**")

if not issn:
    st.warning("⚠️ Введите ISSN!")
    st.stop()

# ==================== РАСЧЕТ ====================
progress_bar = st.progress(0)
status_text = st.empty()

with st.spinner(f"🔄 Анализ в режиме **{mode}**..."):
    start_time = time.time()
    
    if mode == "fast":
        result = calculate_metrics_fast(issn, journal_name)
        analysis_time = f"{time.time() - start_time:.1f} сек"
        mode_class = "fast-mode"
    elif mode == "enhanced":
        result = calculate_metrics_enhanced(issn, journal_name)
        analysis_time = f"{time.time() - start_time:.1f} сек"
        mode_class = "precise-mode"
    else:
        result = calculate_metrics_dynamic(issn, journal_name)
        analysis_time = f"{time.time() - start_time:.1f} сек"
        mode_class = "dynamic-mode"

if result is None:
    st.error("❌ Ошибка анализа!")
    st.stop()

# ==================== ОСНОВНЫЕ МЕТРИКИ ====================
st.markdown(f"**⏱️ Время:** {analysis_time}")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(f"""
    <div class="metric-card {mode_class}">
        <h3>📈 ИМПАКТ-ФАКТОР</h3>
        <h1>{result['current_if']:.3f}</h1>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card {mode_class}">
        <h3>📊 CITE SCORE</h3>
        <h1>{result['current_citescore']:.3f}</h1>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card {mode_class}">
        <h3>📅 ДАТА</h3>
        <h1>{result['analysis_date'].strftime('%d.%m.%Y')}</h1>
    </div>
    """, unsafe_allow_html=True)

# ==================== ПРОГНОЗЫ ====================
st.markdown("---")
st.subheader("🔮 ПРОГНОЗЫ НА КОНЕЦ 2025")

col4, col5 = st.columns(2)

with col4:
    st.markdown("**Импакт-Фактор**")
    st.metric("Баланс", f"{result['if_forecasts']['balanced']:.3f}")

with col5:
    st.markdown("**CiteScore**")
    st.metric("Баланс", f"{result['citescore_forecasts']['balanced']:.3f}")

# ==================== ПЕРИОДЫ ====================
st.markdown("---")
st.subheader("📅 ПЕРИОДЫ АНАЛИЗА")

if mode == "dynamic" and 'mode' in result:
    col1, col2 = st.columns(2)
    
    with col1:
        art_start, art_end = result['if_details']['periods']['articles']
        cite_start, cite_end = result['if_details']['periods']['citations']
        st.markdown(f"""
        **📈 ИМПАКТ-ФАКТОР**  
        📚 Статьи: {result['total_articles_if']}  
        📅 {art_start} → {art_end}  
        🔗 Цитаты: {result['total_cites_if']}  
        📅 {cite_start} → {cite_end}
        """)
    
    with col2:
        art_start, art_end = result['cs_details']['periods']['articles']
        cite_start, cite_end = result['cs_details']['periods']['citations']
        st.markdown(f"""
        **📊 CITE SCORE**  
        📚 Статьи: {result['total_articles_cs']}  
        📅 {art_start} → {art_end}  
        🔗 Цитаты: {result['total_cites_cs']}  
        📅 {cite_start} → {cite_end}
        """)
else:
    col1, col2 = st.columns(2)
    
    with col1:
        years = result['if_publication_years']
        st.markdown(f"""
        **📈 ИМПАКТ-ФАКТОР**  
        📚 Статьи: {result['total_articles_if']}  
        📅 {years[0]} → {years[1]}  
        🔗 Цитаты: {result['total_cites_if']}  
        📅 2025-01-01 → {result['analysis_date'].strftime('%d.%m.%Y')}
        """)
    
    with col2:
        years = result['cs_publication_years']
        st.markdown(f"""
        **📊 CITE SCORE**  
        📚 Статьи: {result['total_articles_cs']}  
        📅 {years[0]} → {years[-1]}  
        🔗 Цитаты: {result['total_cites_cs']}  
        📅 {years[0]}-01-01 → {result['analysis_date'].strftime('%d.%m.%Y')}
        """)

# ==================== ВАЛИДАЦИЯ ====================
st.markdown("---")
st.subheader("✅ ВАЛИДАЦИЯ")

validation = result['validation']
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("IF Точность", validation['if_accuracy'])

with col2:
    st.metric("CS Точность", validation['cs_accuracy'])

with col3:
    st.success(f"**Уверенность:** {validation['confidence']}")

# ==================== ГРАФИКИ ====================
st.markdown("---")
st.subheader("📈 ПРОГНОЗЫ")

fig = make_subplots(rows=1, cols=2, subplot_titles=('ИФ Прогнозы', 'CS Прогнозы'))

scenarios = ['conservative', 'balanced', 'optimistic']
colors = ['#ff6b6b', '#4ecdc4', '#45b7d1']

for i, scenario in enumerate(scenarios):
    fig.add_trace(go.Bar(x=[scenario], y=[result['if_forecasts'][scenario]], 
                        marker_color=colors[i]), row=1, col=1)
    fig.add_trace(go.Bar(x=[scenario], y=[result['citescore_forecasts'][scenario]], 
                        marker_color=colors[i], showlegend=False), row=1, col=2)

fig.update_layout(height=400, showlegend=False)
st.plotly_chart(fig, use_container_width=True)

# ==================== СТАТИСТИКА ====================
st.markdown("---")
st.subheader("📋 СТАТИСТИКА")

if mode == "dynamic" and 'mode' in result:
    tab1, tab2 = st.tabs(["📈 ИФ", "📊 CS"])
    
    with tab1:
        df = pd.DataFrame(result['if_citation_data'])
        st.dataframe(df, use_container_width=True)
    
    with tab2:
        df = pd.DataFrame(result['cs_citation_data'])
        st.dataframe(df, use_container_width=True)
else:
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📈 ИФ")
        df = pd.DataFrame(result['if_citation_data'])
        st.dataframe(df, use_container_width=True)
    
    with col2:
        st.markdown("### 📊 CS")
        df = pd.DataFrame(result['cs_citation_data'])
        st.dataframe(df, use_container_width=True)

# ==================== ФУТЕР ====================
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666;'>"
    "🚀 Журнальный Анализатор v2.0 | xAI Grok | 520 строк"
    "</div>", 
    unsafe_allow_html=True
)
