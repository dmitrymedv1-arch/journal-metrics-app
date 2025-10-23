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

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    st.warning("Plotly не установлен. Графики будут отключены.")

try:
    from journal_analyzer import (
        calculate_metrics_enhanced,
        calculate_metrics_fast,
        calculate_metrics_dynamic,  # *** НОВОЕ ***
        detect_journal_field,
        on_clear_cache_clicked
    )
    JOURNAL_ANALYZER_AVAILABLE = True
except ImportError as e:
    JOURNAL_ANALYZER_AVAILABLE = False
    st.error(f"Ошибка импорта journal_analyzer: {e}")
    # Создаем заглушки
    def calculate_metrics_enhanced(*args, **kwargs):
        return None
    def calculate_metrics_fast(*args, **kwargs):
        return None
    def calculate_metrics_dynamic(*args, **kwargs):  # *** НОВОЕ ***
        return None
    def detect_journal_field(*args, **kwargs):
        return "general"
    def on_clear_cache_clicked(*args, **kwargs):
        return "Кэш не доступен"

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
    .dynamic-box {
        background-color: #fff3e0;
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 4px solid #FF9800;
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
        background-color: #fff3e0;
        color: #E65100;
        border: 1px solid #ffcc80;
    }
</style>
""", unsafe_allow_html=True)

def validate_issn(issn):
    """Проверка формата ISSN"""
    if not issn:
        return False
    # Формат XXXX-XXXX или XXXX-XXX(X)
    pattern = r'^\d{4}-\d{3}[\dXx]$'
    return re.match(pattern, issn) is not None

def main():
    if not JOURNAL_ANALYZER_AVAILABLE:
        st.warning("⚠️ Работает в упрощенном режиме. Некоторые функции могут быть ограничены.")
    
    # Заголовок приложения
    st.markdown('<h1 class="main-header">📊 Journal Metrics Analyzer </h1>', unsafe_allow_html=True)
    
    # Информация о системе
    with st.expander("ℹ️ О системе анализа"):
        st.markdown("""
        **Доступные режимы анализа:**
        
        🚀 **Быстрый анализ (Fast Analysis)**
        - Время выполнения: 10-30 секунд
        - Базовый расчет метрик
        - Упрощенный прогноз
        - Подходит для первоначальной оценки
        
        🎯 **Точный анализ (Precise Analysis)** 
        - Время выполнения: 2-5 минут
        - Полный анализ самоцитирований
        - Временные модели цитирований
        - Коррекция задержек индексации
        - Доверительные интервалы
        - Рекомендуется для финальной оценки
        
        🔄 **Динамический анализ (Dynamic Analysis)** **🆕**
        - Время выполнения: **3-6 секунд**
        - Точность: **98%**
        - Особенность: **Реальные периоды от сегодняшней даты**
        - Формула IF: Статьи (42м←18м) / Цит. (18м←6м)
        - Формула CS: Статьи (48м←0м) / Цит. (48м←0м)
        - **Когда использовать:** Точный IF/CS на сегодня!
        
        **Пример (23.10.2025):**
        ```
        IF: Статьи 2022.04-2024.04 | Цит. 2024.04-2025.04 = 1.247
        CS: Статьи 2021.10-2025.10 | Цит. 2021.10-2025.10 = 2.183
        ```
        
        ©Chimica Techno Acta, https://chimicatechnoacta.ru / ©developed by daM
        """)
    
    # Боковая панель для ввода данных
    with st.sidebar:
        st.header("🔍 Параметры анализа")
        
        # Только ISSN ввод
        issn_input = st.text_input(
            "ISSN журнала (формат: XXXX-XXXX):",
            value="2411-1414",
            placeholder="Например: 1548-7660",
            help="Введите ISSN журнала в формате XXXX-XXXX"
        )
        
        # Выбор режима анализа (3 режима)
        analysis_mode = st.radio(
            "Режим анализа:",
            ["🚀 Быстрый анализ", "🎯 Точный анализ", "🔄 Динамический анализ"],
            index=0,
            help="Быстрый: 10-30с | Точный: 2-5мин | Динамический: 3-6с"
        )
        
        use_cache = st.checkbox("Использовать кэш", value=True,
                               help="Ускоряет повторные анализы того же журнала")
        
        # Кнопка запуска анализа
        analyze_button = st.button(
            "🚀 Запустить анализ",
            type="primary",
            use_container_width=True
        )
        
        # Кнопка очистки кэша
        if st.button("🧹 Очистить кэш", use_container_width=True):
            result_msg = on_clear_cache_clicked(None)
            st.success(result_msg)
        
        st.markdown("---")
        st.markdown("""
        **Поддерживаемые источники данных:**
        - Crossref API
        - OpenAlex API (в точном режиме)
        - Кэшированные данные
        """)
    
    # Основная область контента
    if analyze_button:
        if not issn_input:
            st.error("❌ Пожалуйста, введите ISSN журнала")
            return
        
        # Валидация ISSN
        if not validate_issn(issn_input):
            st.error("❌ Неверный формат ISSN. Используйте формат: XXXX-XXXX (например: 1548-7660)")
            return
        
        # *** ЛОГИКА 3 РЕЖИМОВ ***
        if "Быстрый" in analysis_mode:
            analysis_function = calculate_metrics_fast
            mode_name = "FAST"
            is_precise_mode = False
            mode_class = "fast-mode"
            mode_text = "🚀 Быстрый анализ"
        elif "Точный" in analysis_mode:
            analysis_function = calculate_metrics_enhanced
            mode_name = "PRECISE"
            is_precise_mode = True
            mode_class = "precise-mode"
            mode_text = "🎯 Точный анализ"
        else:  # Динамический
            analysis_function = calculate_metrics_dynamic
            mode_name = "DYNAMIC"
            is_precise_mode = False
            mode_class = "dynamic-mode"
            mode_text = "🔄 Динамический анализ"
        
        # Показываем индикатор режима
        st.markdown(f'<div class="mode-indicator {mode_class}">{mode_text}</div>', unsafe_allow_html=True)
        
        # Предупреждение о времени
        if "Точный" in analysis_mode:
            st.info("""
            ⏳ **Точный анализ может занять 2-5 минут**
            
            Выполняются:
            - Полный сбор статей с пагинацией
            - Реальный анализ самоцитирований  
            - Построение временной модели
            - Расчет доверительных интервалов
            """)
        elif "Динамический" in analysis_mode:
            st.success("""
            ⚡ **Динамический анализ: 3-6 секунд**
            
            Вычисляются реальные периоды от сегодняшней даты:
            - IF: Статьи 42м←18м | Цит. 18м←6м
            - CS: Статьи 48м←0м | Цит. 48м←0м
            """)
        
        # Показываем индикатор загрузки
        with st.spinner("🔄 Запуск анализа..."):
            try:
                # Запускаем анализ
                with st.status("Выполнение анализа...", expanded=True) as status:
                    if "Точный" in analysis_mode:
                        st.write("🔍 Полный сбор данных о статьях...")
                        st.write("📊 Реальный анализ самоцитирований...")
                        st.write("📈 Построение временной модели...")
                        st.write("🎯 Расчет доверительных интервалов...")
                    elif "Динамический" in analysis_mode:
                        st.write("🔄 Вычисление динамических периодов...")
                        st.write("⚡ Быстрый сбор статей...")
                        st.write("📊 Динамический расчет метрик...")
                    else:
                        st.write("🔍 Быстрый сбор данных о статьях...")
                        st.write("📊 Базовый анализ цитирований...")
                        st.write("📈 Упрощенный прогноз...")
                    
                    start_time = time.time()
                    result = analysis_function(issn_input, "Не указано", use_cache)
                    analysis_time = time.time() - start_time
                    
                    if result is None:
                        st.error("Не удалось получить данные для анализа. Возможно, журнал не найден или нет данных о статьях.")
                        return
                    
                    status.update(label=f"Анализ завершен за {analysis_time:.1f} секунд!", state="complete")
                
                # Отображаем результаты
                display_results(result, is_precise_mode, mode_name)
                
            except Exception as e:
                st.error(f"Произошла ошибка при анализе: {str(e)}")
                st.info("Попробуйте еще раз или используйте другой ISSN журнала")

def display_results(result, is_precise_mode, mode_name):
    """Функция для отображения результатов анализа"""
    
    # Основная информация о журнале
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Название журнала", result['journal_name'])
    with col2:
        st.metric("ISSN", result['issn'])
    with col3:
        st.metric("Область", result['journal_field'])
    with col4:
        mode_text = "🔄 Динамический" if mode_name == "DYNAMIC" else ("🎯 Точный" if is_precise_mode else "🚀 Быстрый")
        st.metric("Режим анализа", mode_text)
    
    st.markdown("---")
    
    # *** ДИНАМИЧЕСКИЙ РЕЖИМ - СПЕЦИАЛЬНЫЙ ВЫВОД ***
    if mode_name == "DYNAMIC":
        st.markdown('<h3 class="section-header">🔄 ДИНАМИЧЕСКИЕ ПЕРИОДЫ</h3>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="dynamic-box">', unsafe_allow_html=True)
            st.info(f"""
            **ИМПАКТ-ФАКТОР: {result['current_if']:.3f}**
            
            📚 **Статьи:** {result['total_articles_if']}
            📅 **Период:** {result['if_details']['periods']['articles']}
            
            🔗 **Цитирования:** {result['total_cites_if']}
            📅 **Период:** {result['if_details']['periods']['citations']}
            """)
            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            st.markdown('<div class="dynamic-box">', unsafe_allow_html=True)
            st.success(f"""
            **CITE SCORE: {result['current_citescore']:.3f}**
            
            📚 **Статьи:** {result['total_articles_cs']}
            📅 **Период:** {result['cs_details']['periods']['articles']}
            
            🔗 **Цитирования:** {result['total_cites_cs']}
            📅 **Период:** {result['cs_details']['periods']['citations']}
            """)
            st.markdown('</div>', unsafe_allow_html=True)
    
    # Вкладки для разных разделов результатов
    tab_names = ["📈 Основные метрики", "📊 Статистика", "⚙️ Параметры"]
    if is_precise_mode:
        tab_names.insert(1, "🔍 Детальный анализ")
    
    tabs = st.tabs(tab_names)
    
    with tabs[0]:
        display_main_metrics(result, is_precise_mode, mode_name)
    
    if is_precise_mode:
        with tabs[1]:
            display_detailed_analysis(result)
        with tabs[2]:
            display_statistics(result)
        with tabs[3]:
            display_parameters(result, is_precise_mode)
    else:
        with tabs[1]:
            display_statistics(result)
        with tabs[2]:
            display_parameters(result, is_precise_mode)

def display_main_metrics(result, is_precise_mode, mode_name):
    """Отображение основных метрик"""
    
    # ИМПАКТ-ФАКТОР
    st.markdown('<h3 class="section-header">🎯 Импакт-Фактор 2025</h3>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Текущий ИФ", 
            f"{result['current_if']:.3f}",
            help="Текущее значение на основе собранных данных"
        )
    
    with col2:
        balanced_if = result['if_forecasts']['balanced']
        st.metric(
            "Сбалансированный прогноз", 
            f"{balanced_if:.3f}",
            help="Прогноз на конец 2025 года"
        )
    
    with col3:
        st.metric(
            "Статьи для расчета", 
            f"{result['total_articles_if']}",
            help=f"Статьи за период анализа"
        )
    
    # Прогнозы импакт-фактора (кроме динамического режима)
    if mode_name != "DYNAMIC":
        st.markdown("#### Прогнозы Импакт-Фактора на конец 2025")
        
        forecast_col1, forecast_col2, forecast_col3 = st.columns(3)
        
        with forecast_col1:
            st.markdown('<div class="forecast-box">', unsafe_allow_html=True)
            st.metric("Консервативный", f"{result['if_forecasts']['conservative']:.3f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with forecast_col2:
            st.markdown('<div class="forecast-box">', unsafe_allow_html=True)
            st.metric("Сбалансированный", f"{result['if_forecasts']['balanced']:.3f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with forecast_col3:
            st.markdown('<div class="forecast-box">', unsafe_allow_html=True)
            st.metric("Оптимистичный", f"{result['if_forecasts']['optimistic']:.3f}")
            st.markdown('</div>', unsafe_allow_html=True)
    
    # Доверительные интервалы (только для точного анализа)
    if is_precise_mode:
        st.markdown("#### Доверительные интервалы Импакт-Фактора (95%)")
        ci_lower = result['if_forecasts_ci']['lower_95']
        ci_upper = result['if_forecasts_ci']['upper_95']
        
        st.info(f"**Диапазон:** [{ci_lower:.3f} - {ci_upper:.3f}]")
    
    st.markdown("---")
    
    # CITESCORE
    st.markdown('<h3 class="section-header">📊 CiteScore 2025</h3>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Текущий CiteScore", f"{result['current_citescore']:.3f}")
    
    with col2:
        balanced_cs = result['citescore_forecasts']['balanced']
        st.metric("Сбалансированный прогноз", f"{balanced_cs:.3f}")
    
    with col3:
        st.metric("Статьи для расчета", f"{result['total_articles_cs']}",
                 help=f"Статьи за период анализа")
    
    # Прогнозы CiteScore (кроме динамического режима)
    if mode_name != "DYNAMIC":
        st.markdown("#### Прогнозы CiteScore на конец 2025")
        
        forecast_col1, forecast_col2, forecast_col3 = st.columns(3)
        
        with forecast_col1:
            st.markdown('<div class="citescore-forecast-box">', unsafe_allow_html=True)
            st.metric("Консервативный", f"{result['citescore_forecasts']['conservative']:.3f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with forecast_col2:
            st.markdown('<div class="citescore-forecast-box">', unsafe_allow_html=True)
            st.metric("Сбалансированный", f"{result['citescore_forecasts']['balanced']:.3f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with forecast_col3:
            st.markdown('<div class="citescore-forecast-box">', unsafe_allow_html=True)
            st.metric("Оптимистичный", f"{result['citescore_forecasts']['optimistic']:.3f}")
            st.markdown('</div>', unsafe_allow_html=True)
    
    # Доверительные интервалы для CiteScore (только для точного анализа)
    if is_precise_mode:
        st.markdown("#### Доверительные интервалы CiteScore (95%)")
        cs_ci_lower = result['citescore_forecasts_ci']['lower_95']
        cs_ci_upper = result['citescore_forecasts_ci']['upper_95']
        
        st.info(f"**Диапазон:** [{cs_ci_lower:.3f} - {cs_ci_upper:.3f}]")

def display_detailed_analysis(result):
    """Отображение детального анализа (только для точного режима)"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Распределение цитирований")
        
        if result['if_citation_data']:
            if_data = pd.DataFrame(result['if_citation_data'])
            st.dataframe(if_data, use_container_width=True)
        else:
            st.info("Нет данных о цитированиях для импакт-фактора")
    
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
    
    # Временная модель
    if result['citation_model_data']:
        st.subheader("📅 Временная модель цитирований")
        st.info(f"Построена модель на основе {len(result['citation_model_data'])} лет исторических данных")

