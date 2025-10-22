import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime
import calendar
import sys
import os

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
        get_issn_by_name, 
        calculate_metrics_enhanced,
        detect_journal_field,
        on_clear_cache_clicked
    )
    JOURNAL_ANALYZER_AVAILABLE = True
except ImportError as e:
    JOURNAL_ANALYZER_AVAILABLE = False
    st.error(f"Ошибка импорта journal_analyzer: {e}")
    # Создаем заглушки
    def get_issn_by_name(*args, **kwargs):
        return None, None
    def calculate_metrics_enhanced(*args, **kwargs):
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
    }
    .warning-box {
        background-color: #fff3cd;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #ffc107;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

def main():
    if not JOURNAL_ANALYZER_AVAILABLE:
        st.warning("⚠️ Работает в упрощенном режиме. Некоторые функции могут быть ограничены.")
    
    # Заголовок приложения
    st.markdown('<h1 class="main-header">📊 Анализатор Метрик Журнала</h1>', unsafe_allow_html=True)
    
    # Информация о системе
    with st.expander("ℹ️ О системе анализа"):
        st.markdown("""
        **Возможности системы:**
        - ✅ Расчет текущих значений импакт-фактора и CiteScore
        - 🔮 Прогнозирование метрик на конец года
        - 🔍 Анализ самоцитирований
        - 📊 Статистика по статьям
        - 🎯 Автоматическое определение области журнала
        """)
    
    # Боковая панель для ввода данных
    with st.sidebar:
        st.header("🔍 Параметры анализа")
        
        input_type = st.radio(
            "Тип ввода:",
            ["ISSN журнала", "Название журнала"]
        )
        
        if input_type == "ISSN журнала":
            issn_input = st.text_input(
                "ISSN (формат: XXXX-XXXX):",
                value="2411-1414",
                placeholder="Например: 1548-7660"
            )
            journal_name_input = ""
        else:
            journal_name_input = st.text_input(
                "Название журнала на английском:",
                value="Nature",
                placeholder="Например: Nature или Science"
            )
            issn_input = ""
        
        use_cache = st.checkbox("Использовать кэш", value=True)
        
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
        - Кэшированные данные
        """)
    
    # Основная область контента
    if analyze_button:
        if not issn_input and not journal_name_input:
            st.error("❌ Пожалуйста, введите ISSN или название журнала")
            return
        
        # Показываем индикатор загрузки
        with st.spinner("🔄 Запуск анализа..."):
            try:
                # Получаем ISSN если введено название
                if journal_name_input and not issn_input:
                    with st.status("Поиск журнала...", expanded=True) as status:
                        st.write(f"Поиск ISSN для: {journal_name_input}")
                        issn, journal_name = get_issn_by_name(journal_name_input, use_cache)
                        if issn:
                            st.success(f"Найден журнал: {journal_name} (ISSN: {issn})")
                            status.update(label="Журнал найден!", state="complete")
                        else:
                            st.error("Журнал не найден. Проверьте название.")
                            return
                else:
                    issn = issn_input
                    journal_name = "Не указано"
                
                # Запускаем основной анализ
                with st.status("Выполнение анализа...", expanded=True) as status:
                    st.write("🔍 Сбор данных о статьях...")
                    st.write("📊 Анализ цитирований...")
                    st.write("📈 Построение прогнозов...")
                    
                    result = calculate_metrics_enhanced(issn, journal_name, use_cache)
                    
                    if result is None:
                        st.error("Не удалось получить данные для анализа. Возможно, журнал не найден или нет данных о статьях.")
                        return
                    
                    status.update(label="Анализ завершен!", state="complete")
                
                # Отображаем результаты
                display_results(result)
                
            except Exception as e:
                st.error(f"Произошла ошибка при анализе: {str(e)}")
                st.info("Попробуйте еще раз или используйте другой идентификатор журнала")

def display_results(result):
    """Функция для отображения результатов анализа"""
    
    # Основная информация о журнале
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Название журнала", result['journal_name'])
    with col2:
        st.metric("ISSN", result['issn'])
    with col3:
        st.metric("Область", result['journal_field'])
    
    st.markdown("---")
    
    # Вкладки для разных разделов результатов
    tab1, tab2, tab3 = st.tabs([
        "📈 Основные метрики", 
        "📊 Статистика", 
        "⚙️ Параметры"
    ])
    
    with tab1:
        display_main_metrics(result)
    
    with tab2:
        display_statistics(result)
    
    with tab3:
        display_parameters(result)

def display_main_metrics(result):
    """Отображение основных метрик"""
    
    st.subheader("🎯 Импакт-Фактор 2025")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Текущий ИФ", 
            f"{result['current_if']:.2f}",
            help="Текущее значение на основе собранных данных"
        )
    
    with col2:
        st.metric(
            "Сбалансированный прогноз", 
            f"{result['if_forecasts']['balanced']:.2f}",
            help="Прогноз на конец 2025 года"
        )
    
    with col3:
        st.metric(
            "Статьи для расчета", 
            f"{result['total_articles_if']}",
            help=f"Статьи за {result['if_publication_years'][0]}-{result['if_publication_years'][1]}"
        )
    
    # Прогнозы импакт-фактора
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
    
    # Аналогично для CiteScore
    st.subheader("📊 CiteScore 2025")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Текущий CiteScore", f"{result['current_citescore']:.2f}")
    
    with col2:
        st.metric("Сбалансированный прогноз", f"{result['citescore_forecasts']['balanced']:.2f}")
    
    with col3:
        st.metric("Статьи для расчета", f"{result['total_articles_cs']}")

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

def display_parameters(result):
    """Отображение параметров расчета"""
    
    st.subheader("⚙️ Параметры расчета")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Периоды расчета:**")
        st.write(f"- Импакт-фактор: {result['if_publication_years'][0]}-{result['if_publication_years'][1]}")
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

if __name__ == "__main__":
    main()
