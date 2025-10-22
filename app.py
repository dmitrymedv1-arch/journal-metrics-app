import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Импорт нашей логики анализа
from journal_analyzer import (
    get_issn_by_name, 
    calculate_metrics_enhanced,
    detect_journal_field,
    on_clear_cache_clicked
)

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
    # Заголовок приложения
    st.markdown('<h1 class="main-header">📊 Усовершенствованный Анализатор Метрик Журнала</h1>', unsafe_allow_html=True)
    
    # Информация о системе
    with st.expander("ℹ️ О системе анализа"):
        st.markdown("""
        **Реализованные улучшения:**
        - ✅ Реальный анализ самоцитирований через reference-list
        - ✅ Временная модель на исторических данных
        - ✅ Коррекция задержек индексации цитирований
        - ✅ Доверительные интервалы (бутстрэп-метод)
        - ✅ Исключение некорректных типов статей
        - ✅ Мульти-источниковая верификация данных
        - ✅ Автоматическое определение области журнала
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
        analysis_type = st.selectbox(
            "Тип анализа:",
            ["Полный анализ", "Быстрый анализ", "Детальный анализ с верификацией"]
        )
        
        # Кнопка запуска анализа
        analyze_button = st.button(
            "🚀 Запустить анализ",
            type="primary",
            use_container_width=True
        )
        
        # Кнопка очистки кэша
        if st.button("🧹 Очистить кэш", use_container_width=True):
            on_clear_cache_clicked(None)
            st.success("Кэш успешно очищен!")
        
        st.markdown("---")
        st.markdown("""
        **Поддерживаемые источники данных:**
        - Crossref API
        - OpenAlex API
        - Кэшированные исторические данные
        """)
    
    # Основная область контента
    if analyze_button:
        if not issn_input and not journal_name_input:
            st.error("❌ Пожалуйста, введите ISSN или название журнала")
            return
        
        # Показываем индикатор загрузки
        with st.spinner("🔄 Запуск усовершенствованного анализа..."):
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
                    st.write("📊 Анализ цитирований и самоцитирований...")
                    st.write("📈 Построение прогнозных моделей...")
                    
                    result = calculate_metrics_enhanced(issn, journal_name, use_cache)
                    
                    if result is None:
                        st.error("Не удалось получить данные для анализа.")
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
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Основные метрики", 
        "🔍 Детальный анализ", 
        "📊 Статистика", 
        "📅 Сезонность",
        "⚙️ Параметры"
    ])
    
    with tab1:
        display_main_metrics(result)
    
    with tab2:
        display_detailed_analysis(result)
    
    with tab3:
        display_statistics(result)
    
    with tab4:
        display_seasonality_analysis(result)
    
    with tab5:
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
    
    # Доверительные интервалы
    st.markdown("#### Доверительные интервалы (95%)")
    ci_lower = result['if_forecasts_ci']['lower_95']
    ci_upper = result['if_forecasts_ci']['upper_95']
    
    st.info(f"**Диапазон:** [{ci_lower:.2f} - {ci_upper:.2f}]")
    
    # Аналогично для CiteScore
    st.subheader("📊 CiteScore 2025")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Текущий CiteScore", f"{result['current_citescore']:.2f}")
    
    with col2:
        st.metric("Сбалансированный прогноз", f"{result['citescore_forecasts']['balanced']:.2f}")
    
    with col3:
        st.metric("Статьи для расчета", f"{result['total_articles_cs']}")

def display_detailed_analysis(result):
    """Отображение детального анализа"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Распределение цитирований")
        
        # Создаем DataFrame для визуализации
        if_data = pd.DataFrame(result['if_citation_data'])
        if not if_data.empty:
            fig = px.histogram(if_data, x='Цитирования', 
                             title='Распределение цитирований для ИФ',
                             nbins=20)
            st.plotly_chart(fig, use_container_width=True)
    
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

def display_seasonality_analysis(result):
    """Анализ сезонности"""
    
    st.subheader("📅 Сезонность цитирований")
    
    # Создаем график сезонности
    months = list(range(1, 13))
    month_names = [calendar.month_name[i] for i in months]
    coefficients = [result['seasonal_coefficients'].get(i, 0) for i in months]
    
    fig = go.Figure(data=[
        go.Bar(x=month_names, y=coefficients, 
               marker_color='#1E88E5',
               name='Коэффициент цитирования')
    ])
    
    fig.update_layout(
        title='Распределение цитирований по месяцам',
        xaxis_title='Месяц',
        yaxis_title='Коэффициент',
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Информация о коэффициентах нормализации
    st.subheader("📈 Коэффициенты нормализации")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Консервативный", f"{result['multipliers']['conservative']:.2f}x")
    with col2:
        st.metric("Сбалансированный", f"{result['multipliers']['balanced']:.2f}x")
    with col3:
        st.metric("Оптимистичный", f"{result['multipliers']['optimistic']:.2f}x")

def display_parameters(result):
    """Отображение параметров расчета"""
    
    st.subheader("⚙️ Параметры расчета")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Периоды расчета:**")
        st.write(f"- Импакт-фактор: {result['if_publication_years'][0]}-{result['if_publication_years'][1]}")
        st.write(f"- CiteScore: {result['cs_publication_years'][0]}-{result['cs_publication_years'][-1]}")
        
        st.markdown("**Качество модели:**")
        st.write(f"- Использовано лет для модели: {len(result['citation_model_data'])}")
        st.write(f"- Размер бутстрэп-выборки: 1000 итераций")
        st.write(f"- Уровень доверия: 95%")
    
    with col2:
        st.markdown("**Дата анализа:**")
        st.write(result['analysis_date'].strftime('%d.%m.%Y'))
        
        if result['bootstrap_stats']['if_mean'] > 0:
            if_cv = result['bootstrap_stats']['if_upper'] / result['bootstrap_stats']['if_mean'] - 1
            st.metric("Коэффициент вариации ИФ", f"{if_cv:.1%}")

if __name__ == "__main__":
    main()