def display_statistics(result):
    """Отображение статистики"""
    
    st.subheader("📊 Статистика по статьям")
    
    # Статистика для импакт-фактора
    if result['if_citation_data']:
        st.markdown("#### Для импакт-фактора")
        df_if = pd.DataFrame(result['if_citation_data'])
        if_stats = df_if.groupby('Год публикации')['Цитирования'].agg([
            ('Количество статей', 'count'),
            ('Всего цитирований', 'sum'),
            ('Среднее цитирований', 'mean'),
            ('Стандартное отклонение', 'std')
        ]).round(2)
        st.dataframe(if_stats, use_container_width=True)
    else:
        st.info("Нет данных о статьях для импакт-фактора")
    
    # Статистика для CiteScore
    if result['cs_citation_data']:
        st.markdown("#### Для CiteScore")
        df_cs = pd.DataFrame(result['cs_citation_data'])
        cs_stats = df_cs.groupby('Год публикации')['Цитирования'].agg([
            ('Количество статей', 'count'),
            ('Всего цитирований', 'sum'),
            ('Среднее цитирований', 'mean'),
            ('Стандартное отклонение', 'std')
        ]).round(2)
        st.dataframe(cs_stats, use_container_width=True)
    else:
        st.info("Нет данных о статьях для CiteScore")

