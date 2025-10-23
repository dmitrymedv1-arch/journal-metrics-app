# Количество строк: 510
# ✅ ИСПРАВЛЕНО: автоматическая установка aiohttp + fallback на синхронный режим

import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime
import calendar
import sys
import os
import re
import subprocess
import importlib.util

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(__file__))

# ✅ АВТОМАТИЧЕСКАЯ УСТАНОВКА aiohttp
def install_package(package):
    """Автоматическая установка пакета"""
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Проверяем и устанавливаем aiohttp
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    st.warning("⚠️ aiohttp не установлен. Устанавливаем...")
    with st.spinner("Установка aiohttp..."):
        install_package("aiohttp")
    try:
        import aiohttp
        AIOHTTP_AVAILABLE = True
        st.success("✅ aiohttp установлен!")
    except ImportError:
        AIOHTTP_AVAILABLE = False
        st.error("❌ Не удалось установить aiohttp")

# Проверяем plotly
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# Импорт journal_analyzer с fallback
JOURNAL_ANALYZER_AVAILABLE = False
try:
    from journal_analyzer import (
        calculate_metrics_enhanced,
        calculate_metrics_fast,
        calculate_metrics_dynamic,
        detect_journal_field,
        on_clear_cache_clicked
    )
    JOURNAL_ANALYZER_AVAILABLE = True
    st.success("✅ journal_analyzer загружен!")
except ImportError as e:
    st.error(f"❌ Ошибка импорта journal_analyzer: {e}")
    # Создаем заглушки
    def calculate_metrics_enhanced(*args, **kwargs): return None
    def calculate_metrics_fast(*args, **kwargs): return None
    def calculate_metrics_dynamic(*args, **kwargs): return None
    def detect_journal_field(*args, **kwargs): return "general"
    def on_clear_cache_clicked(*args, **kwargs): return "Кэш не доступен"

