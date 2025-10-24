import streamlit as st
import pandas as pd
from journal_analyzer import (
    calculate_metrics_fast,
    calculate_metrics_enhanced,
    calculate_metrics_dynamic,
    validate_issn,
    get_journal_name_from_issn,
    clear_cache
)
from datetime import date
import base64
import os

# Настройка страницы
st.set_page_config(page_title="Анализ журналов 📊", page_icon="📊", layout="wide")

# Стили CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5em;
        color: #2c3e50;
        text-align: center;
        margin-bottom: 20px;
    }
    .section-header {
        font-size: 1.8em;
        color: #34495e;
        margin-top: 20px;
    }
    .journal-name-box {
        background-color: #e8f4f8;
        padding: 10px;
        border-radius: 5px;
        margin-bottom: 15px;
    }
    .forecast-box {
        background-color: #d4edda;
        padding: 10px;
        border-radius: 5px;
    }
    .citescore-forecast-box {
        background-color: #d1ecf1;
        padding: 10px;
        border-radius: 5px;
    }
    .stButton>button {
        background-color: #007bff;
        color: white;
        border-radius: 5px;
    }
    .stButton>button:hover {
        background-color: #0056b3;
    }
</style>
""", unsafe_allow_html=True)

# Заголовок приложения
st.markdown('<h1 class="main-header">📊 Анализ метрик научных журналов</h1>', unsafe_allow_html=True)

# Инициализация состояния прогресс-бара
if 'progress' not in st.session_state:
    st.session_state.progress = 0.0

# Функция для обновления прогресс-бара
def update_progress(progress):
    st.session_state.progress = progress
    progress_bar.progress(progress)

# Функция для отображения основных метрик
def display_main_metrics(result, is_precise_mode, is_dynamic_mode):
    """Отображение основных метрик"""
    
    st.markdown('<h3 class="section-header">🎯 Импакт-Фактор</h3>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Текущий ИФ", 
            f"{result.get('current_if', 0):.2f}",
            help="Текущее значение на основе цитирований в периоде"
        )
    
    with col2:
        st.metric(
            "Статьи для расчета", 
            f"{result.get('total_articles_if', 0)}",
            help=f"Статьи за {result.get('if_publication_period', [2023, 2024])[0]}–{result.get('if_publication_period', [2023, 2024])[1]}" if is_dynamic_mode else f"Статьи за {result.get('if_publication_years', [2023, 2024])[0]}–{result.get('if_publication_years', [2023, 2024])[1]}"
        )
    
    with col3:
        st.metric(
            "Цитирований", 
            f"{result.get('total_cites_if', 0)}",
            help="Цитирования за 2025 год" if is_precise_mode else f"Цитирования за {result.get('if_citation_period', [2023, 2024])[0]}–{result.get('if_citation_period', [2023, 2024])[1]}" if is_dynamic_mode else f"Цитирования за {result.get('if_publication_years', [2023, 2024])[0]}–{result.get('if_publication_years', [2023, 2024])[1]}"
        )
    
    if is_precise_mode and not is_dynamic_mode:
        st.markdown("#### Прогнозы Импакт-Фактора на конец 2025")
        forecast_col1, forecast_col2, forecast_col3 = st.columns(3)
        
        with forecast_col1:
            st.markdown('<div class="forecast-box">', unsafe_allow_html=True)
            st.metric("Консервативный", f"{result.get('if_forecasts', {}).get('conservative', 0):.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with forecast_col2:
            st.markdown('<div class="forecast-box">', unsafe_allow_html=True)
            st.metric("Сбалансированный", f"{result.get('if_forecasts', {}).get('balanced', 0):.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with forecast_col3:
            st.markdown('<div class="forecast-box">', unsafe_allow_html=True)
            st.metric("Оптимистичный", f"{result.get('if_forecasts', {}).get('optimistic', 0):.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.markdown('<h3 class="section-header">📊 CiteScore</h3>', unsafe_allow_html=True)
    
    if is_dynamic_mode:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "CiteScore (OpenAlex)", 
                f"{result.get('current_citescore_openalex', 0):.2f}",
                help="На основе цитирований OpenAlex за период 52–4 месяцев назад"
            )
        with col2:
            st.metric(
                "CiteScore (Crossref)", 
                f"{result.get('current_citescore_crossref', 0):.2f}",
                help="На основе всех цитирований Crossref"
            )
        with col3:
            st.metric(
                "Статьи для расчета", 
                f"{result.get('total_articles_cs', 0)}",
                help=f"Статьи за {result.get('cs_publication_period', [2021, 2025])[0]}–{result.get('cs_publication_period', [2021, 2025])[1]}"
            )
        with col4:
            st.metric(
                "Цитирований (OpenAlex)", 
                f"{result.get('total_cites_cs_openalex', 0)}",
                help=f"Цитирования за {result.get('cs_citation_period', [2021, 2025])[0]}–{result.get('cs_citation_period', [2021, 2025])[1]}"
            )
        
        # Отображение таблицы cs_citation_data
        if result.get('cs_citation_data'):
            st.markdown("#### Детализация цитирований CiteScore")
            cs_df = pd.DataFrame(result['cs_citation_data'])
            cs_df = cs_df.rename(columns={
                'DOI': 'DOI',
                'Дата публикации': 'Дата публикации',
                'Цитирования (Crossref)': 'Цитирования (Crossref)',
                'Цитирования (OpenAlex)': 'Цитирования (OpenAlex)',
                'Самоцитирования (OpenAlex)': 'Самоцитирования (OpenAlex)',
                'Цитирования в периоде 52–4 месяцев назад': 'Цитирования в периоде (52–4 мес.)'
            })
            st.dataframe(cs_df, use_container_width=True)
        else:
            st.warning("⚠️ Нет данных для таблицы CiteScore. Проверьте наличие статей за период 52–4 месяцев назад.")
    
    else:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                "Текущий CiteScore", 
                f"{result.get('current_citescore', 0):.2f}",
                help="На основе цитирований за 18–6 месяцев назад" if is_precise_mode else "На основе цитирований за последние годы"
            )
        
        with col2:
            st.metric(
                "Статьи для расчета", 
                f"{result.get('total_articles_cs', 0)}",
                help=f"Статьи за {result.get('cs_publication_period', [2021, 2024])[0]}–{result.get('cs_publication_period', [2021, 2024])[-1]}" if is_dynamic_mode else f"Статьи за {result.get('cs_publication_years', [2021, 2024])[0]}–{result.get('cs_publication_years', [2021, 2024])[-1]}"
            )
        
        with col3:
            st.metric(
                "Цитирований", 
                f"{result.get('total_cites_cs', 0)}",
                help=f"Цитирования за {result.get('cs_citation_period', [2021, 2024])[0]}–{result.get('cs_citation_period', [2021, 2024])[-1]}" if is_dynamic_mode else f"Цитирования за {result.get('cs_publication_years', [2021, 2024])[0]}–{result.get('cs_publication_years', [2021, 2024])[-1]}"
            )
        
        # Отображение таблицы cs_citation_data
        if result.get('cs_citation_data'):
            st.markdown("#### Детализация цитирований CiteScore")
            cs_df = pd.DataFrame(result['cs_citation_data'])
            cs_df = cs_df.rename(columns={
                'DOI': 'DOI',
                'Дата публикации': 'Дата публикации',
                'Цитирования (Crossref)': 'Цитирования (Crossref)',
                'Цитирования (OpenAlex)': 'Цитирования (OpenAlex)',
                'Самоцитирования (OpenAlex)': 'Самоцитирования (OpenAlex)',
                'Цитирования в периоде 18–6 месяцев назад': 'Цитирования в периоде'
            })
            st.dataframe(cs_df, use_container_width=True)
        else:
            st.warning("⚠️ Нет данных для таблицы CiteScore. Проверьте наличие статей за указанный период.")
    
    if is_precise_mode and not is_dynamic_mode:
        st.markdown("#### Прогнозы CiteScore на конец 2025")
        forecast_col1, forecast_col2, forecast_col3 = st.columns(3)
        
        with forecast_col1:
            st.markdown('<div class="citescore-forecast-box">', unsafe_allow_html=True)
            st.metric("Консервативный", f"{result.get('citescore_forecasts', {}).get('conservative', 0):.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with forecast_col2:
            st.markdown('<div class="citescore-forecast-box">', unsafe_allow_html=True)
            st.metric("Сбалансированный", f"{result.get('citescore_forecasts', {}).get('balanced', 0):.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with forecast_col3:
            st.markdown('<div class="citescore-forecast-box">', unsafe_allow_html=True)
            st.metric("Оптимистичный", f"{result.get('citescore_forecasts', {}).get('optimistic', 0):.2f}")
            st.markdown('</div>', unsafe_allow_html=True)

# Функция для отображения детального анализа
def display_detailed_analysis(result, is_dynamic_mode):
    """Отображение детального анализа"""
    
    st.markdown('<h3 class="section-header">🔍 Детальный анализ</h3>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Самоцитирования")
        st.metric("Доля самоцитирований (ИФ)", f"{result.get('self_citation_rate_if', 0):.2%}",
                  help="Доля самоцитирований в общем объеме цитирований для ИФ")
        st.metric("Доля самоцитирований (CiteScore)", f"{result.get('self_citation_rate_cs', 0):.2%}",
                  help="Доля самоцитирований в общем объеме цитирований для CiteScore")
    
    with col2:
        st.markdown("#### Сезонные коэффициенты")
        if result.get('citation_distribution'):
            dist_df = pd.DataFrame.from_dict(
                result['citation_distribution'], orient='index', columns=['Коэффициент']
            ).reset_index().rename(columns={'index': 'Месяц'})
            st.dataframe(dist_df, use_container_width=True)
        else:
            st.warning("⚠️ Нет данных о сезонных коэффициентах")
    
    # Таблица детализации цитирований для ИФ
    if result.get('if_citation_data'):
        st.markdown("#### Детализация цитирований Импакт-Фактора")
        if_df = pd.DataFrame(result['if_citation_data'])
        if_df = if_df.rename(columns={
            'DOI': 'DOI',
            'Дата публикации': 'Дата публикации',
            'Цитирования': 'Цитирования',
            'Самоцитирования': 'Самоцитирования'
        })
        st.dataframe(if_df, use_container_width=True)
    else:
        st.warning("⚠️ Нет данных для таблицы Импакт-Фактора. Проверьте наличие статей за указанный период.")

# Функция для экспорта результатов в CSV
def export_to_csv(result):
    """Экспорт результатов в CSV"""
    if result.get('if_citation_data'):
        if_df = pd.DataFrame(result['if_citation_data'])
        if_df['Тип'] = 'Импакт-Фактор'
    else:
        if_df = pd.DataFrame()
    
    if result.get('cs_citation_data'):
        cs_df = pd.DataFrame(result['cs_citation_data'])
        cs_df['Тип'] = 'CiteScore'
    else:
        cs_df = pd.DataFrame()
    
    combined_df = pd.concat([if_df, cs_df], ignore_index=True)
    
    if not combined_df.empty:
        csv = combined_df.to_csv(index=False, encoding='utf-8-sig')
        b64 = base64.b64encode(csv.encode('utf-8-sig')).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="journal_analysis_{result.get("issn", "unknown")}.csv">Скачать результаты в CSV</a>'
        st.markdown(href, unsafe_allow_html=True)
    else:
        st.warning("⚠️ Нет данных для экспорта")

# Основная функция
def main():
    # Боковая панель
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
        else:
            detected_name = "Не указано"
        
        journal_field = st.selectbox(
            "Область журнала:",
            options=["natural_sciences", "social_sciences", "mathematics", "biological_sciences", "general"],
            format_func=lambda x: {
                "natural_sciences": "Естественные науки",
                "social_sciences": "Социологические науки",
                "mathematics": "Математические науки",
                "biological_sciences": "Биологические науки",
                "general": "Общая"
            }[x],
            help="Выберите область журнала для точного расчета сезонных коэффициентов"
        )
        
        analysis_mode = st.radio(
            "Режим анализа:",
            ["🚀 Быстрый анализ (Fast Analysis)",
             "🎯 Точный анализ (Precise Analysis)",
             "🌐 Динамический анализ (Dynamic Analysis)"],
            help="Быстрый: 10-30 сек, Точный/Динамический: 30-60 сек"
        )
        
        use_cache = st.checkbox("Использовать кэш", value=True, help="Использовать кэшированные данные для ускорения")
        
        use_parallel = st.checkbox("Параллельная обработка", value=True, help="Использовать многопоточность для ускорения")
        
        max_workers = st.slider("Максимальное количество потоков:", min_value=1, max_value=50, value=20, help="Количество потоков для параллельной обработки")
        
        if st.button("🗑 Очистить кэш"):
            clear_cache()
            st.success("Кэш очищен!")
        
        st.markdown("---")
        st.markdown("**ℹ️ Инструкции:**")
        st.markdown("- Введите ISSN в формате XXXX-XXXX.")
        st.markdown("- Выберите режим анализа.")
        st.markdown("- Для точного анализа требуется больше времени.")
        st.markdown("- Динамический анализ использует гибкие периоды.")
    
    # Прогресс-бар
    progress_bar = st.progress(st.session_state.progress)
    
    # Кнопка для запуска анализа
    if st.button("🚀 Начать анализ"):
        if not validate_issn(issn_input):
            st.error("❌ Неверный формат ISSN. Используйте формат XXXX-XXXX.")
            return
        
        real_journal_name = detected_name
        is_precise_mode = "Точный анализ" in analysis_mode
        is_dynamic_mode = "Динамический анализ" in analysis_mode
        
        try:
            with st.spinner("⏳ Выполняется анализ..."):
                if is_dynamic_mode:
                    result = calculate_metrics_dynamic(
                        issn_input, 
                        real_journal_name, 
                        use_cache, 
                        progress_callback=update_progress,
                        use_parallel=use_parallel,
                        max_workers=max_workers,
                        journal_field=journal_field
                    )
                elif is_precise_mode:
                    result = calculate_metrics_enhanced(
                        issn_input, 
                        real_journal_name, 
                        use_cache, 
                        progress_callback=update_progress,
                        use_parallel=use_parallel,
                        max_workers=max_workers,
                        journal_field=journal_field
                    )
                else:
                    result = calculate_metrics_fast(
                        issn_input, 
                        real_journal_name, 
                        use_cache, 
                        progress_callback=update_progress
                    )
            
            if result is None:
                st.error("❌ Не удалось получить данные для анализа. Проверьте ISSN или наличие статей в Crossref.")
                st.info("Попробуйте использовать другой ISSN (например, 0028-0836 для Nature) или очистить кэш.")
                st.markdown("**Возможные причины ошибки:**")
                st.markdown("- Журнал не имеет статей за указанные периоды в Crossref.")
                st.markdown("- Проблемы с API (например, ограничения запросов).")
                st.markdown("- Устаревший кэш. Попробуйте очистить кэш.")
                st.markdown("- Проверьте наличие статей за период 2023–2024 (для ИФ) или 2021–2025 (для CiteScore).")
                return
            
            # Отображение результатов
            st.markdown(f"**Анализ журнала:** {result.get('journal_name', 'Не указано')} (ISSN: {result.get('issn', 'Не указано')})")
            st.markdown(f"**Дата анализа:** {result.get('analysis_date', date.today())}")
            st.markdown(f"**Режим анализа:** {result.get('mode', 'Не указан')}")
            st.markdown(f"**Область журнала:** {journal_field.replace('_', ' ').title()}")
            
            # Вкладки для результатов
            tab1, tab2 = st.tabs(["📊 Основные метрики", "🔍 Детальный анализ"])
            
            with tab1:
                display_main_metrics(result, is_precise_mode, is_dynamic_mode)
            
            with tab2:
                display_detailed_analysis(result, is_dynamic_mode)
            
            # Кнопка экспорта
            st.markdown("---")
            st.markdown("#### 💾 Экспорт результатов")
            export_to_csv(result)
        
        except Exception as e:
            st.error(f"❌ Произошла ошибка при анализе: {str(e)}")
            st.info("Попробуйте очистить кэш или использовать другой ISSN (например, 0028-0836 для Nature).")
            st.markdown("**Возможные причины ошибки:**")
            st.markdown("- Проблемы с API Crossref или OpenAlex.")
            st.markdown("- Устаревший кэш. Попробуйте очистить кэш.")
            st.markdown("- Проверьте наличие статей за указанные периоды.")
            st.markdown(f"**Подробности ошибки:** {str(e)}")
        
        finally:
            st.session_state.progress = 1.0
            progress_bar.progress(1.0)

# Запуск приложения
if __name__ == "__main__":
    main()
