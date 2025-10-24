# Количество строк: ~415
# Изменения:
# +15 строк: обновление display_main_metrics для двух CiteScore и display_detailed_analysis для новой колонки

import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime
import calendar
import sys
import os
import re
from concurrent.futures import ThreadPoolExecutor
import threading

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(__file__))

try:
    from journal_analyzer import (
        calculate_metrics_enhanced,
        calculate_metrics_fast,
        calculate_metrics_dynamic,
        detect_journal_field,
        on_clear_cache_clicked,
        get_journal_name_from_issn,
        validate_parallel_openalex
    )
    JOURNAL_ANALYZER_AVAILABLE = True
except ImportError as e:
    JOURNAL_ANALYZER_AVAILABLE = False
    st.error(f"Ошибка импорта journal_analyzer: {e}")
    def calculate_metrics_enhanced(*args, **kwargs):
        return None
    def calculate_metrics_fast(*args, **kwargs):
        return None
    def calculate_metrics_dynamic(*args, **kwargs):
        return None
    def detect_journal_field(*args, **kwargs):
        return "general"
    def on_clear_cache_clicked(*args, **kwargs):
        return "Кэш не доступен"
    def get_journal_name_from_issn(*args, **kwargs):
        return "Неизвестный журнал"
    def validate_parallel_openalex(*args, **kwargs):
        return True, 20

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
        font-size: 2.0rem;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1.3rem;
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
    .journal-name-box {
        background-color: #f0f8ff;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid #1E88E5;
    }
    .parallel-indicator {
        background-color: #e8f5e8;
        color: #2e7d32;
        padding: 0.3rem 0.8rem;
        border-radius: 15px;
        font-size: 0.9rem;
        margin: 0.2rem 0;
    }
    .markdown-text-container p, .markdown-text-container li {
        line-height: 1.0 !important;
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
        - Время выполнения: 2-5 минут
        - CiteScore через Crossref
        - Импакт-Фактор через OpenAlex (цитирования текущего года)
        - **Параллельные запросы OpenAlex** для ускорения
        - Полный анализ самоцитирований
        - Рекомендуется для финальной оценки
        
        🌐 **Динамический анализ (Dynamic Analysis)**
        - Время выполнения: 2-5 минут
        - Imact Factor: цитирования за последние 18–6 месяцев на статьи за 42–18 месяцев назад (OpenAlex)
        - CiteScore: цитирования за 52–4 месяца назад на статьи за за 52–4 месяцев назад (OpenAlex и Crossref)
        - Imact Factor и CiteScore в динамическом анализе на текущую дату проведения анализа имитируют логику объявления оффициальных показателей в конце июня (для IF) и начале мая (для SC) за предыдущий анализируемый период.
        - **Параллельные запросы OpenAlex** для ускорения
        - Без прогнозов, текущие метрики
        
        **🆕 Новые возможности:**
        - Автоматическое определение названия журнала по ISSN
        - Параллельная обработка цитирований (ускорение до 5x)
        - Два значения CiteScore в динамическом режиме (OpenAlex и Crossref)
        - Колонка с датой публикации в таблице детального анализа
        
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
        
        if issn_input and validate_issn(issn_input):
            with st.spinner("🔍 Определение названия журнала..."):
                detected_name = get_journal_name_from_issn(issn_input)
                st.markdown(f'<div class="journal-name-box"><strong>📚 Найден журнал:</strong> {detected_name}</div>', unsafe_allow_html=True)
        
        analysis_mode = st.radio(
            "Режим анализа:",
            ["🚀 Быстрый анализ (Fast Analysis)",
             "🎯 Точный анализ (Precise Analysis)",
             "🌐 Динамический анализ (Dynamic Analysis)"],
            help="Быстрый: 10-30 сек, Точный/Динамический: 2-5 мин"
        )
        
        use_parallel = st.checkbox(
            "⚡ Параллельные запросы OpenAlex", 
            value=True,
            help="Ускоряет анализ цитирований до 5x (требует точный/динамический режим)"
        )
        
        max_workers = st.slider(
            "Количество параллельных потоков:",
            min_value=3,
            max_value=20,
            value=5,
            help="Больше потоков = быстрее, но выше нагрузка на API"
        )
        
        use_cache = st.checkbox("💾 Использовать кэш", value=True,
                               help="Ускоряет повторные анализы того же журнала")
        
        if use_parallel and (analysis_mode == "🚀 Быстрый анализ (Fast Analysis)"):
            st.warning("⚠️ Параллельные запросы доступны только в точном/динамическом режимах")
            use_parallel = False
        
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
        - OpenAlex API (в точном и динамическом режимах)
        - **Параллельные запросы OpenAlex** (ускорение до 5x)
        - Кэшированные данные
        """)
    
    if analyze_button:
        if not issn_input:
            st.error("❌ Пожалуйста, введите ISSN журнала")
            return
        
        if not validate_issn(issn_input):
            st.error("❌ Неверный формат ISSN. Используйте формат: XXXX-XXXX (например: 1548-7660)")
            return
        
        with st.spinner("🔍 Получение данных о журнале..."):
            real_journal_name = get_journal_name_from_issn(issn_input)
        
        mode_class = {
            "Быстрый": "fast-mode",
            "Точный": "precise-mode",
            "Динамический": "dynamic-mode"
        }[analysis_mode.split()[1]]
        mode_text = {
            "Быстрый": "🚀 Быстрый анализ",
            "Точный": "🎯 Точный анализ",
            "Динамический": "🌐 Динамический анализ"
        }[analysis_mode.split()[1]]
        st.markdown(f'<div class="mode-indicator {mode_class}">{mode_text}</div>', unsafe_allow_html=True)
        
        if use_parallel:
            st.markdown(f'<div class="parallel-indicator">⚡ Параллельная обработка включена ({max_workers} потоков)</div>', unsafe_allow_html=True)
        
        is_precise_mode = "Точный" in analysis_mode
        is_dynamic_mode = "Динамический" in analysis_mode
        analysis_function = (
            calculate_metrics_dynamic if is_dynamic_mode else
            calculate_metrics_enhanced if is_precise_mode else
            calculate_metrics_fast
        )
        
        if is_precise_mode or is_dynamic_mode:
            st.info(f"""
            ⏳ **Анализ может занять 2-5 минут**
            
            Выполняются:
            - Сбор статей через Crossref
            - **Параллельный** анализ цитирований через OpenAlex для ИФ и CiteScore
            - Расчет метрик
            """)
        
        try:
            if is_precise_mode or is_dynamic_mode:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(progress):
                    progress_bar.progress(min(progress, 1.0))
                    status_text.text(f"Прогресс: {int(progress * 100)}%")
                
                start_time = time.time()
                status_text.text("🔍 Сбор данных...")
                
                result = analysis_function(
                    issn_input, 
                    real_journal_name, 
                    use_cache, 
                    progress_callback=update_progress,
                    use_parallel=use_parallel,
                    max_workers=max_workers
                )
                analysis_time = time.time() - start_time
                
                if result is None:
                    st.error("Не удалось получить данные для анализа. Проверьте ISSN или наличие статей в Crossref за указанные периоды.")
                    status_text.text("Анализ не удался")
                    st.info("Попробуйте очистить кэш или использовать другой ISSN (например, 0028-0836 для Nature).")
                    st.markdown("**Возможные причины ошибки:**")
                    st.markdown("- Журнал не имеет статей за указанные периоды в Crossref.")
                    st.markdown("- Проблемы с API (например, ограничения запросов).")
                    st.markdown("- Устаревший кэш. Попробуйте очистить кэш.")
                    return
                
                status_text.text(f"✅ Анализ завершен за {analysis_time:.1f} секунд!")
            else:
                with st.spinner("🔄 Выполнение быстрого анализа..."):
                    start_time = time.time()
                    result = analysis_function(issn_input, real_journal_name, use_cache)
                    analysis_time = time.time() - start_time
                
                if result is None:
                    st.error("Не удалось получить данные для анализа. Проверьте ISSN или наличие статей в Crossref за указанные периоды.")
                    st.info("Попробуйте очистить кэш или использовать другой ISSN (например, 0028-0836 для Nature).")
                    st.markdown("**Возможные причины ошибки:**")
                    st.markdown("- Журнал не имеет статей за указанные периоды в Crossref.")
                    st.markdown("- Проблемы с API (например, ограничения запросов).")
                    st.markdown("- Устаревший кэш. Попробуйте очистить кэш.")
                    return
                
                st.success(f"Анализ завершен за {analysis_time:.1f} секунд!")
            
            display_results(result, is_precise_mode, is_dynamic_mode)
        
        except Exception as e:
            st.error(f"Произошла ошибка при анализе: {str(e)}")
            st.info("Попробуйте очистить кэш, проверить подключение к интернету или использовать другой ISSN.")

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
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Текущий ИФ", 
            f"{result['current_if']:.2f}",
            help="Текущее значение на основе цитирований в периоде"
        )
    
    with col2:
        st.metric(
            "Статьи для расчета", 
            f"{result['total_articles_if']}",
            help=f"Статьи за {result['if_publication_period' if is_dynamic_mode else 'if_publication_years'][0]}–{result['if_publication_period' if is_dynamic_mode else 'if_publication_years'][1]}"
        )
    
    with col3:
        current_year = result['analysis_date'].year
        citation_period_start = result['if_citation_period'][0] if is_dynamic_mode else current_year
        citation_period_end = result['if_citation_period'][1] if is_dynamic_mode else current_year
        st.metric(
            "Цитирований", 
            f"{result['total_cites_if']}",
            help=f"Цитирования за {citation_period_start}–{citation_period_end}"
        )
    
    if is_precise_mode and not is_dynamic_mode:
        st.markdown("#### Прогнозы Импакт-Фактора на конец текущего года")
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
    
    if is_dynamic_mode:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("CiteScore (OpenAlex)", f"{result['current_citescore_openalex']:.2f}")
        
        with col2:
            st.metric("CiteScore (Crossref)", f"{result['current_citescore_crossref']:.2f}")
        
        with col3:
            st.metric("Статьи для расчета", f"{result['total_articles_cs']}",
                     help=f"Статьи за {result['cs_publication_period'][0]}–{result['cs_publication_period'][1]}")
        
        with col4:
            st.metric("Цитирований", f"O: {result['total_cites_cs_openalex']} | C: {result['total_cites_cs_crossref']}",
                     help=f"Цитирования за {result['cs_citation_period'][0]}–{result['cs_citation_period'][1]}")
    else:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Текущий CiteScore", f"{result['current_citescore']:.2f}")
        
        with col2:
            st.metric("Статьи для расчета", f"{result['total_articles_cs']}",
                     help=f"Статьи за {result['cs_publication_period' if is_dynamic_mode else 'cs_publication_years'][0]}–{result['cs_publication_period' if is_dynamic_mode else 'cs_publication_years'][-1]}")
        
        with col3:
            st.metric("Цитирований", f"{result['total_cites_cs']}",
                     help=f"Цитирования за {result['cs_citation_period' if is_dynamic_mode else 'cs_publication_years'][0]}–{result['cs_citation_period' if is_dynamic_mode else 'cs_publication_years'][-1]}")
    
    if is_precise_mode and not is_dynamic_mode:
        st.markdown("#### Прогнозы CiteScore на конец текущего года")
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
    """Отображение детального анализа (только для точного и динамического режимов)"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Распределение цитирований")
        
        if result['if_citation_data']:
            if_data = pd.DataFrame(result['if_citation_data'])
            if_data = if_data[['DOI', 'Год публикации', 'Дата публикации', 'Цитирования (Crossref)', 'Цитирования (OpenAlex)', 'Цитирования в периоде']]
            st.dataframe(if_data, use_container_width=True)
        else:
            st.info("Нет данных о цитированиях для импакт-фактора")
        
        if result['cs_citation_data']:
            st.markdown("#### Для CiteScore")
            cs_data = pd.DataFrame(result['cs_citation_data'])
            cs_data = cs_data[['DOI', 'Год публикации', 'Дата публикации', 'Цитирования (Crossref)', 'Цитирования (OpenAlex)', 'Цитирования в периоде']]
            st.dataframe(cs_data, use_container_width=True)
        else:
            st.info("Нет данных о цитированиях для CiteScore")
    
    with col2:
        st.subheader("🎯 Анализ самоцитирований")
        
        self_citation_rate = result['self_citation_rate']
        
        st.metric("Уровень самоцитирований", f"{self_citation_rate:.1%}")
        st.metric("Примерное количество", f"{result['total_self_citations']:.0f}")
        
        if self_citation_rate > 0.2:
            st.warning("⚠️ Высокий уровень самоцитирований (>20%)")
        elif self_citation_rate > 0.1:
            st.info("ℹ️ Умеренный уровень самоцитирований (10-20%)")
        else:
            st.success("✅ Нормальный уровень самоцитирований (<10%)")
    
    if result['citation_model_data']:
        st.subheader("📅 Временная модель цитирований")
        st.info(f"Построена модель на основе {len(result['citation_model_data'])} лет исторических данных")

