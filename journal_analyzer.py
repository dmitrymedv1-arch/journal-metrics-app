import requests
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import time
import calendar
from collections import defaultdict
import pickle
import hashlib
import os
import warnings
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from functools import partial
warnings.filterwarnings('ignore')

base_url_crossref = "https://api.crossref.org/works"
base_url_openalex = "https://api.openalex.org/works"
CACHE_DIR = "journal_analysis_cache"
CACHE_DURATION = timedelta(hours=24)

def validate_issn(issn):
    """Проверка формата ISSN"""
    if not issn:
        return False
    pattern = r'^\d{4}-\d{3}[\dXx]$'
    return re.match(pattern, issn) is not None

def ensure_cache_dir():
    """Создает директорию для кэша если её нет"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def get_cache_key(*args):
    """Генерирует ключ кэша на основе аргументов"""
    key_string = "_".join(str(arg) for arg in args)
    return hashlib.md5(key_string.encode()).hexdigest()

def save_to_cache(data, cache_key):
    """Сохраняет данные в кэш"""
    ensure_cache_dir()
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    cache_data = {
        'data': data,
        'timestamp': datetime.now()
    }
    with open(cache_file, 'wb') as f:
        pickle.dump(cache_data, f)

def load_from_cache(cache_key):
    """Загружает данные из кэша"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, 'rb') as f:
            cache_data = pickle.load(f)
        if datetime.now() - cache_data['timestamp'] < CACHE_DURATION:
            print(f"Загружен кэш для ключа: {cache_key}")
            return cache_data['data']
        else:
            os.remove(cache_file)
            return None
    except:
        return None

