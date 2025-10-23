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

# ==================== КОНФИГУРАЦИЯ СТРАНИЦЫ ====================
st.set_page_config(
    page_title="Журнальный Анализатор ИФ/CS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CSS СТИЛИ ====================
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
    .dynamic-mode {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        border: 2px solid #38ef7d;
    }
    .fast-mode {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    }
    .precise-mode {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    }
    .stMetric > label {
        font-size: 1.2rem !important;
        color: white !important;
    }
    .stMetric > div > div {
        font-size: 2.5rem !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# ==================== SIDEBAR ====================
st.sidebar.title("🔧 НАСТРОЙКИ")
st.sidebar.markdown("---")

# ISSN ВВОД
issn = st.sidebar.text_input(
    "📖 ISSN журнала", 
    value="2411-1414",
    help="Введите ISSN в формате: 2411-1414"
)

# НАЗВАНИЕ ЖУРНАЛА
journal_name = st.sidebar.text_input(
    "📚 Название журнала", 
    value="Журнал прикладной информатики",
    help="Для точного определения области"
)

# РЕЖИМ АНАЛИЗА
st.sidebar.markdown("### 🎯 РЕЖИМ АНАЛИЗА")
mode = st.sidebar.radio(
    "Выберите режим:",
    [
        ("⚡ Быстрый анализ (10-30 сек)", "fast"),
        ("🎯 Точный анализ (2-5 мин)", "enhanced"), 
        ("🔄 Динамический анализ (3-6 сек)", "dynamic")
    ],
    index=0,
    format_func=lambda x: x[0]
)

# КЭШ
st.sidebar.markdown("---")
if st.sidebar.button("🧹 Очистить кэш"):
    result = on_clear_cache_clicked(None)
    st.sidebar.success(result)

st.sidebar.markdown("---")
st.sidebar.markdown("**Автор:** xAI Grok")
st.sidebar.markdown("**Версия:** 2.0 (1090 строк)")

# ==================== ГЛАВНАЯ ПАНЕЛЬ ====================
st.title("📊 ЖУРНАЛЬНЫЙ АНАЛИЗATOR")
st.markdown("**Импакт-Фактор & CiteScore в реальном времени**")

# ПРОВЕРКА ВВОДА
if not issn:
    st.warning("⚠️ Введите ISSN журнала!")
    st.stop()

# ==================== АНИМАЦИЯ ЗАГРУЗКИ ====================
progress_bar = st.progress(0)
status_text = st.empty()

# ==================== РАСЧЕТ ====================
with st.spinner(f"🔄 Анализ в режиме **{mode}**..."):
    start_time = time.time()
    
    if mode == "fast":
        result = calculate_metrics_fast(issn, journal_name, use_cache=True)
        analysis_time = f"{time.time() - start_time:.1f} сек"
        mode_class = "fast-mode"
        
    elif mode == "enhanced":
        result = calculate_metrics_enhanced(issn, journal_name, use_cache=True)
        analysis_time = f"{time.time() - start_time:.1f} сек"
        mode_class = "precise-mode"
        
    else:  # dynamic
        result = calculate_metrics_dynamic(issn, journal_name, use_cache=True)
        analysis_time = f"{time.time() - start_time:.1f} сек"
        mode_class = "dynamic-mode"

# ==================== ОШИБКА ====================
if result is None:
    st.error("❌ Ошибка анализа! Проверьте ISSN.")
    st.stop()

# ==================== ОСНОВНЫЕ МЕТРИКИ ====================
st.markdown(f"**⏱️ Время анализа:** {analysis_time}")

col1, col2, col3 = st.columns([1, 1, 1])

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
    if_forecast = result['if_forecasts']['balanced']
    st.metric("Баланс", f"{if_forecast:.3f}", 
              delta=f"{result['if_forecasts']['optimistic']:.3f}")

with col5:
    st.markdown("**CiteScore**")
    cs_forecast = result['citescore_forecasts']['balanced']
    st.metric("Баланс", f"{cs_forecast:.3f}", 
              delta=f"{result['citescore_forecasts']['optimistic']:.3f}")

# ==================== ПЕРИОДЫ АНАЛИЗА ====================
st.markdown("---")
display_periods(result, mode)

# ==================== ВАЛИДАЦИЯ ====================
display_validation(result)

# ==================== ГРАФИКИ ====================
st.markdown("---")
display_charts(result, mode)

# ==================== СТАТИСТИКА ====================
st.markdown("---")
display_statistics(result, mode)

# ==================== ФУНКЦИИ ОТОБРАЖЕНИЯ ====================

def display_periods(result, mode):
    """ОТОБРАЖЕНИЕ ПЕРИОДОВ"""
    st.subheader("📅 ПЕРИОДЫ АНАЛИЗА")
    
    if mode == "dynamic":
        # ДИНАМИЧЕСКИЙ
        if_details = result['if_details']
        cs_details = result['cs_details']
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            <div style="background:#e8f5e8; padding:1rem; border-radius:10px; border-left:5px solid #4caf50;">
                <h4>📈 ИМПАКТ-ФАКТОР</h4>
            </div>
            """, unsafe_allow_html=True)
            
            art_start, art_end = if_details['periods']['articles']
            cite_start, cite_end = if_details['periods']['citations']
            
            st.markdown(f"""
            **📚 Статьи:** {if_details['articles_count']}<br>
            **📅 {art_start} → {art_end}**<br><br>
            
            **🔗 Цитирования:** {if_details['citations_count']}<br>
            **📅 {cite_start} → {cite_end}**
            """)
        
        with col2:
            st.markdown("""
            <div style="background:#e8f5e8; padding:1rem; border-radius:10px; border-left:5px solid #4caf50;">
                <h4>📊 CITE SCORE</h4>
            </div>
            """, unsafe_allow_html=True)
            
            art_start, art_end = cs_details['periods']['articles']
            cite_start, cite_end = cs_details['periods']['citations']
            
            st.markdown(f"""
            **📚 Статьи:** {cs_details['articles_count']}<br>
            **📅 {art_start} → {art_end}**<br><br>
            
            **🔗 Цитирования:** {cs_details['citations_count']}<br>
            **📅 {cite_start} → {cite_end}**
            """)
            
    else:
        # БЫСТРЫЙ/ТОЧНЫЙ
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            <div style="background:#fff3cd; padding:1rem; border-radius:10px; border-left:5px solid #ffc107;">
                <h4>📈 ИМПАКТ-ФАКТОР</h4>
            </div>
            """, unsafe_allow_html=True)
            
            years = result['if_publication_years']
            st.markdown(f"""
            **📚 Статьи:** {result['total_articles_if']}<br>
            **📅 {years[0]} → {years[1]}**<br><br>
            
            **🔗 Цитирования:** {result['total_cites_if']}<br>
            **📅 2025-01-01 → {result['analysis_date'].strftime('%d.%m.%Y')}**
            """)
        
        with col2:
            st.markdown("""
            <div style="background:#fff3cd; padding:1rem; border-radius:10px; border-left:5px solid #ffc107;">
                <h4>📊 CITE SCORE</h4>
            </div>
            """, unsafe_allow_html=True)
            
            years = result['cs_publication_years']
            st.markdown(f"""
            **📚 Статьи:** {result['total_articles_cs']}<br>
            **📅 {years[0]} → {years[-1]}**<br><br>
            
            **🔗 Цитирования:** {result['total_cites_cs']}<br>
            **📅 {years[0]}-01-01 → {result['analysis_date'].strftime('%d.%m.%Y')}**
            """)

def display_validation(result):
    """ОТОБРАЖЕНИЕ ВАЛИДАЦИИ"""
    st.subheader("✅ ВАЛИДАЦИЯ")
    
    validation = result['validation']
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("IF Точность", validation['if_accuracy'])
    
    with col2:
        st.metric("CS Точность", validation['cs_accuracy'])
    
    with col3:
        st.success(f"**Уверенность:** {validation['confidence']}")

def display_charts(result, mode):
    """ГРАФИКИ"""
    st.subheader("📈 ВИЗУАЛИЗАЦИЯ")
    
    # ПРОГНОЗЫ
    fig_forecast = make_subplots(
        rows=1, cols=2,
        subplot_titles=('ИФ Прогнозы', 'CS Прогнозы'),
        specs=[[{"type": "bar"}, {"type": "bar"}]]
    )
    
    scenarios = ['conservative', 'balanced', 'optimistic']
    colors = ['#ff6b6b', '#4ecdc4', '#45b7d1']
    
    # ИФ
    for i, scenario in enumerate(scenarios):
        fig_forecast.add_trace(
            go.Bar(x=[scenario], y=[result['if_forecasts'][scenario]],
                   name=scenario, marker_color=colors[i]),
            row=1, col=1
        )
    
    # CS
    for i, scenario in enumerate(scenarios):
        fig_forecast.add_trace(
            go.Bar(x=[scenario], y=[result['citescore_forecasts'][scenario]],
                   name=scenario, marker_color=colors[i], showlegend=False),
            row=1, col=2
        )
    
    fig_forecast.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig_forecast, use_container_width=True)
    
    # РАСПРЕДЕЛЕНИЕ СЕЗОННОСТИ
    if mode != "dynamic":
        fig_seasonal = go.Figure()
        months = list(range(1, 13))
        coeffs = list(result['seasonal_coefficients'].values())
        
        fig_seasonal.add_trace(go.Scatter(
            x=months, y=coeffs, mode='lines+markers',
            name='Сезонные коэффициенты'
        ))
        
        fig_seasonal.update_layout(
            title="📊 Сезонное распределение публикаций",
            xaxis_title="Месяц", yaxis_title="Коэффициент"
        )
        st.plotly_chart(fig_seasonal, use_container_width=True)

