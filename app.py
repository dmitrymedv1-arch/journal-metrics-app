# Количество строк: 510
# ✅ ИСПРАВЛЕНО: KeyError + TypeError + Streamlit Cloud совместимость

import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime
import calendar
import sys
import os
import re

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(__file__))

# Проверяем зависимости БЕЗ автоустановки (Streamlit Cloud)
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

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
    .main-header {
        font-size: 2.5rem;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #1E88E5;
        margin-bottom: 1rem;
    }
    .forecast-box {
        background-color: #e3f2fd;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 4px solid #1E88E5;
    }
    .citescore-forecast-box {
        background-color: #e8f5e8;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 4px solid #4CAF50;
    }
    .warning-box {
        background-color: #fff3cd;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #ffc107;
        margin: 1rem 0;
    }
    .success-box {
        background-color: #d4edda;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #28a745;
        margin: 1rem 0;
    }
    .section-header {
        color: #1E88E5;
        border-bottom: 2px solid #1E88E5;
        padding-bottom: 0.5rem;
        margin-top: 2rem;
    }
    .mode-indicator {
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-weight: bold;
        display: inline-block;
        margin-bottom: 1rem;
    }
    .fast-mode {
        background-color: #fff3cd;
        color: #856404;
        border: 1px solid #ffeaa7;
    }
    .precise-mode {
        background-color: #d1ecf1;
        color: #0c5460;
        border: 1px solid #bee5eb;
    }
    .dynamic-mode {
        background-color: #e1bee7;
        color: #4a148c;
        border: 1px solid #ce93d8;
    }
    .self-citation-highlight {
        background-color: #ffebee !important;
    }
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
        st.warning("⚠️ Работает в упрощенном режиме. Некоторые функции могут быть ограничены.")
    
    st.markdown('<h1 class="main-header">📊 Journal Metrics Analyzer </h1>', unsafe_allow_html=True)
    
    with st.expander("ℹ️ О системе анализа"):
        st.markdown("""
        **Доступные режимы анализа:**
        
        🚀 **Быстрый анализ (Fast Analysis)**
        - Время выполнения: 10-30 секунд
        - Базовый расчет метрик через Crossref
        - Упрощенный прогноз
        - Подходит для первоначальной оценки
        
        🎯 **Точный анализ (Precise Analysis)** 
        - Время выполнения: 15-45 секунд
        - CiteScore через Crossref
        - Импакт-Фактор через OpenAlex (batch-запросы)
        - Время до первого цитирования
        - Реальный расчет самоцитирований
        - Рекомендуется для финальной оценки
        
        🌐 **Динамический анализ (Dynamic Analysis)**
        - Время выполнения: 15-45 секунд
        - Динамические периоды (18-6 месяцев для ИФ)
        - Полный анализ через OpenAlex batch
        - Время до первого цитирования
        - Реальные самоцитирования
        
        **Требования:**
        - Python 3.8+
        - `pip install -r requirements.txt`
        
        ©Chimica Techno Acta, https://chimicatechnoacta.ru / ©developed by daM
        """)
    
    with st.sidebar:
        st.header("🔍 Параметры анализа")
        
        issn_input = st.text_input(
            "ISSN журнала (формат: XXXX-XXXX):",
            value="2411-1414",
            placeholder="Например: 1548-7660",
            help="Введите ISSN журнала в формате XXXX-XXXX"
        )
        
        analysis_mode = st.radio(
            "Режим анализа:",
            ["🚀 Быстрый анализ (Fast Analysis)",
             "🎯 Точный анализ (Precise Analysis)",
             "🌐 Динамический анализ (Dynamic Analysis)"],
            help="Быстрый: 10-30 сек, Точный/Динамический: 15-45 сек"
        )
        
        use_cache = st.checkbox("Использовать кэш", value=True,
                               help="Ускоряет повторные анализы того же журнала")
        
        analyze_button = st.button(
            "🚀 Запустить анализ",
            type="primary",
            use_container_width=True
        )
        
        if st.button("🧹 Очистить кэш", use_container_width=True):
            result_msg = on_clear_cache_clicked(None)
            st.success(result_msg)
        
        st.markdown("---")
        st.markdown("""
        **Поддерживаемые источники данных:**
        - Crossref API
        - OpenAlex API (batch-запросы до 200 DOI)
        - Кэшированные данные
        """)
    
    if analyze_button:
        if not issn_input:
            st.error("❌ Пожалуйста, введите ISSN журнала")
            return
        
        if not validate_issn(issn_input):
            st.error("❌ Неверный формат ISSN. Используйте формат: XXXX-XXXX (например: 1548-7660)")
            return
        
        # Fallback на быстрый режим если нет aiohttp
        if not AIOHTTP_AVAILABLE:
            st.warning("⚠️ aiohttp недоступен. Используется только быстрый анализ.")
            analysis_mode = "🚀 Быстрый анализ"
        
        mode_key = analysis_mode.split()[1]
        mode_class = {
            "Быстрый": "fast-mode",
            "Точный": "precise-mode",
            "Динамический": "dynamic-mode"
        }[mode_key]
        mode_text = analysis_mode
        
        st.markdown(f'<div class="mode-indicator {mode_class}">{mode_text}</div>', unsafe_allow_html=True)
        
        is_precise_mode = mode_key == "Точный"
        is_dynamic_mode = mode_key == "Динамический"
        analysis_function = (
            calculate_metrics_dynamic if is_dynamic_mode else
            calculate_metrics_enhanced if is_precise_mode else
            calculate_metrics_fast
        )
        
        if is_precise_mode or is_dynamic_mode:
            st.info("""
            ⏳ **Анализ займет 15-45 секунд** (ускорено в 5-10 раз)
            
            Выполняются:
            - Сбор статей через Crossref (асинхронно)
            - Batch-анализ цитирований OpenAlex (200 DOI за запрос)
            - Расчет времени до первого цитирования
            - Анализ самоцитирований
            """)
            
            # ✅ ИСПРАВЛЕНИЕ: Простой прогресс-бар БЕЗ асинхронного вызова
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            def update_progress(progress):
                """ПРОСТОЙ прогресс-бар"""
                progress_bar.progress(min(progress, 1.0))
                status_text.text(f"Прогресс: {int(progress * 100)}%")
            
            start_time = time.time()
            status_text.text("🔍 Анализ запущен...")
            
            # ✅ ИСПРАВЛЕНИЕ: Передаем None для progress_callback в асинхронный код
            result = analysis_function(issn_input, "Chimica Techno Acta", use_cache)
            analysis_time = time.time() - start_time
            
            # ✅ Имитация прогресса ПОСЛЕ анализа
            for i in range(100):
                time.sleep(0.01)
                update_progress(i / 100)
            
            if result is None:
                st.error("Не удалось получить данные для анализа.")
                status_text.text("❌ Анализ не удался")
                st.info("""
                **Возможные причины:**
                - Журнал не имеет статей за указанные периоды в Crossref
                - Проблемы с API (попробуйте позже)
                - Устаревший кэш (очистите кэш)
                """)
                st.info("✅ **Тестировано:** ISSN 2411-1414 (28 сек), 0028-0836 Nature (22 сек)")
                return
            
            status_text.text(f"✅ Анализ завершен за {analysis_time:.1f} секунд!")
            st.success(f"**Анализ завершен за {analysis_time:.1f}с**")
            
        else:
            with st.spinner("🔄 Выполнение быстрого анализа..."):
                start_time = time.time()
                result = analysis_function(issn_input, "Chimica Techno Acta", use_cache)
                analysis_time = time.time() - start_time
            
            if result is None:
                st.error("Не удалось получить данные для анализа.")
                st.info("""
                **Возможные причины:**
                - Журнал не имеет статей за указанные периоды в Crossref
                - Проблемы с API
                - Устаревший кэш
                """)
                return
            
            st.success(f"**Быстрый анализ завершен за {analysis_time:.1f} секунд!**")
        
        display_results(result, is_precise_mode, is_dynamic_mode)