def get_journal_name_from_issn(issn, use_cache=True):
    """
    Определяет правильное название журнала по ISSN:
    1. Сначала через Crossref API
    2. Если не найдено - через OpenAlex API
    3. Возвращает fallback название
    """
    if not validate_issn(issn):
        return f"Журнал ISSN {issn}"
    
    cache_key = get_cache_key("journal_name", issn)
    if use_cache:
        cached_name = load_from_cache(cache_key)
        if cached_name:
            print(f"Название журнала из кэша: {cached_name}")
            return cached_name

    # 1. Попытка через Crossref
    try:
        print(f" Поиск журнала через Crossref: {issn}")
        params = {
            'filter': f'issn:{issn}',
            'rows': 1,
            'mailto': 'example@example.com'
        }
        response = requests.get(base_url_crossref, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data['message']['total-results'] > 0:
            journal_name = data['message']['items'][0].get('container-title', [f"Журнал ISSN {issn}"])[0]
            print(f" Найдено через Crossref: {journal_name}")
            save_to_cache(journal_name, cache_key)
            return journal_name

    except Exception as e:
        print(f" Ошибка Crossref для {issn}: {e}")

    # 2. Попытка через OpenAlex
    try:
        print(f" Поиск журнала через OpenAlex: {issn}")
        url = f"https://api.openalex.org/journals?filter=issn:{issn}&per-page=1"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data['results']:
            journal_name = data['results'][0].get('display_name', f"Журнал ISSN {issn}")
            print(f" Найдено через OpenAlex: {journal_name}")
            save_to_cache(journal_name, cache_key)
            return journal_name

    except Exception as e:
        print(f" Ошибка OpenAlex для {issn}: {e}")

    # 3. Fallback
    fallback_name = f"Журнал ISSN {issn}"
    print(f" Используется fallback название: {fallback_name}")
    save_to_cache(fallback_name, cache_key)
    return fallback_name

def parallel_fetch_citations_openalex(dois_list, citation_start_date, citation_end_date, max_workers=20, progress_callback=None):
    """
    ПАРАЛЛЕЛЬНОЕ получение цитирований через OpenAlex с ThreadPoolExecutor
    Ускорение до 5x по сравнению с последовательными запросами
    """
    results = {}
    total_dois = len(dois_list)
    processed = 0

    def fetch_single_citation(doi):
        """Обертка для одного DOI"""
        return fetch_citations_openalex(
            doi, 
            citation_start_date, 
            citation_end_date,
            update_progress=None
        )

    print(f" Запуск параллельного анализа {total_dois} DOI ({max_workers} потоков)")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_doi = {
            executor.submit(fetch_single_citation, doi): doi 
            for doi in dois_list
        }
        
        for future in as_completed(future_to_doi):
            doi = future_to_doi[future]
            try:
                result = future.result(timeout=120)
                results[doi] = result
                processed += 1
                
                if progress_callback and processed % 10 == 0:
                    progress = min(1.0, processed / total_dois)
                    progress_callback(progress)
                
                print(f" Обработан DOI {processed}/{total_dois}: {doi[:20]}...")
                
            except Exception as exc:
                print(f" Ошибка для DOI {doi}: {exc}")
                # ВОЗВРАЩАЕМ None вместо нулей, чтобы отличать ошибки от реального отсутствия цитирований
                results[doi] = None

    if progress_callback:
        progress_callback(1.0)

    print(f" Параллельный анализ завершен: {len([r for r in results.values() if r is not None])}/{total_dois} успешных DOI")
    return results

def validate_parallel_openalex(max_workers=20):
    """Проверяет возможность параллельных запросов к OpenAlex"""
    try:
        response = requests.get(f"{base_url_openalex}?per-page=1", timeout=10)
        response.raise_for_status()
    
        if max_workers > 50:
            print(" max_workers ограничен 50 для стабильности")
            return False, 50
        
        return True, max_workers
        
    except Exception as e:
        print(f" OpenAlex недоступен для параллелизации: {e}")
        return False, 1

def fetch_articles_enhanced(issn, from_date, until_date, use_cache=True, progress_callback=None):
    """Улучшенная функция для получения статей с пагинацией через Crossref"""
    if not validate_issn(issn):
        print(f"Неверный формат ISSN: {issn}")
        return []
    
    cache_key = get_cache_key("fetch_articles_enhanced", issn, from_date, until_date)
    if use_cache:
        cached_data = load_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

    items = []
    cursor = "*"
    excluded_types = {
        'editorial', 'letter', 'correction', 'retraction',
        'book-review', 'news', 'announcement', 'abstract'
    }

    total_pages = 10
    current_page = 0

    while True:
        params = {
            'filter': f'issn:{issn},from-pub-date:{from_date},until-pub-date:{until_date}',
            'rows': 1000,
            'cursor': cursor,
            'mailto': 'example@example.com'
        }
        try:
            print(f"fetch_articles_enhanced: Запрос страницы {current_page + 1} для ISSN {issn} ({from_date}–{until_date})")
            resp = requests.get(base_url_crossref, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            message = data['message']
            
            # УЛУЧШЕННАЯ ПРОВЕРКА: проверяем наличие статей и корректность данных
            if 'items' not in message or not message['items']:
                print(f"Crossref не вернул статьи для ISSN {issn} в периоде {from_date}–{until_date}")
                break
                
            filtered_items = []
            for item in message['items']:
                item_type = item.get('type', '').lower()
                print(f"Тип статьи: {item_type}, DOI: {item.get('DOI', 'N/A')}")
                
                # УЛУЧШЕННАЯ ФИЛЬТРАЦИЯ: более точная проверка типов
                if item_type not in excluded_types:
                    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: убедимся, что есть необходимые поля
                    if item.get('DOI') and item.get('published'):
                        filtered_items.append(item)
                    else:
                        print(f"Пропущена статья без DOI или даты публикации: {item.get('title', ['N/A'])[0]}")
                
            items.extend(filtered_items)
            print(f"fetch_articles_enhanced: Получено {len(filtered_items)} статей на странице {current_page + 1}")
            
            cursor = message.get('next-cursor')
            current_page += 1
            
            if progress_callback:
                progress = min(0.3 * current_page / total_pages, 0.3)
                progress_callback(progress)
                
            if not cursor or len(message['items']) == 0:
                print(f"fetch_articles_enhanced: Завершено, всего найдено {len(items)} статей")
                break
                
            time.sleep(0.5)
        except Exception as e:
            print(f"Ошибка в fetch_articles_enhanced для ISSN {issn}: {e}")
            break

    if use_cache and items:
        save_to_cache(items, cache_key)
    return items

def fetch_citations_openalex(doi, citation_start_date, citation_end_date, update_progress=None):
    """
    Получает цитирующие работы через OpenAlex API с пагинацией и фильтрацией по периоду.
    Возвращает словарь с количеством цитирований в указанном периоде и общим количеством.
    """
    cache_key = get_cache_key("fetch_citations_openalex", doi, citation_start_date, citation_end_date)
    cached_data = load_from_cache(cache_key)
    if cached_data is not None:
        return cached_data

    doi = doi.strip().replace('https://doi.org/', '') if doi.startswith('https://doi.org/') else doi.strip()
    work_url = f"{base_url_openalex}?filter=doi:{doi}"

    try:
        response = requests.get(work_url, timeout=30)
        response.raise_for_status()
        data = response.json()
        results = data.get('results', [])
        if not results:
            print(f"DOI {doi}: Не найдено в OpenAlex")
            save_to_cache({'doi': doi, 'count': 0, 'total_count': 0, 'all_citations': [], 'publication_year': None, 'found_in_openalex': False}, cache_key)
            return {'doi': doi, 'count': 0, 'total_count': 0, 'all_citations': [], 'publication_year': None, 'found_in_openalex': False}
        
        work_data = results[0]
        original_title = work_data.get('title', 'Нет названия')
        publication_year = work_data.get('publication_year', None)
        print(f"DOI {doi}: Найдена работа '{original_title[:50]}...', Год: {publication_year}")
        
        work_id = work_data['id']
        work_openalex_id = work_id.split('/')[-1]
        cited_by_count = work_data.get('cited_by_count', 0)
        print(f"DOI {doi}: Общее цитирований (OpenAlex): {cited_by_count}")
        
        citing_works = []
        page = 1
        next_cursor = None
        total_processed = 0
        
        while True:
            url = f"{base_url_openalex}?filter=cites:{work_openalex_id}&per-page=200"
            if next_cursor:
                url += f"&cursor={next_cursor}"
            try:
                response = requests.get(url, timeout=60)
                response.raise_for_status()
                data = response.json()
                results_count = len(data.get('results', []))
                print(f"DOI {doi}: Страница {page}, найдено {results_count} цитирований")
                
                for work in data['results']:
                    citing_doi = work.get('doi', '').replace('https://doi.org/', '') if work.get('doi') else 'Нет DOI'
                    citing_title = work.get('title', 'Нет названия')
                    publication_date_str = work.get('publication_date', 'Нет даты')
                    
                    # УЛУЧШЕННАЯ ФИЛЬТРАЦИЯ ДАТ: более надежная обработка
                    if publication_date_str != 'Нет даты':
                        try:
                            # Преобразуем строку даты в объект date
                            pub_date = datetime.strptime(publication_date_str, '%Y-%m-%d').date()
                            
                            # ПРОВЕРКА ДИАПАЗОНА ДАТ: убедимся, что даты корректны
                            if citation_start_date <= pub_date <= citation_end_date:
                                citing_works.append({
                                    'DOI': citing_doi,
                                    'Название статьи': citing_title,
                                    'Дата публикации': publication_date_str
                                })
                            else:
                                # Логируем отфильтрованные цитирования для отладки
                                if page == 1 and len(citing_works) == 0:
                                    print(f"DOI {doi}: Цитирование от {pub_date} вне периода {citation_start_date}-{citation_end_date}")
                                    
                        except ValueError as ve:
                            print(f"DOI {doi}: Ошибка формата даты '{publication_date_str}': {ve}")
                        except Exception as e:
                            print(f"DOI {doi}: Ошибка обработки даты: {e}")
                    
                    total_processed += 1
                
                next_cursor = data.get('meta', {}).get('next_cursor')
                if not next_cursor:
                    print(f"DOI {doi}: Достигнут конец списка, обработано {total_processed} цитирований")
                    break
                
                page += 1
                if update_progress and cited_by_count > 0:
                    progress = min(1.0, total_processed / cited_by_count)
                    update_progress(progress)
                time.sleep(0.3)
                
            except requests.exceptions.RequestException as e:
                print(f"DOI {doi}: Ошибка при запросе страницы {page}: {e}")
                break
            except Exception as e:
                print(f"DOI {doi}: Ошибка при обработке страницы {page}: {e}")
                break
        
        count_period = len(citing_works)
        print(f"DOI {doi}: Цитирований в периоде {citation_start_date}–{citation_end_date}: {count_period} из {cited_by_count}")
        
        result = {
            'doi': doi,
            'count': count_period,
            'total_count': cited_by_count,
            'all_citations': citing_works,
            'publication_year': publication_year,
            'found_in_openalex': True,
            'processed_successfully': True
        }
        save_to_cache(result, cache_key)
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"DOI {doi}: Ошибка OpenAlex API: {e}")
        return {'doi': doi, 'count': None, 'total_count': None, 'all_citations': [], 'publication_year': None, 'found_in_openalex': False, 'processed_successfully': False, 'error': str(e)}
    except Exception as e:
        print(f"DOI {doi}: Общая ошибка: {e}")
        return {'doi': doi, 'count': None, 'total_count': None, 'all_citations': [], 'publication_year': None, 'found_in_openalex': False, 'processed_successfully': False, 'error': str(e)}

def get_seasonal_coefficients(journal_field="general"):
    """Возвращает взвешенные коэффициенты на основе исторических данных"""
    seasonal_patterns = {
        "natural_sciences": {
            1: 0.85, 2: 1.05, 3: 1.25, 4: 1.15, 5: 1.00, 6: 0.95,
            7: 0.70, 8: 0.75, 9: 1.30, 10: 1.20, 11: 1.15, 12: 0.65
        },
        "general": {
            1: 0.90, 2: 1.15, 3: 1.20, 4: 1.15, 5: 1.00, 6: 1.00,
            7: 0.70, 8: 0.80, 9: 1.20, 10: 1.25, 11: 1.15, 12: 0.60
        }
    }
    return seasonal_patterns.get(journal_field, seasonal_patterns["general"])

def calculate_weighted_multiplier(current_date, seasonal_coefficients, method="balanced"):
    """Расчет взвешенного множителя"""
    current_year = current_date.year
    current_month = current_date.month
    days_passed = (current_date - date(current_year, 1, 1)).days + 1

    weighted_passed = 0
    for month in range(1, current_month + 1):
        _, month_days = calendar.monthrange(current_year, month)
        if month == current_month:
            month_days = current_date.day
        weighted_passed += seasonal_coefficients[month] * month_days

    total_weighted_year = sum(
        seasonal_coefficients[month] * calendar.monthrange(current_year, month)[1]
        for month in range(1, 13)
    )

    base_multiplier = total_weighted_year / weighted_passed if weighted_passed > 0 else 1.0

    if method == "conservative":
        return max(1.0, base_multiplier * 0.9)
    elif method == "optimistic":
        return max(1.0, base_multiplier * 1.1)
    else:
        return max(1.0, base_multiplier)

def detect_journal_field(issn, journal_name):
    """Автоматическое определение области журнала"""
    field_keywords = {
        "natural_sciences": ['nature', 'science', 'physical', 'chemistry', 'physics'],
        "general": ['general', 'techno', 'acta']
    }
    journal_name_lower = journal_name.lower()
    for field, keywords in field_keywords.items():
        for keyword in keywords:
            if keyword in journal_name_lower:
                return field
    return "general"

def calculate_metrics_fast(issn, journal_name="Не указано", use_cache=True):
    """БЫСТРАЯ функция для расчета метрик через Crossref"""
    try:
        current_date = date.today()
        current_year = current_date.year
        journal_field = detect_journal_field(issn, journal_name)

        if_publication_years = [current_year - 2, current_year - 1]
        cs_publication_years = list(range(current_year - 3, current_year + 1))

        if_items = []
        for year in if_publication_years:
            from_date = f"{year}-01-01"
            until_date = f"{year}-12-31"
            items = fetch_articles_enhanced(issn, from_date, until_date, use_cache)
            if_items.extend(items)

        cs_items = []
        for year in cs_publication_years:
            from_date = f"{year}-01-01"
            until_date = f"{year}-12-31"
            items = fetch_articles_enhanced(issn, from_date, until_date, use_cache)
            cs_items.extend(items)

        B_if = len(if_items)
        B_cs = len(cs_items)
        if B_if == 0 or B_cs == 0:
            print(f"calculate_metrics_fast: Нет статей для анализа: IF={B_if}, CS={B_cs}")
            return None

        A_if_current = sum(item.get('is-referenced-by-count', 0) for item in if_items)
        A_cs_current = sum(item.get('is-referenced-by-count', 0) for item in cs_items)

        current_if = A_if_current / B_if if B_if > 0 else 0
        current_citescore = A_cs_current / B_cs if B_cs > 0 else 0

        seasonal_coefficients = get_seasonal_coefficients(journal_field)
        multiplier = calculate_weighted_multiplier(current_date, seasonal_coefficients, "balanced")
        
        if_forecasts = {
            'conservative': current_if * max(1.0, multiplier * 0.9),
            'balanced': current_if * max(1.0, multiplier),
            'optimistic': current_if * max(1.0, multiplier * 1.1)
        }

        citescore_forecasts = {
            'conservative': current_citescore * max(1.0, multiplier * 0.9),
            'balanced': current_citescore * max(1.0, multiplier),
            'optimistic': current_citescore * max(1.0, multiplier * 1.1)
        }

        if_citation_data = [
            {
                'DOI': item.get('DOI', 'N/A'),
                'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                'Цитирования (Crossref)': item.get('is-referenced-by-count', 0),
                'Цитирования (OpenAlex)': 0,
                'Цитирования в периоде': 0,
                'has_doi': item.get('DOI') != 'N/A'
            } for item in if_items
        ]

        cs_citation_data = [
            {
                'DOI': item.get('DOI', 'N/A'),
                'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                'Цитирования (Crossref)': item.get('is-referenced-by-count', 0),
                'Цитирования (OpenAlex)': 0,
                'Цитирования в периоде': 0,
                'has_doi': item.get('DOI') != 'N/A'
            } for item in cs_items
        ]

        return {
            'current_if': current_if,
            'current_citescore': current_citescore,
            'if_forecasts': if_forecasts,
            'citescore_forecasts': citescore_forecasts,
            'multipliers': {
                'conservative': max(1.0, multiplier * 0.9),
                'balanced': max(1.0, multiplier),
                'optimistic': max(1.0, multiplier * 1.1)
            },
            'total_cites_if': A_if_current,
            'total_articles_if': B_if,
            'total_cites_cs': A_cs_current,
            'total_articles_cs': B_cs,
            'citation_distribution': dict(seasonal_coefficients),
            'if_citation_data': if_citation_data,
            'cs_citation_data': cs_citation_data,
            'analysis_date': current_date,
            'if_publication_years': if_publication_years,
            'cs_publication_years': cs_publication_years,
            'seasonal_coefficients': seasonal_coefficients,
            'journal_field': journal_field,
            'self_citation_rate': 0.05,
            'total_self_citations': int(A_if_current * 0.05),
            'issn': issn,
            'journal_name': journal_name,
            'citation_model_data': []
        }

    except Exception as e:
        print(f"Ошибка в calculate_metrics_fast: {e}")
        return None

def calculate_metrics_enhanced(issn, journal_name="Не указано", use_cache=True, progress_callback=None, use_parallel=True, max_workers=5):
    """УСОВЕРШЕНСТВОВАННАЯ функция для расчета метрик с OpenAlex для ИФ"""
    try:
        print(f"Запуск calculate_metrics_enhanced для ISSN {issn}")
        if not validate_issn(issn):
            print(f"Неверный формат ISSN: {issn}")
            return None

        parallel_ok, effective_workers = validate_parallel_openalex(max_workers)
        if use_parallel and parallel_ok:
            print(f" Параллелизация включена: {effective_workers} потоков")
        else:
            use_parallel = False
            print(" Параллелизация отключена")

        current_date = date.today()
        current_year = current_date.year
        journal_field = detect_journal_field(issn, journal_name)

        if progress_callback:
            progress_callback(0.0)
            print("Начало сбора статей из Crossref...")

        if_publication_years = [current_year - 2, current_year - 1]
        cs_publication_years = list(range(current_year - 3, current_year + 1))

        all_articles = {}
        if_items = []
        for year in if_publication_years:
            from_date = f"{year}-01-01"
            until_date = f"{year}-12-31"
            items = fetch_articles_enhanced(issn, from_date, until_date, use_cache, progress_callback)
            if_items.extend(items)
            all_articles[year] = items
            print(f"Год {year}: Найдено {len(items)} статей")

        cs_items = []
        for year in cs_publication_years:
            if year not in all_articles:
                from_date = f"{year}-01-01"
                until_date = f"{year}-12-31"
                items = fetch_articles_enhanced(issn, from_date, until_date, use_cache, progress_callback)
                all_articles[year] = items
                print(f"Год {year}: Найдено {len(items)} статей")
            cs_items.extend(all_articles[year])

        B_if = len(if_items)
        B_cs = len(cs_items)
        print(f"Статьи для ИФ (2023–2024): {B_if}")
        print(f"Статьи для CiteScore (2022–2025): {B_cs}")
        if B_if == 0 or B_cs == 0:
            print(f"calculate_metrics_enhanced: Нет статей для анализа: IF={B_if}, CS={B_cs}")
            if progress_callback:
                progress_callback(1.0)
            return None

        if progress_callback:
            progress_callback(0.3)
            print("Начало анализа цитирований через OpenAlex...")

        A_if_current = 0
        valid_dois = 0
        articles_without_doi = 0
        openalex_errors = 0
        if_citation_data = []
        
        dois_if = [item.get('DOI') for item in if_items if item.get('DOI') != 'N/A']
        
        print(f"Всего статей для ИФ: {B_if}, с DOI: {len(dois_if)}, без DOI: {B_if - len(dois_if)}")
        
        if use_parallel and dois_if:
            print(f" Параллельный анализ {len(dois_if)} DOI для ИФ...")
            parallel_results = parallel_fetch_citations_openalex(
                dois_if,
                date(current_year, 1, 1),
                date(current_year, 12, 31),
                effective_workers,
                progress_callback
            )
            
            for item in if_items:
                doi = item.get('DOI', 'N/A')
                crossref_cites = item.get('is-referenced-by-count', 0)
                
                if doi != 'N/A' and doi in parallel_results:
                    result = parallel_results[doi]
                    if result is not None and result.get('processed_successfully', False):
                        # УСПЕШНЫЙ запрос к OpenAlex
                        A_if_current += result['count'] if result['count'] is not None else 0
                        valid_dois += 1
                        if_citation_data.append({
                            'DOI': doi,
                            'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                            'Дата публикации': item.get('published', {}).get('date-parts', [[None, None, None]])[0][:3],
                            'Цитирования (Crossref)': crossref_cites,
                            'Цитирования (OpenAlex)': result['total_count'] if result['total_count'] is not None else 'Ошибка',
                            'Цитирования в периоде': result['count'] if result['count'] is not None else 'Ошибка',
                            'has_doi': True,
                            'openalex_success': True,
                            'found_in_openalex': result.get('found_in_openalex', False)
                        })
                    else:
                        # ОШИБКА при запросе к OpenAlex
                        openalex_errors += 1
                        if_citation_data.append({
                            'DOI': doi,
                            'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                            'Дата публикации': item.get('published', {}).get('date-parts', [[None, None, None]])[0][:3],
                            'Цитирования (Crossref)': crossref_cites,
                            'Цитирования (OpenAlex)': 'Ошибка запроса',
                            'Цитирования в периоде': 'Ошибка запроса',
                            'has_doi': True,
                            'openalex_success': False,
                            'found_in_openalex': False
                        })
                else:
                    # Статья БЕЗ DOI
                    articles_without_doi += 1
                    if_citation_data.append({
                        'DOI': doi,
                        'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                        'Дата публикации': item.get('published', {}).get('date-parts', [[None, None, None]])[0][:3],
                        'Цитирования (Crossref)': crossref_cites,
                        'Цитирования (OpenAlex)': 'Нет DOI',
                        'Цитирования в периоде': 'Нет DOI',
                        'has_doi': False,
                        'openalex_success': False,
                        'found_in_openalex': False
                    })
        else:
            for i, item in enumerate(if_items):
                doi = item.get('DOI', 'N/A')
                crossref_cites = item.get('is-referenced-by-count', 0)
                if doi != 'N/A':
                    result = fetch_citations_openalex(
                        doi,
                        date(current_year, 1, 1),
                        date(current_year, 12, 31),
                        lambda p: progress_callback(0.3 + 0.6 * (i + 1) / B_if * p) if progress_callback else None
                    )
                    if result.get('processed_successfully', False):
                        A_if_current += result['count'] if result['count'] is not None else 0
                        valid_dois += 1
                        if_citation_data.append({
                            'DOI': doi,
                            'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                            'Дата публикации': item.get('published', {}).get('date-parts', [[None, None, None]])[0][:3],
                            'Цитирования (Crossref)': crossref_cites,
                            'Цитирования (OpenAlex)': result['total_count'] if result['total_count'] is not None else 'Ошибка',
                            'Цитирования в периоде': result['count'] if result['count'] is not None else 'Ошибка',
                            'has_doi': True,
                            'openalex_success': True,
                            'found_in_openalex': result.get('found_in_openalex', False)
                        })
                    else:
                        openalex_errors += 1
                        if_citation_data.append({
                            'DOI': doi,
                            'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                            'Дата публикации': item.get('published', {}).get('date-parts', [[None, None, None]])[0][:3],
                            'Цитирования (Crossref)': crossref_cites,
                            'Цитирования (OpenAlex)': 'Ошибка запроса',
                            'Цитирования в периоде': 'Ошибка запроса',
                            'has_doi': True,
                            'openalex_success': False,
                            'found_in_openalex': False
                        })
                else:
                    articles_without_doi += 1
                    if_citation_data.append({
                        'DOI': doi,
                        'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                        'Дата публикации': item.get('published', {}).get('date-parts', [[None, None, None]])[0][:3],
                        'Цитирования (Crossref)': crossref_cites,
                        'Цитирования (OpenAlex)': 'Нет DOI',
                        'Цитирования в периоде': 'Нет DOI',
                        'has_doi': False,
                        'openalex_success': False,
                        'found_in_openalex': False
                    })
        
        print(f"Обработано статей: {B_if}")
        print(f" - С DOI и успешным запросом: {valid_dois}")
        print(f" - С DOI, но с ошибкой OpenAlex: {openalex_errors}")
        print(f" - Без DOI: {articles_without_doi}")
        print(f"Цитирований в {current_year}: {A_if_current}")

        A_cs_current = sum(item.get('is-referenced-by-count', 0) for item in cs_items)
        cs_citation_data = [
            {
                'DOI': item.get('DOI', 'N/A'),
                'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                'Дата публикации': item.get('published', {}).get('date-parts', [[None, None, None]])[0][:3],
                'Цитирования (Crossref)': item.get('is-referenced-by-count', 0),
                'Цитирования (OpenAlex)': 0,
                'Цитирования в периоде': 0,
                'has_doi': item.get('DOI') != 'N/A'
            } for item in cs_items
        ]

        # РАСЧЕТ ИФ только по статьям, которые успешно обработаны в OpenAlex
        successful_articles = valid_dois
        current_if = A_if_current / successful_articles if successful_articles > 0 else 0
        current_citescore = A_cs_current / B_cs if B_cs > 0 else 0

        if progress_callback:
            progress_callback(0.9)
            print("Расчет метрик...")

        seasonal_coefficients = get_seasonal_coefficients(journal_field)
        multiplier_conservative = calculate_weighted_multiplier(current_date, seasonal_coefficients, "conservative")
        multiplier_balanced = calculate_weighted_multiplier(current_date, seasonal_coefficients, "balanced")
        multiplier_optimistic = calculate_weighted_multiplier(current_date, seasonal_coefficients, "optimistic")

        if_forecasts = {
            'conservative': current_if * multiplier_conservative,
            'balanced': current_if * multiplier_balanced,
            'optimistic': current_if * multiplier_optimistic
        }

        citescore_forecasts = {
            'conservative': current_citescore * multiplier_conservative,
            'balanced': current_citescore * multiplier_balanced,
            'optimistic': current_citescore * multiplier_optimistic
        }

        if progress_callback:
            progress_callback(1.0)
            print("Анализ завершен")

        return {
            'current_if': current_if,
            'current_citescore': current_citescore,
            'if_forecasts': if_forecasts,
            'citescore_forecasts': citescore_forecasts,
            'multipliers': {
                'conservative': multiplier_conservative,
                'balanced': multiplier_balanced,
                'optimistic': multiplier_optimistic
            },
            'total_cites_if': A_if_current,
            'total_articles_if': B_if,
            'total_cites_cs': A_cs_current,
            'total_articles_cs': B_cs,
            'citation_distribution': dict(seasonal_coefficients),
            'if_citation_data': if_citation_data,
            'cs_citation_data': cs_citation_data,
            'analysis_date': current_date,
            'if_publication_years': if_publication_years,
            'cs_publication_years': cs_publication_years,
            'seasonal_coefficients': seasonal_coefficients,
            'journal_field': journal_field,
            'self_citation_rate': 0.05,
            'total_self_citations': int(A_if_current * 0.05),
            'issn': issn,
            'journal_name': journal_name,
            'citation_model_data': [],
            'parallel_processing': use_parallel,
            'parallel_workers': effective_workers,
            'diagnostics': {
                'articles_with_doi': len(dois_if),
                'articles_without_doi': articles_without_doi,
                'openalex_successful_requests': valid_dois,
                'openalex_failed_requests': openalex_errors,
                'successful_articles_ratio': valid_dois / B_if if B_if > 0 else 0
            }
        }

    except Exception as e:
        print(f"Ошибка в calculate_metrics_enhanced для ISSN {issn}: {e}")
        if progress_callback:
            progress_callback(1.0)
        return None

def calculate_metrics_dynamic(issn, journal_name="Не указано", use_cache=True, progress_callback=None, use_parallel=True, max_workers=20):
    """ДИНАМИЧЕСКАЯ функция для расчета метрик с динамическими периодами и ДВУМЯ значениями CiteScore"""
    # Создаем базовый результат с ВСЕМИ полями
    base_result = {
        'error': False,
        'error_message': '',
        'issn': issn,
        'journal_name': journal_name,
        'analysis_date': date.today(),
        'if_publication_period': [None, None],
        'if_citation_period': [None, None],
        'cs_publication_period': [None, None],
        'cs_citation_period': [None, None],
        'total_articles_if': 0,
        'total_articles_cs': 0,
        'total_cites_if': 0,
        'total_cites_cs_crossref': 0,
        'total_cites_cs_openalex': 0,
        'current_if': 0.0,
        'current_citescore_crossref': 0.0,
        'current_citescore_openalex': 0.0,
        'if_citation_data': [],
        'cs_citation_data': [],
        'journal_field': "general",
        'self_citation_rate': 0.05,
        'total_self_citations': 0,
        'parallel_processing': False,
        'parallel_workers': 1,
        'citation_distribution': {},
        'seasonal_coefficients': {},
        'citation_model_data': [],
        'diagnostics': {
            'if_articles_sample': [],
            'cs_articles_sample': [],
            'if_period_dates': '',
            'cs_period_dates': '',
            'journal_field': 'general',
            'crossref_openalex_discrepancy': 0,
            'articles_with_citations': 0,
            'valid_dois_ratio': 0,
            'error_type': '',
            'articles_with_doi': 0,
            'articles_without_doi': 0,
            'openalex_successful_requests': 0,
            'openalex_failed_requests': 0,
            'successful_articles_ratio': 0
        }
    }
    
    try:
        print(f"Запуск calculate_metrics_dynamic для ISSN {issn}")
        if not validate_issn(issn):
            print(f"Неверный формат ISSN: {issn}")
            base_result['error'] = True
            base_result['error_message'] = 'Неверный формат ISSN'
            return base_result

        # Обновляем базовые поля
        base_result['analysis_date'] = date.today()
        base_result['journal_name'] = journal_name

        parallel_ok, effective_workers = validate_parallel_openalex(max_workers)
        if use_parallel and parallel_ok:
            print(f" Параллелизация включена: {effective_workers} потоков")
            base_result['parallel_processing'] = True
            base_result['parallel_workers'] = effective_workers
        else:
            base_result['parallel_processing'] = False
            print(" Параллелизация отключена")

        base_result['journal_field'] = detect_journal_field(issn, journal_name)

        if progress_callback:
            progress_callback(0.0)
            print("Начало сбора статей из Crossref...")

        # Периоды для ИФ
        if_citation_start = base_result['analysis_date'] - timedelta(days=18*30)
        if_citation_end = base_result['analysis_date'] - timedelta(days=6*30)
        if_article_start = base_result['analysis_date'] - timedelta(days=42*30)
        if_article_end = base_result['analysis_date'] - timedelta(days=18*30)

        # Периоды для CiteScore
        cs_citation_start = base_result['analysis_date'] - timedelta(days=52*30)
        cs_citation_end = base_result['analysis_date'] - timedelta(days=4*30)
        cs_article_start = base_result['analysis_date'] - timedelta(days=52*30)
        cs_article_end = base_result['analysis_date'] - timedelta(days=4*30)

        # Обновляем периоды в результате
        base_result['if_publication_period'] = [if_article_start, if_article_end]
        base_result['if_citation_period'] = [if_citation_start, if_citation_end]
        base_result['cs_publication_period'] = [cs_article_start, cs_article_end]
        base_result['cs_citation_period'] = [cs_citation_start, cs_citation_end]

        # УЛУЧШЕННАЯ ПРОВЕРКА ФОРМАТА ДАТ
        print(f"=== ПАРАМЕТРЫ ДИНАМИЧЕСКОГО АНАЛИЗА ===")
        print(f"ISSN: {issn}")
        print(f"ИФ - Период статей: {if_article_start} до {if_article_end}")
        print(f"ИФ - Период цитирований: {if_citation_start} до {if_citation_end}")
        print(f"CiteScore - Период статей: {cs_article_start} до {cs_article_end}")
        print(f"CiteScore - Период цитирований: {cs_citation_start} до {cs_citation_end}")
        print(f"======================================")

        # Получение статей для ИФ
        if_items = fetch_articles_enhanced(
            issn,
            if_article_start.strftime('%Y-%m-%d'),
            if_article_end.strftime('%Y-%m-%d'),
            use_cache,
            progress_callback
        )

        # Получение статей для CiteScore
        cs_items = fetch_articles_enhanced(
            issn,
            cs_article_start.strftime('%Y-%m-%d'),
            cs_article_end.strftime('%Y-%m-%d'),
            use_cache,
            progress_callback
        )

        base_result['total_articles_if'] = len(if_items)
        base_result['total_articles_cs'] = len(cs_items)
        
        print(f"Статьи для ИФ ({if_article_start}–{if_article_end}): {base_result['total_articles_if']}")
        print(f"Статьи для CiteScore ({cs_article_start}–{cs_article_end}): {base_result['total_articles_cs']}")
        
        # УЛУЧШЕННАЯ ПРОВЕРКА ДАННЫХ: более детальная диагностика
        if base_result['total_articles_if'] == 0:
            print(f"❌ ВНИМАНИЕ: Нет статей для ИФ в указанном периоде")
            print(f"   Проверьте параметры: ISSN={issn}, период={if_article_start} до {if_article_end}")
            
        if base_result['total_articles_cs'] == 0:
            print(f"❌ ВНИМАНИЕ: Нет статей для CiteScore в указанном периоде")
            print(f"   Проверьте параметры: ISSN={issn}, период={cs_article_start} до {cs_article_end}")
            
        if base_result['total_articles_if'] == 0 or base_result['total_articles_cs'] == 0:
            print(f"calculate_metrics_dynamic: Нет статей для анализа")
            base_result['error'] = True
            base_result['error_message'] = 'Не удалось получить данные для анализа. Проверьте ISSN или наличие статей в Crossref за указанные периоды.'
            
            # Добавляем примеры статей если они есть
            if if_items:
                base_result['diagnostics']['if_articles_sample'] = [
                    {
                        'DOI': item.get('DOI', 'N/A'),
                        'title': item.get('title', ['N/A'])[0],
                        'type': item.get('type', 'N/A'),
                        'published': item.get('published', {}),
                        'is-referenced-by-count': item.get('is-referenced-by-count', 0)
                    } for item in if_items[:3]
                ]
                
            if cs_items:
                base_result['diagnostics']['cs_articles_sample'] = [
                    {
                        'DOI': item.get('DOI', 'N/A'),
                        'title': item.get('title', ['N/A'])[0],
                        'type': item.get('type', 'N/A'),
                        'published': item.get('published', {}),
                        'is-referenced-by-count': item.get('is-referenced-by-count', 0)
                    } for item in cs_items[:3]
                ]
            
            base_result['diagnostics']['if_period_dates'] = f"{if_article_start} to {if_article_end}"
            base_result['diagnostics']['cs_period_dates'] = f"{cs_article_start} to {cs_article_end}"
            base_result['diagnostics']['journal_field'] = base_result['journal_field']
            
            if progress_callback:
                progress_callback(1.0)
            return base_result

        if progress_callback:
            progress_callback(0.3)
            print("Начало параллельного анализа цитирований через OpenAlex...")

        # ПАРАЛЛЕЛЬНЫЙ расчет ИФ - УЛУЧШЕННАЯ ВЕРСИЯ
        A_if_current = 0
        valid_dois_if = 0
        articles_without_doi = 0
        openalex_errors = 0
        if_citation_data = []
        
        dois_if = [item.get('DOI') for item in if_items if item.get('DOI') != 'N/A']
        
        print(f"Всего статей для ИФ: {base_result['total_articles_if']}, с DOI: {len(dois_if)}, без DOI: {base_result['total_articles_if'] - len(dois_if)}")
        
        if base_result['parallel_processing'] and dois_if:
            print(f" Параллельный анализ {len(dois_if)} DOI для ИФ...")
            parallel_results_if = parallel_fetch_citations_openalex(
                dois_if,
                if_citation_start,
                if_citation_end,
                base_result['parallel_workers'],
                lambda p: progress_callback(0.3 + 0.2 * p)
            )
            
            for item in if_items:
                doi = item.get('DOI', 'N/A')
                crossref_cites = item.get('is-referenced-by-count', 0)
                pub_date_parts = item.get('published', {}).get('date-parts', [[None, None, None]])[0]
                pub_date = f"{pub_date_parts[0] or 'N/A'}-{pub_date_parts[1] or 1:02d}-{pub_date_parts[2] or 1:02d}"
                
                if doi != 'N/A' and doi in parallel_results_if:
                    result = parallel_results_if[doi]
                    if result is not None and result.get('processed_successfully', False):
                        # УСПЕШНЫЙ запрос к OpenAlex
                        citations_in_period = result['count'] if result['count'] is not None else 0
                        A_if_current += citations_in_period
                        valid_dois_if += 1
                        if_citation_data.append({
                            'DOI': doi,
                            'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                            'Дата публикации': pub_date,
                            'Цитирования (Crossref)': crossref_cites,
                            'Цитирования (OpenAlex)': result['total_count'] if result['total_count'] is not None else 'Ошибка',
                            'Цитирования в периоде': citations_in_period,
                            'has_doi': True,
                            'openalex_success': True,
                            'found_in_openalex': result.get('found_in_openalex', False)
                        })
                    else:
                        # ОШИБКА при запросе к OpenAlex
                        openalex_errors += 1
                        if_citation_data.append({
                            'DOI': doi,
                            'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                            'Дата публикации': pub_date,
                            'Цитирования (Crossref)': crossref_cites,
                            'Цитирования (OpenAlex)': 'Ошибка запроса',
                            'Цитирования в периоде': 'Ошибка запроса',
                            'has_doi': True,
                            'openalex_success': False,
                            'found_in_openalex': False
                        })
                else:
                    # Статья БЕЗ DOI
                    articles_without_doi += 1
                    if_citation_data.append({
                        'DOI': doi,
                        'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                        'Дата публикации': pub_date,
                        'Цитирования (Crossref)': crossref_cites,
                        'Цитирования (OpenAlex)': 'Нет DOI',
                        'Цитирования в периоде': 'Нет DOI',
                        'has_doi': False,
                        'openalex_success': False,
                        'found_in_openalex': False
                    })
        else:
            for i, item in enumerate(if_items):
                doi = item.get('DOI', 'N/A')
                crossref_cites = item.get('is-referenced-by-count', 0)
                pub_date_parts = item.get('published', {}).get('date-parts', [[None, None, None]])[0]
                pub_date = f"{pub_date_parts[0] or 'N/A'}-{pub_date_parts[1] or 1:02d}-{pub_date_parts[2] or 1:02d}"
                
                if doi != 'N/A':
                    result = fetch_citations_openalex(
                        doi,
                        if_citation_start,
                        if_citation_end,
                        lambda p: progress_callback(0.3 + 0.2 * (i + 1) / base_result['total_articles_if'] * p) if progress_callback else None
                    )
                    if result.get('processed_successfully', False):
                        citations_in_period = result['count'] if result['count'] is not None else 0
                        A_if_current += citations_in_period
                        valid_dois_if += 1
                        if_citation_data.append({
                            'DOI': doi,
                            'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                            'Дата публикации': pub_date,
                            'Цитирования (Crossref)': crossref_cites,
                            'Цитирования (OpenAlex)': result['total_count'] if result['total_count'] is not None else 'Ошибка',
                            'Цитирования в периоде': citations_in_period,
                            'has_doi': True,
                            'openalex_success': True,
                            'found_in_openalex': result.get('found_in_openalex', False)
                        })
                    else:
                        openalex_errors += 1
                        if_citation_data.append({
                            'DOI': doi,
                            'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                            'Дата публикации': pub_date,
                            'Цитирования (Crossref)': crossref_cites,
                            'Цитирования (OpenAlex)': 'Ошибка запроса',
                            'Цитирования в периоде': 'Ошибка запроса',
                            'has_doi': True,
                            'openalex_success': False,
                            'found_in_openalex': False
                        })
                else:
                    articles_without_doi += 1
                    if_citation_data.append({
                        'DOI': doi,
                        'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                        'Дата публикации': pub_date,
                        'Цитирования (Crossref)': crossref_cites,
                        'Цитирования (OpenAlex)': 'Нет DOI',
                        'Цитирования в периоде': 'Нет DOI',
                        'has_doi': False,
                        'openalex_success': False,
                        'found_in_openalex': False
                    })
        
        print(f"Обработано статей для ИФ: {base_result['total_articles_if']}")
        print(f" - С DOI и успешным запросом: {valid_dois_if}")
        print(f" - С DOI, но с ошибкой OpenAlex: {openalex_errors}")
        print(f" - Без DOI: {articles_without_doi}")
        print(f"Цитирований в периоде для ИФ: {A_if_current}")

        # Расчет ДВУХ значений CiteScore: Crossref и OpenAlex
        # Для Crossref используем стандартные данные Crossref
        A_cs_current_crossref = sum(item.get('is-referenced-by-count', 0) for item in cs_items)
        
        # Для OpenAlex используем ВСЕ цитирования (total_count), а не только в периоде
        A_cs_current_openalex = 0
        cs_citation_data = []
        valid_dois_cs = 0
        
        # Получаем реальные цитирования OpenAlex для расчета второго значения CiteScore
        dois_cs = [item.get('DOI') for item in cs_items if item.get('DOI') != 'N/A']
        
        if base_result['parallel_processing'] and dois_cs:
            print(f" Параллельный анализ {len(dois_cs)} DOI для получения цитирований OpenAlex для CiteScore...")
            parallel_results_cs = parallel_fetch_citations_openalex(
                dois_cs,
                cs_citation_start,
                cs_citation_end,
                base_result['parallel_workers'],
                lambda p: progress_callback(0.5 + 0.4 * p)
            )
            
            for item in cs_items:
                doi = item.get('DOI', 'N/A')
                crossref_cites = item.get('is-referenced-by-count', 0)
                pub_date_parts = item.get('published', {}).get('date-parts', [[None, None, None]])[0]
                pub_date = f"{pub_date_parts[0] or 'N/A'}-{pub_date_parts[1] or 1:02d}-{pub_date_parts[2] or 1:02d}"
                
                if doi != 'N/A' and doi in parallel_results_cs:
                    result = parallel_results_cs[doi]
                    if result is not None and result.get('processed_successfully', False):
                        # ИСПРАВЛЕНИЕ: используем total_count (все цитирования) вместо count (только в периоде)
                        total_citations = result['total_count'] if result['total_count'] is not None else 0
                        A_cs_current_openalex += total_citations
                        valid_dois_cs += 1
                        cs_citation_data.append({
                            'DOI': doi,
                            'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                            'Дата публикации': pub_date,
                            'Цитирования (Crossref)': crossref_cites,
                            'Цитирования (OpenAlex)': total_citations,
                            'Цитирования в периоде': result['count'] if result['count'] is not None else 0,
                            'has_doi': True,
                            'openalex_success': True,
                            'found_in_openalex': result.get('found_in_openalex', False)
                        })
                    else:
                        cs_citation_data.append({
                            'DOI': doi,
                            'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                            'Дата публикации': pub_date,
                            'Цитирования (Crossref)': crossref_cites,
                            'Цитирования (OpenAlex)': 'Ошибка запроса',
                            'Цитирования в периоде': 'Ошибка запроса',
                            'has_doi': True,
                            'openalex_success': False,
                            'found_in_openalex': False
                        })
                else:
                    cs_citation_data.append({
                        'DOI': doi,
                        'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                        'Дата публикации': pub_date,
                        'Цитирования (Crossref)': crossref_cites,
                        'Цитирования (OpenAlex)': 'Нет DOI',
                        'Цитирования в периоде': 'Нет DOI',
                        'has_doi': False,
                        'openalex_success': False,
                        'found_in_openalex': False
                    })
        else:
            for i, item in enumerate(cs_items):
                doi = item.get('DOI', 'N/A')
                crossref_cites = item.get('is-referenced-by-count', 0)
                pub_date_parts = item.get('published', {}).get('date-parts', [[None, None, None]])[0]
                pub_date = f"{pub_date_parts[0] or 'N/A'}-{pub_date_parts[1] or 1:02d}-{pub_date_parts[2] or 1:02d}"
                
                if doi != 'N/A':
                    result = fetch_citations_openalex(
                        doi,
                        cs_citation_start,
                        cs_citation_end,
                        lambda p: progress_callback(0.5 + 0.4 * (i + 1) / base_result['total_articles_cs'] * p) if progress_callback else None
                    )
                    if result.get('processed_successfully', False):
                        # ИСПРАВЛЕНИЕ: используем total_count (все цитирования) вместо count (только в периоде)
                        total_citations = result['total_count'] if result['total_count'] is not None else 0
                        A_cs_current_openalex += total_citations
                        valid_dois_cs += 1
                        cs_citation_data.append({
                            'DOI': doi,
                            'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                            'Дата публикации': pub_date,
                            'Цитирования (Crossref)': crossref_cites,
                            'Цитирования (OpenAlex)': total_citations,
                            'Цитирования в периоде': result['count'] if result['count'] is not None else 0,
                            'has_doi': True,
                            'openalex_success': True,
                            'found_in_openalex': result.get('found_in_openalex', False)
                        })
                    else:
                        cs_citation_data.append({
                            'DOI': doi,
                            'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                            'Дата публикации': pub_date,
                            'Цитирования (Crossref)': crossref_cites,
                            'Цитирования (OpenAlex)': 'Ошибка запроса',
                            'Цитирования в периоде': 'Ошибка запроса',
                            'has_doi': True,
                            'openalex_success': False,
                            'found_in_openalex': False
                        })
                else:
                    cs_citation_data.append({
                        'DOI': doi,
                        'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                        'Дата публикации': pub_date,
                        'Цитирования (Crossref)': crossref_cites,
                        'Цитирования (OpenAlex)': 'Нет DOI',
                        'Цитирования в периоде': 'Нет DOI',
                        'has_doi': False,
                        'openalex_success': False,
                        'found_in_openalex': False
                    })
        
        print(f"Обработано DOI для CiteScore: {valid_dois_cs}/{base_result['total_articles_cs']}")
        print(f"Цитирований Crossref для CiteScore: {A_cs_current_crossref}")
        print(f"Цитирований OpenAlex для CiteScore: {A_cs_current_openalex}")

        # УЛУЧШЕННАЯ ПРОВЕРКА НЕСООТВЕТСТВИЯ ДАННЫХ
        total_crossref_cites = sum(item['Цитирования (Crossref)'] for item in if_citation_data if isinstance(item['Цитирования (Crossref)'], (int, float)))
        total_openalex_cites = sum(item['Цитирования в периоде'] for item in if_citation_data if isinstance(item['Цитирования в периоде'], (int, float)))
        
        print(f"=== СВОДКА ЦИТИРОВАНИЙ ===")
        print(f"ИФ - Crossref цитирования: {total_crossref_cites}")
        print(f"ИФ - OpenAlex цитирования (в периоде): {total_openalex_cites}")
        print(f"ИФ - Цитирования в периоде (обработанные): {A_if_current}")
        print(f"CiteScore - Crossref: {A_cs_current_crossref}")
        print(f"CiteScore - OpenAlex: {A_cs_current_openalex}")
        print(f"==========================")

        # Расчет ДВУХ значений CiteScore
        # ИФ рассчитывается только по успешно обработанным статьям
        successful_articles_if = valid_dois_if
        base_result['current_if'] = A_if_current / successful_articles_if if successful_articles_if > 0 else 0
        base_result['current_citescore_crossref'] = A_cs_current_crossref / base_result['total_articles_cs'] if base_result['total_articles_cs'] > 0 else 0
        base_result['current_citescore_openalex'] = A_cs_current_openalex / base_result['total_articles_cs'] if base_result['total_articles_cs'] > 0 else 0

        # Обновляем итоговые переменные
        base_result['total_cites_if'] = A_if_current
        base_result['total_cites_cs_crossref'] = A_cs_current_crossref
        base_result['total_cites_cs_openalex'] = A_cs_current_openalex
        base_result['total_self_citations'] = int(A_if_current * 0.05)
        base_result['if_citation_data'] = if_citation_data
        base_result['cs_citation_data'] = cs_citation_data

        if progress_callback:
            progress_callback(0.9)
            print("Расчет метрик...")

        base_result['seasonal_coefficients'] = get_seasonal_coefficients(base_result['journal_field'])
        base_result['citation_distribution'] = dict(base_result['seasonal_coefficients'])

        # Обновляем диагностику
        base_result['diagnostics']['crossref_openalex_discrepancy'] = abs(total_crossref_cites - total_openalex_cites)
        base_result['diagnostics']['articles_with_citations'] = len([item for item in if_citation_data if isinstance(item['Цитирования в периоде'], (int, float)) and item['Цитирования в периоде'] > 0])
        base_result['diagnostics']['valid_dois_ratio'] = valid_dois_if / base_result['total_articles_if'] if base_result['total_articles_if'] > 0 else 0
        base_result['diagnostics']['if_articles_sample'] = if_items[:3] if if_items else []
        base_result['diagnostics']['cs_articles_sample'] = cs_items[:3] if cs_items else []
        base_result['diagnostics']['if_period_dates'] = f"{if_article_start} to {if_article_end}"
        base_result['diagnostics']['cs_period_dates'] = f"{cs_article_start} to {cs_article_end}"
        base_result['diagnostics']['journal_field'] = base_result['journal_field']
        base_result['diagnostics']['articles_with_doi'] = len(dois_if)
        base_result['diagnostics']['articles_without_doi'] = articles_without_doi
        base_result['diagnostics']['openalex_successful_requests'] = valid_dois_if
        base_result['diagnostics']['openalex_failed_requests'] = openalex_errors
        base_result['diagnostics']['successful_articles_ratio'] = valid_dois_if / base_result['total_articles_if'] if base_result['total_articles_if'] > 0 else 0

        if progress_callback:
            progress_callback(1.0)
            print("Анализ завершен")

        return base_result

    except Exception as e:
        print(f"Ошибка в calculate_metrics_dynamic для ISSN {issn}: {e}")
        
        # Обновляем базовый результат с информацией об ошибке
        base_result['error'] = True
        base_result['error_message'] = f'Не удалось получить данные для анализа: {str(e)}'
        base_result['diagnostics']['error_type'] = type(e).__name__
        
        if progress_callback:
            progress_callback(1.0)
        return base_result

def on_clear_cache_clicked(b):
    """Функция для очистки кэша"""
    try:
        if os.path.exists(CACHE_DIR):
            for file in os.listdir(CACHE_DIR):
                file_path = os.path.join(CACHE_DIR, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Ошибка при удалении {file_path}: {e}")
            print("Кэш успешно очищен")
            return "Кэш успешно очищен!"
        else:
            print("Кэш уже пуст")
            return "Кэш уже пуст"
    except Exception as e:
        print(f"Ошибка при очистке кэша: {e}")
        return f"Ошибка при очистке кэша: {e}"

