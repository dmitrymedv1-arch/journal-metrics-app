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
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Кастомные стили CSS
st.markdown("""<style>
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
    .citescore-comparison {
        background-color: #fff3e0;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid #ff9800;
    }
    .impact-factor-comparison {
        background-color: #f3e5f5;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid #9c27b0;
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
        st.warning(" Работает в упрощенном режиме. Некоторые функции могут быть ограничены.")

    st.markdown('<h1 class="main-header"> Journal Metrics Analyzer </h1>', unsafe_allow_html=True)

    with st.expander(" О системе анализа"):
        st.markdown("""
        **Доступные режимы анализа:**
        
         **Быстрый анализ (Fast Analysis)**
        - Время выполнения: 10-30 секунд
        - Базовый расчет метрик через Crossref
        - Упрощенный прогноз
        - Подходит для первоначальной оценки
        
         **Точный анализ (Precise Analysis)** 
        - Время выполнения: 2-5 минут
        - CiteScore через Crossref
        - Импакт-Фактор через OpenAlex (цитирования 2025 года)
        - **Параллельные запросы OpenAlex** для ускорения
        - Полный анализ самоцитирований
        - Рекомендуется для финальной оценки
        
         **Динамический анализ (Dynamic Analysis)**
        - Время выполнения: 3-8 минут
        - **Два значения Impact Factor**: Crossref и OpenAlex
        - **Два значения CiteScore**: Crossref и OpenAlex  
        - Периоды: статьи 43-19 мес назад, цитирования 18-6 мес назад для IF
        - Impact Factor (OpenAlex) отражает реальную логику расчета IF с учетом полугодовой задержки относительно предыдущего периода (например, IF за 2025 г. объявляется в конце июня 2026 г.)
        - Без прогнозов, только текущие метрики
        
        ** Новые возможности:**
        - Автоматическое определение названия журнала по ISSN
        - Параллельная обработка цитирований (ускорение до 5x)
        - Колонка с датой публикации в таблице детального анализа
        
        ©Chimica Techno Acta, https://chimicatechnoacta.ru / ©developed by daM
        """)

    with st.sidebar:
        st.header(" Параметры анализа")
        
        issn_input = st.text_input(
            "ISSN журнала (формат: XXXX-XXXX):",
            value="2411-1414",
            placeholder="Например: 1548-7660",
            help="Введите ISSN журнала в формате XXXX-XXXX"
        )
        
        if issn_input and validate_issn(issn_input):
            with st.spinner(" Определение названия журнала..."):
                detected_name = get_journal_name_from_issn(issn_input)
                st.markdown(f'<div class="journal-name-box"><strong> Найден журнал:</strong> {detected_name}</div>', unsafe_allow_html=True)
        
        analysis_mode = st.radio(
            "Режим анализа:",
            ["Быстрый анализ (Fast Analysis)",
             "Точный анализ (Precise Analysis)",
             "Динамический анализ (Dynamic Analysis)"],
            help="Быстрый: 10-30 сек, Точный: 2-5 мин, Динамический: 3-8 мин"
        )
        
        use_parallel = st.checkbox(
            " Параллельные запросы OpenAlex", 
            value=True,
            help="Ускоряет анализ цитирований до 5x (требует точный/динамический режим)"
        )
        
        max_workers = st.slider(
            "Количество параллельных потоков:",
            min_value=1,
            max_value=10,
            value=5,
            help="Больше потоков = быстрее, но выше нагрузка на API"
        )
        
        use_cache = st.checkbox(" Использовать кэш", value=True,
                               help="Ускоряет повторные анализы того же журнала")
        
        if use_parallel and ("Быстрый" in analysis_mode):
            st.warning(" Параллельные запросы доступны только в точном/динамическом режимах")
            use_parallel = False
        
        analyze_button = st.button(
            " Запустить анализ",
            type="primary",
            use_container_width=True
        )
        
        if st.button(" Очистить кэш", use_container_width=True):
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
            st.error(" Пожалуйста, введите ISSN журнала")
            return
        
        if not validate_issn(issn_input):
            st.error(" Неверный формат ISSN. Используйте формат: XXXX-XXXX (например: 1548-7660)")
            return
        
        with st.spinner(" Получение данных о журнале..."):
            real_journal_name = get_journal_name_from_issn(issn_input)
        
        # Исправленная логика определения режима
        if "Быстрый" in analysis_mode:
            mode_class = "fast-mode"
            mode_text = "Быстрый анализ"
        elif "Точный" in analysis_mode:
            mode_class = "precise-mode"
            mode_text = "Точный анализ"
        elif "Динамический" in analysis_mode:
            mode_class = "dynamic-mode"
            mode_text = "Динамический анализ"
        else:
            mode_class = "fast-mode"
            mode_text = "Быстрый анализ"
            
        st.markdown(f'<div class="mode-indicator {mode_class}">{mode_text}</div>', unsafe_allow_html=True)
        
        if use_parallel:
            st.markdown(f'<div class="parallel-indicator"> Параллельная обработка включена ({max_workers} потоков)</div>', unsafe_allow_html=True)
        
        is_precise_mode = "Точный" in analysis_mode
        is_dynamic_mode = "Динамический" in analysis_mode
        analysis_function = (
            calculate_metrics_dynamic if is_dynamic_mode else
            calculate_metrics_enhanced if is_precise_mode else
            calculate_metrics_fast
        )
        
        if is_dynamic_mode:
            st.info(f"""
             **Анализ может занять 3-8 минут**
            
            Выполняются:
            - Сбор статей за 52 месяца через Crossref
            - **Параллельный** анализ цитирований через OpenAlex
            - Расчет **двух значений** Impact Factor и CiteScore
            - **Impact Factor (OpenAlex)** отражает реальную логику расчета IF с учетом полугодовой задержки относительно предыдущего периода (например, IF за 2025 г. объявляется в конце июня 2026 г.)
            """)
        elif is_precise_mode:
            st.info(f"""
             **Анализ может занять 2-5 минут**
            
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
                status_text.text(" Сбор данных...")
                
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
                
                status_text.text(f" Анализ завершен за {analysis_time:.1f} секунд!")
            else:
                with st.spinner(" Выполнение быстрого анализа..."):
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
        mode_text = "Динамический" if is_dynamic_mode else "Точный" if is_precise_mode else "Быстрый"
        st.metric("Режим анализа", mode_text)

    st.markdown("---")

    tab_names = ["Основные метрики", "Статистика", "Параметры"]
    if is_precise_mode or is_dynamic_mode:
        tab_names.insert(1, "Детальный анализ")

    tabs = st.tabs(tab_names)

    with tabs[0]:
        display_main_metrics(result, is_precise_mode, is_dynamic_mode)

    if is_precise_mode or is_dynamic_mode:
        with tabs[1]:
            display_detailed_analysis(result, is_dynamic_mode)
        with tabs[2]:
            display_statistics(result, is_dynamic_mode)
        with tabs[3]:
            display_parameters(result, is_precise_mode, is_dynamic_mode)
    else:
        with tabs[1]:
            display_statistics(result, is_dynamic_mode)
        with tabs[2]:
            display_parameters(result, is_precise_mode, is_dynamic_mode)

def display_main_metrics(result, is_precise_mode, is_dynamic_mode):
    """Отображение основных метрик"""
    
    if is_dynamic_mode:
        # ДИНАМИЧЕСКИЙ РЕЖИМ
        st.markdown('<h3 class="section-header"> Impact Factor </h3>', unsafe_allow_html=True)
        
        st.markdown('<div class="impact-factor-comparison">', unsafe_allow_html=True)
        st.markdown("**Сравнение Impact Factor по разным источникам:**")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Impact Factor (Crossref)", 
                f"{result['impact_factor_crossref']:.2f}",
                help="Рассчитан на основе данных Crossref (все цитирования)"
            )
        
        with col2:
            st.metric(
                "Impact Factor (OpenAlex)", 
                f"{result['impact_factor_openalex']:.2f}",
                help="Рассчитан на основе данных OpenAlex (цитирования 18-6 мес назад)"
            )
        
        with col3:
            difference = result['impact_factor_openalex'] - result['impact_factor_crossref']
            st.metric(
                "Разница", 
                f"{difference:+.2f}",
                help="Разница между OpenAlex и Crossref"
            )
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Дополнительная информация о статьях и цитированиях для IF
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Статьи для IF (43-19 мес)", 
                f"{result['if_denominator']}",
                help="Статьи за период 43-19 месяцев назад"
            )
        
        with col2:
            st.metric(
                "Цитирований IF (Crossref)", 
                f"{result['if_crossref_numerator']:.1f}",
                help="Все цитирования Crossref для статей 43-19 мес назад"
            )
        
        with col3:
            st.metric(
                "Цитирований IF (OpenAlex)", 
                f"{result['if_openalex_numerator']:.1f}",
                help="Цитирования OpenAlex 18-6 мес назад для статей 43-19 мес назад"
            )

        st.markdown("---")
        st.markdown('<h3 class="section-header"> CiteScore </h3>', unsafe_allow_html=True)

        st.markdown('<div class="citescore-comparison">', unsafe_allow_html=True)
        st.markdown("**Сравнение CiteScore по разным источникам:**")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "CiteScore (Crossref)", 
                f"{result['citescore_crossref']:.2f}",
                help="Рассчитан на основе данных Crossref"
            )
        
        with col2:
            st.metric(
                "CiteScore (OpenAlex)", 
                f"{result['citescore_openalex']:.2f}",
                help="Рассчитан на основе данных OpenAlex"
            )
        
        with col3:
            difference = result['citescore_openalex'] - result['citescore_crossref']
            st.metric(
                "Разница", 
                f"{difference:+.2f}",
                help="Разница между OpenAlex и Crossref"
            )
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Дополнительная информация о статьях и цитированиях для CiteScore
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Всего статей", 
                f"{result['total_articles']}",
                help="Все статьи за анализируемый период"
            )
        
        with col2:
            st.metric(
                "Цитирований (Crossref)", 
                f"{result['total_crossref_citations']}",
                help="Все цитирования Crossref"
            )
        
        with col3:
            st.metric(
                "Цитирований (OpenAlex)", 
                f"{result['total_openalex_citations']}",
                help="Все цитирования OpenAlex"
            )
            
    else:
        # СТАНДАРТНЫЙ РЕЖИМ (быстрый и точный)
        st.markdown('<h3 class="section-header"> Импакт-Фактор</h3>', unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Текущий ИФ", 
                f"{result['current_if']:.2f}",
                help="Текущее значение на основе цитирований в периоде"
            )

        with col2:
            if is_dynamic_mode:
                st.metric(
                    "Статьи для расчета", 
                    f"{result['total_articles_if']}",
                    help=f"Статьи за {result['if_publication_period'][0]}–{result['if_publication_period'][1]}"
                )
            else:
                st.metric(
                    "Статьи для расчета", 
                    f"{result['total_articles_if']}",
                    help=f"Статьи за {result['if_publication_years'][0]}–{result['if_publication_years'][1]}"
                )

        with col3:
            if is_dynamic_mode:
                st.metric(
                    "Цитирований", 
                    f"{result['total_cites_if']}",
                    help=f"Цитирования за {result['if_citation_period'][0]}–{result['if_citation_period'][1]}"
                )
            else:
                st.metric(
                    "Цитирований", 
                    f"{result['total_cites_if']}",
                    help=f"Цитирования за {result['if_publication_years'][0]}–{result['if_publication_years'][1]}"
                )

        if is_precise_mode and not is_dynamic_mode:
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

        st.markdown('<h3 class="section-header"> CiteScore</h3>', unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Текущий CiteScore", f"{result['current_citescore']:.2f}")
        
        with col2:
            if is_dynamic_mode:
                st.metric("Статьи для расчета", f"{result['total_articles_cs']}",
                         help=f"Статьи за {result['cs_publication_period'][0]}–{result['cs_publication_period'][1]}")
            else:
                st.metric("Статьи для расчета", f"{result['total_articles_cs']}",
                         help=f"Статьи за {result['cs_publication_years'][0]}–{result['cs_publication_years'][-1]}")
        
        with col3:
            if is_dynamic_mode:
                st.metric("Цитирований", f"{result['total_cites_cs']}",
                         help=f"Цитирования за {result['cs_citation_period'][0]}–{result['cs_citation_period'][1]}")
            else:
                st.metric("Цитирований", f"{result['total_cites_cs']}",
                         help=f"Цитирования за {result['cs_publication_years'][0]}–{result['cs_publication_years'][-1]}")

        if is_precise_mode and not is_dynamic_mode:
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

def display_detailed_analysis(result, is_dynamic_mode):
    """Отображение детального анализа (только для точного и динамического режимов)"""
    col1, col2 = st.columns(2)

    with col1:
        st.subheader(" Распределение цитирований")
        
        if result.get('articles_data') and is_dynamic_mode:
            # Для динамического режима используем articles_data
            articles_df = pd.DataFrame(result['articles_data'])
            
            # Создаем отображаемую таблицу с понятными названиями колонок
            display_df = articles_df.copy()
            display_df = display_df.rename(columns={
                'doi': 'DOI',
                'pub_date': 'Дата публикации', 
                'crossref_cites': 'Цитирования (Crossref)',
                'openalex_cites': 'Цитирования (OpenAlex)'
            })
            
            # Показываем только первые 100 строк для производительности
            if len(display_df) > 100:
                st.info(f"Показаны первые 100 строк из {len(display_df)}")
                st.dataframe(display_df.head(100), use_container_width=True)
            else:
                st.dataframe(display_df, use_container_width=True)
                
        elif result.get('if_citation_data'):
            if_data = pd.DataFrame(result['if_citation_data'])
            if_data = if_data[['DOI', 'Год публикации', 'Дата публикации', 'Цитирования (Crossref)', 'Цитирования (OpenAlex)', 'Цитирования в периоде']]
            st.dataframe(if_data, use_container_width=True)
        else:
            st.info("Нет данных о цитированиях")

    with col2:
        st.subheader(" Анализ самоцитирований")
        
        self_citation_rate = result.get('self_citation_rate', 0.05)
        
        st.metric("Уровень самоцитирований", f"{self_citation_rate:.1%}")
        st.metric("Примерное количество", f"{result.get('total_self_citations', 0):.0f}")
        
        if self_citation_rate > 0.2:
            st.warning(" Высокий уровень самоцитирований (>20%)")
        elif self_citation_rate > 0.1:
            st.info(" Умеренный уровень самоцитирований (10-20%)")
        else:
            st.success(" Нормальный уровень самоцитирований (<10%)")

        if is_dynamic_mode:
            st.subheader(" Статистика производительности")
            col_stat1, col_stat2 = st.columns(2)
            with col_stat1:
                st.metric("Всего запросов", f"{result.get('total_requests', 0)}")
                st.metric("Успешность", f"{result.get('success_rate', 0):.1f}%")
            with col_stat2:
                st.metric("Неудачных запросов", f"{result.get('failed_requests', 0)}")
                st.metric("Скорость", f"{result.get('processing_speed', 0):.2f} ст/сек")

def display_statistics(result, is_dynamic_mode=False):
    """Отображение статистики"""
    st.subheader(" Статистика по статьям")

    # Для динамического режима используем articles_data
    if result.get('articles_data') and is_dynamic_mode:
        articles_df = pd.DataFrame(result['articles_data'])
        
        st.markdown("#### Общая статистика")
        
        # Базовая статистика
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Всего статей", len(articles_df))
            st.metric("Статьи для IF", result.get('if_denominator', 0))
            st.metric("Среднее цитирований Crossref", f"{articles_df['crossref_cites'].mean():.2f}")
            
        with col2:
            st.metric("Цитирований Crossref", articles_df['crossref_cites'].sum())
            st.metric("Цитирований OpenAlex", articles_df['openalex_cites'].sum())
            st.metric("Среднее цитирований OpenAlex", f"{articles_df['openalex_cites'].mean():.2f}")
        
        st.markdown("#### Детальная статистика")
        
        # Статистика по годам
        articles_df['year'] = articles_df['pub_date'].str[:4]  # Извлекаем год из даты
        
        yearly_stats = articles_df.groupby('year').agg({
            'doi': 'count',
            'crossref_cites': ['sum', 'mean', 'max'],
            'openalex_cites': ['sum', 'mean', 'max']
        }).round(2)
        
        # Переименовываем колонки для лучшего отображения
        if not yearly_stats.empty:
            yearly_stats.columns = [
                'Количество статей',
                'Crossref сумма', 'Crossref среднее', 'Crossref максимум',
                'OpenAlex сумма', 'OpenAlex среднее', 'OpenAlex максимум'
            ]
            st.dataframe(yearly_stats, use_container_width=True)
        
        # Распределение цитирований
        st.markdown("#### Распределение цитирований")
        col_dist1, col_dist2 = st.columns(2)
        
        with col_dist1:
            zero_cites_crossref = (articles_df['crossref_cites'] == 0).sum()
            zero_cites_openalex = (articles_df['openalex_cites'] == 0).sum()
            
            st.metric("Статей без цитирований (Crossref)", zero_cites_crossref)
            st.metric("Статей без цитирований (OpenAlex)", zero_cites_openalex)
            
        with col_dist2:
            high_cites_crossref = (articles_df['crossref_cites'] > 10).sum()
            high_cites_openalex = (articles_df['openalex_cites'] > 10).sum()
            
            st.metric("Статей с >10 цитирований (Crossref)", high_cites_crossref)
            st.metric("Статей с >10 цитирований (OpenAlex)", high_cites_openalex)
            
    elif result.get('if_citation_data'):
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

    # Для CiteScore в стандартных режимах
    if result.get('cs_citation_data') and not is_dynamic_mode:
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
    elif not is_dynamic_mode:
        st.info("Нет данных о статьях для CiteScore")

def display_parameters(result, is_precise_mode, is_dynamic_mode):
    """Отображение параметров расчета"""
    st.subheader(" Параметры расчета")

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
            st.write(f"**Период статей**: 52-4 месяца назад")
            st.write(f"**IF - Период публикаций**: 43-19 месяцев назад")
            st.write(f"**IF - Период цитирований**: 18-6 месяцев назад")
            st.write(f"**CiteScore - Период**: 52-4 месяца назад")
        else:
            if 'if_publication_years' in result:
                st.write(f"**ИФ - Годы публикаций**: {result['if_publication_years'][0]}–{result['if_publication_years'][1]}")
            if 'cs_publication_years' in result:
                st.write(f"**CiteScore - Годы публикаций**: {result['cs_publication_years'][0]}–{result['cs_publication_years'][-1]}")

    if not is_dynamic_mode and 'multipliers' in result:
        st.markdown("#### Множители прогнозирования")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Консервативный", f"{result['multipliers']['conservative']:.2f}")
        with col2:
            st.metric("Сбалансированный", f"{result['multipliers']['balanced']:.2f}")
        with col3:
            st.metric("Оптимистичный", f"{result['multipliers']['optimistic']:.2f}")

    if 'seasonal_coefficients' in result:
        st.markdown("#### Сезонные коэффициенты")
        seasonal_data = pd.DataFrame(
            list(result['seasonal_coefficients'].items()),
            columns=['Месяц', 'Коэффициент']
        )
        st.dataframe(seasonal_data, use_container_width=True)

if __name__ == "__main__":
    main()