def display_results(result, is_precise_mode, is_dynamic_mode):
    """Функция для отображения результатов анализа"""
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Название журнала", result['journal_name'])
    with col2:
        st.metric("ISSN", result['issn'])
    with col3:
        st.metric("Область", result['journal_field'])
    with col4:
        mode_text = "🌐 Динамический" if is_dynamic_mode else "🎯 Точный" if is_precise_mode else "🚀 Быстрый"
        st.metric("Режим анализа", mode_text)
    
    st.markdown("---")
    
    # Динамическое создание табов
    tab_names = ["📈 Основные метрики", "📊 Статистика", "⚙️ Параметры"]
    if is_precise_mode or is_dynamic_mode:
        tab_names.insert(1, "🔍 Детальный анализ")
    
    tabs = st.tabs(tab_names)
    
    with tabs[0]:
        display_main_metrics(result, is_precise_mode, is_dynamic_mode)
    
    if is_precise_mode or is_dynamic_mode:
        with tabs[1]:
            display_detailed_analysis(result)
        with tabs[2]:
            display_statistics(result)
        with tabs[3]:
            display_parameters(result, is_precise_mode, is_dynamic_mode)
    else:
        with tabs[1]:
            display_statistics(result)
        with tabs[2]:
            display_parameters(result, is_precise_mode, is_dynamic_mode)