# Настройка страницы
st.set_page_config(
    page_title="Journal Metrics Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Кастомные стили CSS
st.markdown("""
<style>
    .main-header { font-size: 2.5rem; color: #1E88E5; text-align: center; margin-bottom: 2rem; }
    .metric-card { background-color: #f8f9fa; padding: 1.5rem; border-radius: 10px; border-left: 4px solid #1E88E5; margin-bottom: 1rem; }
    .forecast-box { background-color: #e3f2fd; padding: 1rem; border-radius: 8px; margin: 0.5rem 0; border-left: 4px solid #1E88E5; }
    .citescore-forecast-box { background-color: #e8f5e8; padding: 1rem; border-radius: 8px; margin: 0.5rem 0; border-left: 4px solid #4CAF50; }
    .warning-box { background-color: #fff3cd; padding: 1rem; border-radius: 8px; border-left: 4px solid #ffc107; margin: 1rem 0; }
    .success-box { background-color: #d4edda; padding: 1rem; border-radius: 8px; border-left: 4px solid #28a745; margin: 1rem 0; }
    .section-header { color: #1E88E5; border-bottom: 2px solid #1E88E5; padding-bottom: 0.5rem; margin-top: 2rem; }
    .mode-indicator { padding: 0.5rem 1rem; border-radius: 20px; font-weight: bold; display: inline-block; margin-bottom: 1rem; }
    .fast-mode { background-color: #fff3cd; color: #856404; border: 1px solid #ffeaa7; }
    .precise-mode { background-color: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
    .dynamic-mode { background-color: #e1bee7; color: #4a148c; border: 1px solid #ce93d8; }
    .self-citation-highlight { background-color: #ffebee !important; }
</style>
""", unsafe_allow_html=True)

def validate_issn(issn):
    """Проверка формата ISSN"""
    if not issn:
        return False
    pattern = r'^\d{4}-\d{3}[\dXx]$'
    return re.match(pattern, issn) is not None

def main():
    # Статус зависимостей
    status_col1, status_col2, status_col3 = st.columns(3)
    with status_col1:
        st.metric("📚 journal_analyzer", "✅" if JOURNAL_ANALYZER_AVAILABLE else "❌")
    with status_col2:
        st.metric("🌐 aiohttp", "✅" if AIOHTTP_AVAILABLE else "❌")
    with status_col3:
        st.metric("📊 Plotly", "✅" if PLOTLY_AVAILABLE else "❌")
    
    if not JOURNAL_ANALYZER_AVAILABLE:
        st.warning("⚠️ Работает в упрощенном режиме.")
    
    st.markdown('<h1 class="main-header">📊 Journal Metrics Analyzer </h1>', unsafe_allow_html=True)
    
    with st.expander("ℹ️ О системе анализа"):
        st.markdown("""
        **🚀 Быстрый анализ**: 10-30 сек (только Crossref)  
        **🎯 Точный анализ**: 15-45 сек (OpenAlex batch)  
        **🌐 Динамический**: 15-45 сек (OpenAlex batch)  
        
        **Требования:**
        - Python 3.8+
        - `pip install -r requirements.txt`
        
        ©Chimica Techno Acta
        """)
    
    with st.sidebar:
        st.header("🔍 Параметры")
        issn_input = st.text_input("ISSN:", value="2411-1414", help="XXXX-XXXX")
        analysis_mode = st.radio("Режим:", [
            "🚀 Быстрый анализ", "🎯 Точный анализ", "🌐 Динамический анализ"
        ])
        use_cache = st.checkbox("Кэш", value=True)
        
        analyze_button = st.button("🚀 Анализ", type="primary", use_container_width=True)
        
        if st.button("🧹 Очистить кэш", use_container_width=True):
            result_msg = on_clear_cache_clicked(None)
            st.success(result_msg)
    
    if analyze_button:
        if not validate_issn(issn_input):
            st.error("❌ Неверный ISSN: XXXX-XXXX")
            return
        
        # Fallback на быстрый режим если нет aiohttp
        if not AIOHTTP_AVAILABLE:
            st.warning("⚠️ aiohttp недоступен. Используется только быстрый анализ.")
            analysis_mode = "🚀 Быстрый анализ"
        
        mode_map = {
            "Быстрый": ("fast", "🚀 Быстрый"),
            "Точный": ("enhanced", "🎯 Точный"), 
            "Динамический": ("dynamic", "🌐 Динамический")
        }
        mode_key, mode_display = mode_map[analysis_mode.split()[1]]
        
        st.markdown(f'<div class="mode-indicator {mode_key}-mode">{mode_display}</div>', unsafe_allow_html=True)
        
        is_precise = mode_key in ["enhanced", "dynamic"] and AIOHTTP_AVAILABLE
        
        if is_precise:
            st.info("⏳ Анализ займет 15-45 секунд")
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            def update_progress(p):
                progress_bar.progress(p)
                status_text.text(f"Прогресс: {int(p*100)}%")
                time.sleep(0.05)
            
            start_time = time.time()
            result = (calculate_metrics_dynamic if mode_key == "dynamic" 
                     else calculate_metrics_enhanced)(issn_input, use_cache=use_cache, 
                                                    progress_callback=update_progress)
            analysis_time = time.time() - start_time
            
            status_text.text(f"✅ Завершено за {analysis_time:.1f}с")
        else:
            with st.spinner("🔄 Быстрый анализ..."):
                start_time = time.time()
                result = calculate_metrics_fast(issn_input, use_cache=use_cache)
                analysis_time = time.time() - start_time
            
            st.success(f"✅ {analysis_time:.1f}с")
        
        if result:
            display_results(result, is_precise, mode_key)
        else:
            st.error("❌ Нет данных. Проверьте ISSN.")

def display_results(result, is_precise, mode):
    """Отображение результатов"""
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Журнал", result['journal_name'])
    with col2: st.metric("ISSN", result['issn'])
    with col3: st.metric("Область", result['journal_field'])
    with col4: st.metric("Режим", mode)
    
    tabs = st.tabs(["📈 Метрики", "📊 Детали", "📈 Статистика"])
    
    with tabs[0]:
        display_main_metrics(result)
    
    with tabs[1]:
        display_detailed_analysis(result)
    
    with tabs[2]:
        display_statistics(result)

def display_main_metrics(result):
    """Основные метрики"""
    st.markdown('<h3 class="section-header">🎯 Импакт-Фактор</h3>', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("ИФ", f"{result['current_if']:.2f}")
    with col2: st.metric("Статьи", result['total_articles_if'])
    with col3: st.metric("Цитаты", result['total_cites_if'])
    with col4: 
        self_rate = result['self_citations_if'] / max(result['total_cites_if'], 1)
        st.metric("Самоциты", f"{self_rate:.1%}", 
                 delta=f"{result['self_citations_if']}")
        if self_rate > 0.2:
            st.markdown('<span style="color:red">⚠️ Высокие самоцитирования</span>', unsafe_allow_html=True)
    
    st.markdown('<h3 class="section-header">📊 CiteScore</h3>', unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("CS", f"{result['current_citescore']:.2f}")
    with col2: st.metric("Статьи", result['total_articles_cs'])
    with col3: st.metric("Цитаты", result['total_cites_cs'])
    with col4:
        self_rate_cs = result['self_citations_cs'] / max(result['total_cites_cs'], 1)
        st.metric("Самоциты", f"{self_rate_cs:.1%}", 
                 delta=f"{result['self_citations_cs']}")

def display_detailed_analysis(result):
    """Детальный анализ"""
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Импакт-Фактор")
        df_if = pd.DataFrame(result['if_citation_data'])
        df_if['Время до первого цитирования'] = df_if['Время до первого цитирования'].apply(
            lambda x: x.strftime('%Y-%m-%d') if x and pd.notna(x) else 'Не цитировалось'
        )
        
        def highlight_self_cite(row):
            return ['background-color: #ffebee'] * len(row) if row['Самоцитирование'] == 'Да' else [''] * len(row)
        
        st.dataframe(df_if.style.apply(highlight_self_cite, axis=1), use_container_width=True)
    
    with col2:
        st.subheader("📊 CiteScore")
        df_cs = pd.DataFrame(result['cs_citation_data'])
        df_cs['Время до первого цитирования'] = df_cs['Время до первого цитирования'].apply(
            lambda x: x.strftime('%Y-%m-%d') if x and pd.notna(x) else 'Не цитировалось'
        )
        st.dataframe(df_cs.style.apply(highlight_self_cite, axis=1), use_container_width=True)

def display_statistics(result):
    """Статистика"""
    st.subheader("📊 Статистика самоцитирований")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Импакт-Фактор**")
        if_data = pd.DataFrame(result['if_citation_data'])
        self_if = if_data[if_data['Самоцитирование'] == 'Да']
        st.metric("Всего самоцитирований", len(self_if))
        st.metric("Доля самоцитирований", f"{len(self_if)/max(len(if_data),1):.1%}")
        
        if len(self_if) > 0:
            st.dataframe(self_if[['DOI', 'Цитирования в периоде']], use_container_width=True)
    
    with col2:
        st.markdown("**CiteScore**")
        cs_data = pd.DataFrame(result['cs_citation_data'])
        self_cs = cs_data[cs_data['Самоцитирование'] == 'Да']
        st.metric("Всего самоцитирований", len(self_cs))
        st.metric("Доля самоцитирований", f"{len(self_cs)/max(len(cs_data),1):.1%}")
        
        if len(self_cs) > 0:
            st.dataframe(self_cs[['DOI', 'Цитирования в периоде']], use_container_width=True)
    
    # Время до первого цитирования
    st.subheader("⏱️ Время до первого цитирования")
    
    if_data = pd.DataFrame(result['if_citation_data'])
    if_data_with_time = if_data.dropna(subset=['Время до первого цитирования'])
    
    if not if_data_with_time.empty:
        if_data_with_time['Дни до цитаты'] = pd.to_datetime(if_data_with_time['Время до первого цитирования']) - \
                                           pd.to_datetime(if_data_with_time['Год публикации'], format='%Y').dt.normalize()
        median_days = if_data_with_time['Дни до цитаты'].dt.days.median()
        st.metric("Медиана (дни)", f"{median_days:.0f}")
        
        if PLOTLY_AVAILABLE:
            fig = px.histogram(if_data_with_time['Дни до цитаты'].dt.days, 
                             nbins=20, title="Распределение времени до цитирования")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.bar_chart(if_data_with_time['Дни до цитаты'].dt.days)

if __name__ == "__main__":
    main()