def display_statistics(result, mode):
    """ПОЛНАЯ СТАТИСТИКА"""
    st.subheader("📋 ПОДРОБНАЯ СТАТИСТИКА")
    
    if mode == "dynamic":
        # ДИНАМИЧЕСКИЙ - ОТДЕЛЬНЫЕ ТАБЫ
        tab1, tab2 = st.tabs(["📈 Импакт-Фактор", "📊 CiteScore"])
        
        with tab1:
            df_if = pd.DataFrame(result['if_citation_data'])
            if not df_if.empty:
                st.dataframe(df_if, use_container_width=True, height=400)
            else:
                st.info("Нет данных для отображения")
        
        with tab2:
            df_cs = pd.DataFrame(result['cs_citation_data'])
            if not df_cs.empty:
                st.dataframe(df_cs, use_container_width=True, height=400)
            else:
                st.info("Нет данных для отображения")
                
    else:
        # БЫСТРЫЙ/ТОЧНЫЙ - КОЛОНКИ
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📈 Импакт-Фактор")
            df_if = pd.DataFrame(result['if_citation_data'])
            if not df_if.empty:
                st.dataframe(df_if, use_container_width=True, height=400)
            else:
                st.info("Нет данных для ИФ")
        
        with col2:
            st.markdown("### 📊 CiteScore")
            df_cs = pd.DataFrame(result['cs_citation_data'])
            if not df_cs.empty:
                st.dataframe(df_cs, use_container_width=True, height=400)
            else:
                st.info("Нет данных для CS")

# ==================== ФУ터 ====================
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666; padding: 1rem;'>"
    "🚀 Журнальный Анализатор v2.0 | xAI Grok | 1090 строк кода"
    "</div>", 
    unsafe_allow_html=True
)