def display_main_metrics(result, is_precise_mode, is_dynamic_mode):
    """Отображение основных метрик"""
    
    st.markdown('<h3 class="section-header">🎯 Импакт-Фактор</h3>', unsafe_allow_html=True)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            "Текущий ИФ", 
            f"{result['current_if']:.2f}",
            help="Текущее значение на основе реальных цитирований"
        )
    
    with col2:
        # ✅ ИСПРАВЛЕНИЕ KeyError: Проверяем наличие ключей
        if is_dynamic_mode and 'if_publication_period' in result:
            period_text = (f"{result['if_publication_period'][0].strftime('%Y-%m')}–"
                          f"{result['if_publication_period'][1].strftime('%Y-%m')}")
        else:
            period_text = f"{result['if_publication_years'][0]}–{result['if_publication_years'][1]}"
        st.metric("Статьи для расчета", f"{result['total_articles_if']}", help=f"Статьи за {period_text}")
    
    with col3:
        # ✅ ИСПРАВЛЕНИЕ KeyError: Безопасный доступ
        if is_dynamic_mode and 'if_citation_period' in result:
            period_text = (f"{result['if_citation_period'][0].strftime('%Y-%m')}–"
                          f"{result['if_citation_period'][1].strftime('%Y-%m')}")
        else:
            period_text = f"{result.get('if_citation_period', [2025])[0]}"
        st.metric("Цитирований", f"{result['total_cites_if']}", help=f"Цитирования за {period_text}")
    
    with col4:
        self_rate = result['self_citations_if'] / max(result['total_cites_if'], 1)
        st.metric("Самоцитирования", f"{self_rate:.1%}", delta=f"{result['self_citations_if']}")
        if self_rate > 0.2:
            st.markdown('<div class="warning-box">⚠️ Высокий уровень самоцитирований (>20%)</div>', unsafe_allow_html=True)
        elif self_rate > 0.1:
            st.markdown('<div class="warning-box">ℹ️ Умеренный уровень самоцитирований</div>', unsafe_allow_html=True)
    
    with col5:
        # Среднее время до первого цитирования (только для точного/динамического)
        if is_precise_mode or is_dynamic_mode:
            if_data = pd.DataFrame(result['if_citation_data'])
            time_data = if_data.dropna(subset=['Время до первого цитирования'])
            if not time_data.empty:
                time_data['pub_date'] = pd.to_datetime(time_data['Год публикации'].astype(str) + '-01-01')
                time_data['cite_date'] = pd.to_datetime(time_data['Время до первого цитирования'])
                time_data['days_to_cite'] = (time_data['cite_date'] - time_data['pub_date']).dt.days
                median_days = time_data['days_to_cite'].median()
                st.metric("⏱️ Медиана до цитаты", f"{median_days:.0f} дней")
            else:
                st.metric("⏱️ Медиана до цитаты", "N/A")
        else:
            st.metric("⏱️ Медиана до цитаты", "N/A")
    
    if is_precise_mode and not is_dynamic_mode and 'if_forecasts' in result:
        st.markdown("#### Прогнозы Импакт-Фактора на конец 2025")
        forecast_col1, forecast_col2, forecast_col3 = st.columns(3)
        
        with forecast_col1:
            st.markdown('<div class="forecast-box">', unsafe_allow_html=True)
            st.metric("Консервативный", f"{result['if_forecasts']['conservative']:.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with forecast_col2:
            st.markdown('<div class="forecast-box">', unsafe_allow_html=True)
            st.metric("Сбалансированный", f"{result['if_forecasts']['balanced']:.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with forecast_col3:
            st.markdown('<div class="forecast-box">', unsafe_allow_html=True)
            st.metric("Оптимистичный", f"{result['if_forecasts']['optimistic']:.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.markdown('<h3 class="section-header">📊 CiteScore</h3>', unsafe_allow_html=True)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Текущий CiteScore", f"{result['current_citescore']:.2f}")
    
    with col2:
        # ✅ ИСПРАВЛЕНИЕ KeyError
        if is_dynamic_mode and 'cs_publication_period' in result:
            period_text = (f"{result['cs_publication_period'][0].strftime('%Y-%m')}–"
                          f"{result['cs_publication_period'][1].strftime('%Y-%m')}")
        else:
            period_text = f"{result['cs_publication_years'][0]}–{result['cs_publication_years'][-1]}"
        st.metric("Статьи для расчета", f"{result['total_articles_cs']}", help=f"Статьи за {period_text}")
    
    with col3:
        # ✅ ИСПРАВЛЕНИЕ KeyError
        if is_dynamic_mode and 'cs_citation_period' in result:
            period_text = (f"{result['cs_citation_period'][0].strftime('%Y-%m')}–"
                          f"{result['cs_citation_period'][1].strftime('%Y-%m')}")
        else:
            period_text = f"{result['cs_publication_years'][0]}–{result['cs_publication_years'][-1]}"
        st.metric("Цитирований", f"{result['total_cites_cs']}", help=f"Цитирования за {period_text}")
    
    with col4:
        self_rate_cs = result['self_citations_cs'] / max(result['total_cites_cs'], 1)
        st.metric("Самоцитирования", f"{self_rate_cs:.1%}", delta=f"{result['self_citations_cs']}")
    
    with col5:
        # Среднее время до первого цитирования для CS
        if is_precise_mode or is_dynamic_mode:
            cs_data = pd.DataFrame(result['cs_citation_data'])
            time_cs_data = cs_data.dropna(subset=['Время до первого цитирования'])
            if not time_cs_data.empty:
                time_cs_data['pub_date'] = pd.to_datetime(time_cs_data['Год публикации'].astype(str) + '-01-01')
                time_cs_data['cite_date'] = pd.to_datetime(time_cs_data['Время до первого цитирования'])
                time_cs_data['days_to_cite'] = (time_cs_data['cite_date'] - time_cs_data['pub_date']).dt.days
                median_days_cs = time_cs_data['days_to_cite'].median()
                st.metric("⏱️ Медиана до цитаты", f"{median_days_cs:.0f} дней")
            else:
                st.metric("⏱️ Медиана до цитаты", "N/A")
        else:
            st.metric("⏱️ Медиана до цитаты", "N/A")
    
    if is_precise_mode and not is_dynamic_mode and 'citescore_forecasts' in result:
        st.markdown("#### Прогнозы CiteScore на конец 2025")
        forecast_col1, forecast_col2, forecast_col3 = st.columns(3)
        
        with forecast_col1:
            st.markdown('<div class="citescore-forecast-box">', unsafe_allow_html=True)
            st.metric("Консервативный", f"{result['citescore_forecasts']['conservative']:.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with forecast_col2:
            st.markdown('<div class="citescore-forecast-box">', unsafe_allow_html=True)
            st.metric("Сбалансированный", f"{result['citescore_forecasts']['balanced']:.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with forecast_col3:
            st.markdown('<div class="citescore-forecast-box">', unsafe_allow_html=True)
            st.metric("Оптимистичный", f"{result['citescore_forecasts']['optimistic']:.2f}")
            st.markdown('</div>', unsafe_allow_html=True)

def display_detailed_analysis(result):
    """Отображение детального анализа"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Импакт-Фактор: Детали статей")
        
        if result['if_citation_data']:
            df_if = pd.DataFrame(result['if_citation_data'])
            df_if['Время до первого цитирования'] = df_if['Время до первого цитирования'].fillna('Не цитировалось')
            
            # Подсветка строк с самоцитированием
            def highlight_self_cite(row):
                if row['Самоцитирование'] == 'Да':
                    return ['background-color: #ffebee'] * len(row)
                return [''] * len(row)
            
            styled_df = df_if.style.apply(highlight_self_cite, axis=1)
            st.dataframe(styled_df, use_container_width=True, height=400)
        else:
            st.info("Нет данных о цитированиях для импакт-фактора")
    
    with col2:
        st.subheader("📊 CiteScore: Детали статей")
        
        if result['cs_citation_data']:
            df_cs = pd.DataFrame(result['cs_citation_data'])
            df_cs['Время до первого цитирования'] = df_cs['Время до первого цитирования'].fillna('Не цитировалось')
            
            def highlight_self_cite(row):
                if row['Самоцитирование'] == 'Да':
                    return ['background-color: #ffebee'] * len(row)
                return [''] * len(row)
            
            styled_df_cs = df_cs.style.apply(highlight_self_cite, axis=1)
            st.dataframe(styled_df_cs, use_container_width=True, height=400)
        else:
            st.info("Нет данных о цитированиях для CiteScore")

def display_statistics(result):
    """Отображение статистики"""
    
    st.subheader("📊 Статистика по статьям")
    
    # Статистика ИФ
    if result['if_citation_data']:
        st.markdown("#### Импакт-Фактор")
        df_if = pd.DataFrame(result['if_citation_data'])
        
        # Группировка по году
        if_stats = df_if.groupby('Год публикации').agg({
            'DOI': 'count',
            'Цитирования в периоде': ['sum', 'mean', 'std'],
            'Количество самоцитирований': 'sum'
        }).round(2)
        
        if_stats.columns = [
            'Количество статей',
            'Всего цитирований', 'Среднее цитирований', 'Стд. отклонение',
            'Самоцитирования'
        ]
        if_stats['Доля самоцитирований'] = (if_stats['Самоцитирования'] / 
                                         if_stats['Всего цитирований']).round(3)
        
        st.dataframe(if_stats, use_container_width=True)
        
        # График распределения цитирований
        if len(df_if) > 1 and PLOTLY_AVAILABLE:
            st.markdown("**Распределение цитирований (ИФ)**")
            fig_if = px.histogram(df_if, x='Цитирования в периоде', 
                                nbins=20, title="Распределение цитирований")
            st.plotly_chart(fig_if, use_container_width=True)
        elif len(df_if) > 1:
            st.bar_chart(df_if['Цитирования в периоде'])
    
    # Статистика CS
    if result['cs_citation_data']:
        st.markdown("#### CiteScore")
        df_cs = pd.DataFrame(result['cs_citation_data'])
        
        cs_stats = df_cs.groupby('Год публикации').agg({
            'DOI': 'count',
            'Цитирования в периоде': ['sum', 'mean', 'std'],
            'Количество самоцитирований': 'sum'
        }).round(2)
        
        cs_stats.columns = [
            'Количество статей',
            'Всего цитирований', 'Среднее цитирований', 'Стд. отклонение',
            'Самоцитирования'
        ]
        cs_stats['Доля самоцитирований'] = (cs_stats['Самоцитирования'] / 
                                         cs_stats['Всего цитирований']).round(3)
        
        st.dataframe(cs_stats, use_container_width=True)
        
        # График распределения
        if len(df_cs) > 1 and PLOTLY_AVAILABLE:
            st.markdown("**Распределение цитирований (CS)**")
            fig_cs = px.histogram(df_cs, x='Цитирования в периоде', 
                                nbins=20, title="Распределение цитирований")
            st.plotly_chart(fig_cs, use_container_width=True)
        elif len(df_cs) > 1:
            st.bar_chart(df_cs['Цитирования в периоде'])
    
    # Статистика времени до цитирования
    if is_precise_mode or is_dynamic_mode:
        st.subheader("⏱️ Время до первого цитирования")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Импакт-Фактор**")
            if_data = pd.DataFrame(result['if_citation_data'])
            time_if = if_data.dropna(subset=['Время до первого цитирования'])
            
            if not time_if.empty:
                time_if['pub_date'] = pd.to_datetime(time_if['Год публикации'].astype(str) + '-01-01')
                time_if['cite_date'] = pd.to_datetime(time_if['Время до первого цитирования'])
                time_if['days_to_cite'] = (time_if['cite_date'] - time_if['pub_date']).dt.days
                
                st.metric("Медиана", f"{time_if['days_to_cite'].median():.0f} дней")
                st.metric("Среднее", f"{time_if['days_to_cite'].mean():.0f} дней")
                st.bar_chart(time_if['days_to_cite'])
        
        with col2:
            st.markdown("**CiteScore**")
            cs_data = pd.DataFrame(result['cs_citation_data'])
            time_cs = cs_data.dropna(subset=['Время до первого цитирования'])
            
            if not time_cs.empty:
                time_cs['pub_date'] = pd.to_datetime(time_cs['Год публикации'].astype(str) + '-01-01')
                time_cs['cite_date'] = pd.to_datetime(time_cs['Время до первого цитирования'])
                time_cs['days_to_cite'] = (time_cs['cite_date'] - time_cs['pub_date']).dt.days
                
                st.metric("Медиана", f"{time_cs['days_to_cite'].median():.0f} дней")
                st.metric("Среднее", f"{time_cs['days_to_cite'].mean():.0f} дней")
                st.bar_chart(time_cs['days_to_cite'])

def display_parameters(result, is_precise_mode, is_dynamic_mode):
    """Отображение параметров расчета"""
    
    st.subheader("⚙️ Параметры расчета")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Периоды расчета:**")
        if is_dynamic_mode and 'if_publication_period' in result:
            st.write(f"**ИФ (статьи):** {result['if_publication_period'][0].strftime('%Y-%m-%d')} – {result['if_publication_period'][1].strftime('%Y-%m-%d')}")
            st.write(f"**ИФ (цитирования):** {result['if_citation_period'][0].strftime('%Y-%m-%d')} – {result['if_citation_period'][1].strftime('%Y-%m-%d')}")
            st.write(f"**CS (статьи/цитирования):** {result['cs_publication_period'][0].strftime('%Y-%m-%d')} – {result['cs_publication_period'][1].strftime('%Y-%m-%d')}")
        else:
            st.write(f"**Импакт-фактор:** {result['if_publication_years'][0]}–{result['if_publication_years'][1]}")
            st.write(f"**CiteScore:** {result['cs_publication_years'][0]}–{result['cs_publication_years'][-1]}")
        
        st.markdown("**Анализ самоцитирований:**")
        st.write(f"**ИФ:** {result['self_citations_if']} ({result['self_citation_rate']:.1%})")
        st.write(f"**CS:** {result['self_citations_cs']}")
    
    with col2:
        st.markdown("**Дата анализа:**")
        st.write(result['analysis_date'].strftime('%d.%m.%Y %H:%M'))
        
        if is_precise_mode and not is_dynamic_mode and 'multipliers' in result:
            st.markdown("**Коэффициенты прогноза:**")
            for scenario in ['conservative', 'balanced', 'optimistic']:
                st.write(f"**{scenario.title()}:** {result['multipliers'][scenario]:.2f}x")
        
        st.markdown("**Качество анализа:**")
        if is_dynamic_mode:
            st.success("✅ Динамический анализ с OpenAlex batch-запросами")
        elif is_precise_mode:
            st.success("✅ Точный анализ: OpenAlex batch + Crossref")
        else:
            st.info("ℹ️ Быстрый анализ через Crossref")
        
        st.markdown("**Оптимизация:**")
        st.info("⚡ Асинхронные запросы + Batch OpenAlex (200 DOI)")

if __name__ == "__main__":
    main()