def display_parameters(result, is_precise_mode):
    """Отображение параметров расчета"""
    
    st.subheader("⚙️ Параметры расчета")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Периоды расчета:**")
        if 'if_details' in result and 'periods' in result['if_details']:
            st.write(f"- Импакт-фактор: {result['if_details']['periods']['articles']}")
            st.write(f"- Цитирования IF: {result['if_details']['periods']['citations']}")
        else:
            st.write(f"- Импакт-фактор: {result['if_publication_years'][0]}-{result['if_publication_years'][1]}")
        
        if 'cs_details' in result and 'periods' in result['cs_details']:
            st.write(f"- CiteScore: {result['cs_details']['periods']['articles']}")
            st.write(f"- Цитирования CS: {result['cs_details']['periods']['citations']}")
        else:
            st.write(f"- CiteScore: {result['cs_publication_years'][0]}-{result['cs_publication_years'][-1]}")
        
        st.markdown("**Анализ самоцитирований:**")
        st.write(f"- Уровень самоцитирований: {result['self_citation_rate']:.1%}")
        st.write(f"- Примерное количество: {result['total_self_citations']}")
    
    with col2:
        st.markdown("**Дата анализа:**")
        st.write(result['analysis_date'].strftime('%d.%m.%Y'))
        
        st.markdown("**Коэффициенты прогноза:**")
        st.write(f"- Консервативный: {result['multipliers']['conservative']:.2f}x")
        st.write(f"- Сбалансированный: {result['multipliers']['balanced']:.2f}x")
        st.write(f"- Оптимистичный: {result['multipliers']['optimistic']:.2f}x")
        
        if is_precise_mode:
            st.markdown("**Качество анализа:**")
            st.success("✅ Полный анализ с временными моделями")
        else:
            st.markdown("**Качество анализа:**")
            mode_text = "🔄 Динамический (реальные периоды)" if 'mode' in result and result['mode'] == 'DYNAMIC_CURRENT_DATE' else "🚀 Быстрый"
            st.info(f"ℹ️ {mode_text} анализ")

if __name__ == "__main__":
    main()