def display_statistics(result):
    """Отображение статистики"""
    
    st.subheader("📊 Статистика по статьям")
    
    if result['if_citation_data']:
        st.markdown("#### Для импакт-фактора")
        df_if = pd.DataFrame(result['if_citation_data'])
        if_stats = df_if.groupby('Год публикации').agg({
            'DOI': 'count',
            'Цитирования (Crossref)': ['sum', 'mean', 'std'],
            'Цитирования (OpenAlex)': ['sum', 'mean', 'std'],
            'Цитирования в периоде': ['sum', 'mean', 'std']
        }).round(2)
        if_stats.columns = [
            'Количество статей',
            'Всего цитирований (Crossref)', 'Среднее цитирований (Crossref)', 'Стд. отклонение (Crossref)',
            'Всего цитирований (OpenAlex)', 'Среднее цитирований (OpenAlex)', 'Стд. отклонение (OpenAlex)',
            'Всего цитирований в периоде', 'Среднее цитирований в периоде', 'Стд. отклонение в периоде'
        ]
        st.dataframe(if_stats, use_container_width=True)
    else:
        st.info("Нет данных о статьях для импакт-фактора")
    
    if result['cs_citation_data']:
        st.markdown("#### Для CiteScore")
        df_cs = pd.DataFrame(result['cs_citation_data'])
        cs_stats = df_cs.groupby('Год публикации').agg({
            'DOI': 'count',
            'Цитирования (Crossref)': ['sum', 'mean', 'std'],
            'Цитирования (OpenAlex)': ['sum', 'mean', 'std'],
            'Цитирования в периоде': ['sum', 'mean', 'std']
        }).round(2)
        cs_stats.columns = [
            'Количество статей',
            'Всего цитирований (Crossref)', 'Среднее цитирований (Crossref)', 'Стд. отклонение (Crossref)',
            'Всего цитирований (OpenAlex)', 'Среднее цитирований (OpenAlex)', 'Стд. отклонение (OpenAlex)',
            'Всего цитирований в периоде', 'Среднее цитирований в периоде', 'Стд. отклонение в периоде'
        ]
        st.dataframe(cs_stats, use_container_width=True)
    else:
        st.info("Нет данных о статьях для CiteScore")

