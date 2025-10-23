with col1:
        st.markdown("**Периоды расчета:**")
        if is_dynamic_mode:
            st.write(f"- ИФ (статьи): {result['if_publication_period'][0]}–{result['if_publication_period'][1]}")
            st.write(f"- ИФ (цитирования): {result['if_citation_period'][0]}–{result['if_citation_period'][1]}")
            st.write(f"- CiteScore (статьи и цитирования): {result['cs_publication_period'][0]}–{result['cs_publication_period'][1]}")
        else:
            st.write(f"- Импакт-фактор: {result['if_publication_years'][0]}-{result['if_publication_years'][1]}")
            st.write(f"- CiteScore: {result['cs_publication_years'][0]}-{result['cs_publication_years'][-1]}")
        
        st.markdown("**Анализ самоцитирований:**")
        st.write(f"- Уровень самоцитирований: {result['self_citation_rate']:.1%}")
        st.write(f"- Примерное количество: {result['total_self_citations']}")
    
    with col2:
        st.markdown("**Дата анализа:**")
        st.write(result['analysis_date'].strftime('%d.%m.%Y'))
        
        if is_precise_mode and not is_dynamic_mode:
            st.markdown("**Коэффициенты прогноза:**")
            st.write(f"- Консервативный: {result['multipliers']['conservative']:.2f}x")
            st.write(f"- Сбалансированный: {result['multipliers']['balanced']:.2f}x")
            st.write(f"- Оптимистичный: {result['multipliers']['optimistic']:.2f}x")
        
        st.markdown("**Качество анализа:**")
        if is_dynamic_mode:
            st.success("✅ Динамический анализ с OpenAlex для ИФ и CiteScore")
        elif is_precise_mode:
            st.success("✅ Полный анализ с OpenAlex для ИФ и Crossref для CiteScore")
        else:
            st.info("ℹ️ Быстрый анализ через Crossref")

if __name__ == "__main__":
    main()