def display_parameters(result, is_precise_mode, is_dynamic_mode):
    """Отображение параметров расчета"""
    
    st.subheader("⚙️ Параметры расчета")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Общие параметры")
        st.write(f"**Дата анализа**: {result['analysis_date']}")
        st.write(f"**Область журнала**: {result['journal_field']}")
        st.write(f"**Параллельная обработка**: {'Да' if result.get('parallel_processing', False) else 'Нет'}")
        if result.get('parallel_processing'):
            st.write(f"**Количество потоков**: {result['parallel_workers']}")
    
    with col2:
        st.markdown("#### Периоды анализа")
        if is_dynamic_mode:
            st.write(f"**ИФ - Период публикаций**: {result['if_publication_period'][0]} – {result['if_publication_period'][1]}")
            st.write(f"**ИФ - Период цитирований**: {result['if_citation_period'][0]} – {result['if_citation_period'][1]}")
            st.write(f"**CiteScore - Период публикаций**: {result['cs_publication_period'][0]} – {result['cs_publication_period'][1]}")
            st.write(f"**CiteScore - Период цитирований**: {result['cs_citation_period'][0]} – {result['cs_citation_period'][1]}")
        else:
            st.write(f"**ИФ - Годы публикаций**: {', '.join(map(str, result['if_publication_years']))}")
            st.write(f"**CiteScore - Годы публикаций**: {', '.join(map(str, result['cs_publication_years']))}")
    
    if not is_dynamic_mode and 'multipliers' in result:
        st.markdown("#### Множители прогнозирования")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Консервативный", f"{result['multipliers']['conservative']:.2f}")
        with col2:
            st.metric("Сбалансированный", f"{result['multipliers']['balanced']:.2f}")
        with col3:
            st.metric("Оптимистичный", f"{result['multipliers']['optimistic']:.2f}")
    
    st.markdown("#### Сезонные коэффициенты")
    seasonal_data = pd.DataFrame(
        list(result['seasonal_coefficients'].items()),
        columns=['Месяц', 'Коэффициент']
    )
    st.dataframe(seasonal_data, use_container_width=True)

if __name__ == "__main__":
    main()











