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
import asyncio
import aiohttp
import nest_asyncio
warnings.filterwarnings('ignore')

# Для работы async в Streamlit
try:
    nest_asyncio.apply()
except:
    pass

base_url_crossref = "https://api.crossref.org/works"
base_url_openalex = "https://api.openalex.org/works"
CACHE_DIR = "journal_analysis_cache"
CACHE_DURATION = timedelta(hours=24)

# Глобальные переменные для статистики
total_requests = 0
failed_requests = 0
request_lock = threading.Lock()
last_429_warning = ""

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

def make_request_with_retry(url, max_retries=8, timeout=10):
    """Умный запрос с увеличенными экспоненциальными backoff задержками"""
    global total_requests, failed_requests, last_429_warning
    
    delays = [0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 1.7, 2.0]
    
    for attempt in range(max_retries):
        try:
            with request_lock:
                total_requests += 1
            
            response = requests.get(url, timeout=timeout)
            
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                delay = delays[min(attempt, len(delays) - 1)]
                last_429_warning = f"⚠️ 429 ошибка, попытка {attempt + 1}, задержка {delay}с"
                time.sleep(delay)
            else:
                time.sleep(delays[min(attempt, len(delays) - 1)])
                
        except requests.exceptions.Timeout:
            time.sleep(delays[min(attempt, len(delays) - 1)])
        except Exception as e:
            time.sleep(delays[min(attempt, len(delays) - 1)])
    
    with request_lock:
        failed_requests += 1
        if last_429_warning:
            print(last_429_warning)
            last_429_warning = ""
    return None

async def make_async_request(session, url, semaphore, timeout=10):
    """Асинхронный запрос с семафором для ограничения параллелизма"""
    async with semaphore:
        try:
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return None
        except Exception as e:
            return None

async def get_openalex_counts_async(dois):
    """Асинхронное пакетное получение цитирований"""
    semaphore = asyncio.Semaphore(5)
    timeout = aiohttp.ClientTimeout(total=15)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        for doi in dois:
            if doi == 'N/A':
                continue
                
            normalized_doi = doi
            if not doi.startswith('https://doi.org/'):
                normalized_doi = f"https://doi.org/{doi}"
            
            url = f"https://api.openalex.org/works/{normalized_doi}"
            task = make_async_request(session, url, semaphore)
            tasks.append((doi, task))
        
        results = {}
        for doi, task in tasks:
            data = await task
            if data:
                results[doi] = data.get('cited_by_count', 0)
            else:
                results[doi] = 0
        
        return results

def get_citing_articles_openalex_with_dates(doi):
    """Получить количество цитирований и даты цитирований через OpenAlex"""
    citing_articles = []
    
    if doi == 'N/A':
        return citing_articles
    
    normalized_doi = doi
    if not doi.startswith('https://doi.org/'):
        normalized_doi = f"https://doi.org/{doi}"
    
    works_url = f"https://api.openalex.org/works/{normalized_doi}"
    
    response = make_request_with_retry(works_url, timeout=15)
    if not response:
        return citing_articles
        
    work_data = response.json()
    cited_by_count = work_data.get('cited_by_count', 0)
    
    if cited_by_count > 0:
        cited_by_url = f"https://api.openalex.org/works?filter=cites:{work_data['id']}&per-page=200"
        
        while cited_by_url:
            response_cited = make_request_with_retry(cited_by_url, timeout=20)
            if not response_cited:
                break
                
            cited_data = response_cited.json()
            results = cited_data.get('results', [])
            
            for work in results:
                publication_date = work.get('publication_date', '')
                if publication_date:
                    citing_articles.append({
                        'date': publication_date,
                        'doi': work.get('doi', '')
                    })
            
            cited_by_url = cited_data.get('meta', {}).get('next_page')
    
    return citing_articles

def get_citing_count_openalex_batch(dois):
    """Пакетное получение цитирований для нескольких DOI"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_doi = {executor.submit(get_single_openalex_count, doi): doi for doi in dois}
                results = {}
                for future in as_completed(future_to_doi):
                    doi, count = future.result()
                    results[doi] = count
                return results
        else:
            return asyncio.run(get_openalex_counts_async(dois))
    except:
        results = {}
        for doi in dois:
            results[doi] = get_single_openalex_count(doi)[1]
        return results

def get_single_openalex_count(doi):
    """Получение цитирований для одного DOI"""
    if doi == 'N/A':
        return doi, 0
        
    normalized_doi = doi
    if not doi.startswith('https://doi.org/'):
        normalized_doi = f"https://doi.org/{doi}"
    
    works_url = f"https://api.openalex.org/works/{normalized_doi}"
    response = make_request_with_retry(works_url, timeout=10)
    
    if response:
        work_data = response.json()
        return doi, work_data.get('cited_by_count', 0)
    return doi, 0

def fetch_articles_parallel(issn, from_date, until_date, use_cache=True):
    """Параллельная загрузка статей из Crossref"""
    cache_key = get_cache_key("fetch_articles_parallel", issn, from_date, until_date)
    if use_cache:
        cached_data = load_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

    items = []
    cursor = "*"
    
    def fetch_page(cursor):
        params = {
            'filter': f'issn:{issn},from-pub-date:{from_date},until-pub-date:{until_date}',
            'rows': 1000,
            'cursor': cursor,
            'mailto': 'example@email.com'
        }
        try:
            resp = requests.get(base_url_crossref, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            print(f"Error fetching data: {e}")
            return None
    
    while cursor:
        data = fetch_page(cursor)
        if not data:
            break
            
        message = data['message']
        items.extend(message['items'])
        cursor = message.get('next-cursor')
        
        if not cursor or len(message['items']) == 0:
            break
    
    if use_cache and items:
        save_to_cache(items, cache_key)
    return items

def extract_article_info_parallel(items):
    """Параллельное извлечение информации о статьях"""
    def process_single_item(item):
        doi = item.get('DOI', 'N/A')
        crossref_cites = item.get('is-referenced-by-count', 0)
        
        created_date_parts = item.get('created', {}).get('date-parts', None)
        pub_year = str(created_date_parts[0][0]) if created_date_parts and created_date_parts[0] and len(created_date_parts[0]) > 0 else 'N/A'
        pub_month = str(created_date_parts[0][1]).zfill(2) if created_date_parts and created_date_parts[0] and len(created_date_parts[0]) > 1 else '01'
        pub_day = str(created_date_parts[0][2]).zfill(2) if created_date_parts and created_date_parts[0] and len(created_date_parts[0]) > 2 else '01'
        pub_date = f"{pub_year}-{pub_month}-{pub_day}"
        
        return {
            'doi': doi,
            'pub_date': pub_date,
            'crossref_cites': crossref_cites,
            'openalex_cites': 0
        }
    
    print("⏳ Параллельное извлечение метаданных статей...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(process_single_item, items))
    
    return results

def process_articles_parallel(articles_data):
    """Параллельная обработка всех статей"""
    print("⏳ Параллельная обработка статей...")
    
    valid_dois = [article['doi'] for article in articles_data if article['doi'] != 'N/A']
    
    print(f"📊 Запрос цитирований для {len(valid_dois)} DOI...")
    openalex_counts = get_citing_count_openalex_batch(valid_dois)
    
    def process_single_article(article):
        doi = article['doi']
        openalex_cites = openalex_counts.get(doi, 0) if doi != 'N/A' else 0
        
        return {
            'doi': doi,
            'pub_date': article['pub_date'],
            'crossref_cites': article['crossref_cites'],
            'openalex_cites': openalex_cites
        }
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(process_single_article, articles_data))
    
    return results

def calculate_metrics_parallel(articles_data, progress_callback=None):
    """Параллельный расчет метрик по методологии Colab"""
    try:
        current_date = datetime.now()
        
        citation_period_start = current_date - timedelta(days=18*30)
        citation_period_end = current_date - timedelta(days=6*30)
        publication_period_start = current_date - timedelta(days=43*30)
        publication_period_end = current_date - timedelta(days=19*30)
        
        print(f"📅 Период публикаций для IF: {publication_period_start.strftime('%Y-%m-%d')} - {publication_period_end.strftime('%Y-%m-%d')}")
        
        total_articles = len(articles_data)
        
        # Расчет CiteScore
        total_crossref_citations = sum(item['crossref_cites'] for item in articles_data)
        total_openalex_citations = sum(item['openalex_cites'] for item in articles_data)
        
        citescore_crossref = total_crossref_citations / total_articles if total_articles > 0 else 0
        citescore_openalex = total_openalex_citations / total_articles if total_articles > 0 else 0
        citescore_diff = abs(citescore_crossref - citescore_openalex)
        
        # Фильтрация статей для Impact Factor
        articles_for_if = [
            article for article in articles_data 
            if (article['pub_date'] >= publication_period_start.strftime('%Y-%m-%d') and 
                article['pub_date'] <= publication_period_end.strftime('%Y-%m-%d'))
        ]
        
        print(f"📊 Статей в знаменателе IF (43-19 мес): {len(articles_for_if)}")
        
        # Расчет Impact Factor
        if_crossref_numerator = 0
        if_openalex_numerator = 0
        if_denominator = len(articles_for_if)
        
        print("⏳ Расчет Impact Factor...")
        
        for i, article in enumerate(articles_for_if):
            # Crossref: используем все цитирования
            crossref_cites_in_period = article['crossref_cites']
            if_crossref_numerator += crossref_cites_in_period
            
            # OpenAlex: считаем только цитирования в периоде 18-6 месяцев назад
            openalex_cites_in_period = 0
            if article['doi'] != 'N/A':
                citing_articles = get_citing_articles_openalex_with_dates(article['doi'])
                for citing_article in citing_articles:
                    cite_date = citing_article['date']
                    if (cite_date >= citation_period_start.strftime('%Y-%m-%d') and 
                        cite_date <= citation_period_end.strftime('%Y-%m-%d')):
                        openalex_cites_in_period += 1
            
            if_openalex_numerator += openalex_cites_in_period
            
            if progress_callback and i % 5 == 0:
                progress = 0.7 + 0.3 * (i / len(articles_for_if))
                progress_callback(progress)
            
            if i % 10 == 0 or i == len(articles_for_if) - 1:
                print(f"Обработано для IF: {i+1}/{len(articles_for_if)} статей")
        
        impact_factor_crossref = if_crossref_numerator / if_denominator if if_denominator > 0 else 0
        impact_factor_openalex = if_openalex_numerator / if_denominator if if_denominator > 0 else 0
        impact_factor_diff = abs(impact_factor_crossref - impact_factor_openalex)
        
        # Возвращаем ВСЕ необходимые поля
        return {
            'citescore_crossref': citescore_crossref,
            'citescore_openalex': citescore_openalex,
            'citescore_diff': citescore_diff,
            'impact_factor_crossref': impact_factor_crossref,
            'impact_factor_openalex': impact_factor_openalex,
            'impact_factor_diff': impact_factor_diff,
            'total_articles': total_articles,
            'if_denominator': if_denominator,
            'total_crossref_citations': total_crossref_citations,
            'total_openalex_citations': total_openalex_citations,
            'if_crossref_numerator': if_crossref_numerator,
            'if_openalex_numerator': if_openalex_numerator
        }
        
    except Exception as e:
        print(f"❌ Ошибка в calculate_metrics_parallel: {e}")
        import traceback
        traceback.print_exc()
        # Возвращаем значения по умолчанию при ошибке
        return {
            'citescore_crossref': 0,
            'citescore_openalex': 0,
            'citescore_diff': 0,
            'impact_factor_crossref': 0,
            'impact_factor_openalex': 0,
            'impact_factor_diff': 0,
            'total_articles': 0,
            'if_denominator': 0,
            'total_crossref_citations': 0,
            'total_openalex_citations': 0,
            'if_crossref_numerator': 0,
            'if_openalex_numerator': 0
        }

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
            items = fetch_articles_parallel(issn, from_date, until_date, use_cache)
            if_items.extend(items)

        cs_items = []
        for year in cs_publication_years:
            from_date = f"{year}-01-01"
            until_date = f"{year}-12-31"
            items = fetch_articles_parallel(issn, from_date, until_date, use_cache)
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
                'Цитирования в периоде': 0
            } for item in if_items
        ]

        cs_citation_data = [
            {
                'DOI': item.get('DOI', 'N/A'),
                'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                'Цитирования (Crossref)': item.get('is-referenced-by-count', 0),
                'Цитирования (OpenAlex)': 0,
                'Цитирования в периоде': 0
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
            items = fetch_articles_parallel(issn, from_date, until_date, use_cache)
            if_items.extend(items)
            all_articles[year] = items
            print(f"Год {year}: Найдено {len(items)} статей")

        cs_items = []
        for year in cs_publication_years:
            if year not in all_articles:
                from_date = f"{year}-01-01"
                until_date = f"{year}-12-31"
                items = fetch_articles_parallel(issn, from_date, until_date, use_cache)
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
        if_citation_data = []
        
        dois_if = [item.get('DOI') for item in if_items if item.get('DOI') != 'N/A']
        
        if use_parallel and dois_if:
            print(f" Параллельный анализ {len(dois_if)} DOI для ИФ...")
            openalex_counts = get_citing_count_openalex_batch(dois_if)
            
            for item in if_items:
                doi = item.get('DOI', 'N/A')
                crossref_cites = item.get('is-referenced-by-count', 0)
                
                if doi != 'N/A' and doi in openalex_counts:
                    openalex_count = openalex_counts[doi]
                    A_if_current += openalex_count
                    valid_dois += 1
                    if_citation_data.append({
                        'DOI': doi,
                        'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                        'Дата публикации': item.get('published', {}).get('date-parts', [[None, None, None]])[0][:3],
                        'Цитирования (Crossref)': crossref_cites,
                        'Цитирования (OpenAlex)': openalex_count,
                        'Цитирования в периоде': openalex_count
                    })
                else:
                    if_citation_data.append({
                        'DOI': doi,
                        'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                        'Дата публикации': item.get('published', {}).get('date-parts', [[None, None, None]])[0][:3],
                        'Цитирования (Crossref)': crossref_cites,
                        'Цитирования (OpenAlex)': 0,
                        'Цитирования в периоде': 0
                    })
        else:
            for i, item in enumerate(if_items):
                doi = item.get('DOI', 'N/A')
                crossref_cites = item.get('is-referenced-by-count', 0)
                if doi != 'N/A':
                    _, openalex_count = get_single_openalex_count(doi)
                    A_if_current += openalex_count
                    valid_dois += 1
                    if_citation_data.append({
                        'DOI': doi,
                        'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                        'Дата публикации': item.get('published', {}).get('date-parts', [[None, None, None]])[0][:3],
                        'Цитирования (Crossref)': crossref_cites,
                        'Цитирования (OpenAlex)': openalex_count,
                        'Цитирования в периоде': openalex_count
                    })
                else:
                    if_citation_data.append({
                        'DOI': doi,
                        'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                        'Дата публикации': item.get('published', {}).get('date-parts', [[None, None, None]])[0][:3],
                        'Цитирования (Crossref)': crossref_cites,
                        'Цитирования (OpenAlex)': 0,
                        'Цитирования в периоде': 0
                    })
        
        print(f"Обработано DOI: {valid_dois}/{B_if}, Цитирований в {current_year}: {A_if_current}")

        A_cs_current = sum(item.get('is-referenced-by-count', 0) for item in cs_items)
        cs_citation_data = [
            {
                'DOI': item.get('DOI', 'N/A'),
                'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                'Дата публикации': item.get('published', {}).get('date-parts', [[None, None, None]])[0][:3],
                'Цитирования (Crossref)': item.get('is-referenced-by-count', 0),
                'Цитирования (OpenAlex)': 0,
                'Цитирования в периоде': 0
            } for item in cs_items
        ]

        current_if = A_if_current / B_if if B_if > 0 else 0
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
            'parallel_workers': max_workers
        }

    except Exception as e:
        print(f"Ошибка в calculate_metrics_enhanced для ISSN {issn}: {e}")
        if progress_callback:
            progress_callback(1.0)
        return None

def calculate_metrics_dynamic(issn, journal_name="Не указано", use_cache=True, progress_callback=None, use_parallel=True, max_workers=20):
    """ДИНАМИЧЕСКАЯ функция для расчета метрик по методологии Google Colab"""
    global total_requests, failed_requests
    
    try:
        print(f"Запуск calculate_metrics_dynamic для ISSN {issn}")
        if not validate_issn(issn):
            print(f"Неверный формат ISSN: {issn}")
            return None

        # Сброс статистики
        total_requests = 0
        failed_requests = 0
        
        start_time = time.time()
        current_date = datetime.now()
        journal_field = detect_journal_field(issn, journal_name)

        if progress_callback:
            progress_callback(0.0)
            print("Начало сбора статей из Crossref...")

        # Периоды по методологии Colab
        until_date = current_date - timedelta(days=4*30)
        from_date = current_date - timedelta(days=52*30)
        
        from_date_str = from_date.strftime('%Y-%m-%d')
        until_date_str = until_date.strftime('%Y-%m-%d')

        print(f"🔍 Поиск статей за период: {from_date_str} - {until_date_str}")
        print(f"📖 Журнал ISSN: {issn}")
        print("⏳ Параллельная загрузка данных из Crossref...")

        items = fetch_articles_parallel(issn, from_date_str, until_date_str, use_cache)
        
        print(f"✅ Найдено статей: {len(items)}")
        
        if len(items) == 0:
            print("Нет статей для анализа")
            if progress_callback:
                progress_callback(1.0)
            return None

        if progress_callback:
            progress_callback(0.2)
            print("Извлечение метаданных статей...")

        articles_data = extract_article_info_parallel(items)
        
        if progress_callback:
            progress_callback(0.4)
            print("Обработка цитирований...")

        processed_articles = process_articles_parallel(articles_data)
        
        if progress_callback:
            progress_callback(0.7)
            print("Расчет метрик...")

        metrics = calculate_metrics_parallel(processed_articles, progress_callback)
        
        end_time = time.time()
        total_time = end_time - start_time
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)
        
        success_rate = ((total_requests - failed_requests) / total_requests * 100) if total_requests > 0 else 0
        processing_speed = len(items) / total_time if total_time > 0 else 0

        if progress_callback:
            progress_callback(1.0)
            print("Анализ завершен")

        # Создаем таблицу для отображения
        def create_table_row(idx, article):
            return [
                idx + 1, 
                article['doi'], 
                article['pub_date'], 
                article['crossref_cites'], 
                article['openalex_cites']
            ]
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            table_data = list(executor.map(
                lambda x: create_table_row(x[0], x[1]), 
                enumerate(processed_articles)
            ))
        
        articles_df = pd.DataFrame(table_data, columns=['№', 'DOI', 'Publication Date', 'Crossref Citations', 'OpenAlex Citations'])

        # Создаем корректный результат со всеми необходимыми полями
        result = {
            # Основные метрики из динамического анализа
            'citescore_crossref': metrics['citescore_crossref'],
            'citescore_openalex': metrics['citescore_openalex'],
            'citescore_diff': metrics['citescore_diff'],
            'impact_factor_crossref': metrics['impact_factor_crossref'],
            'impact_factor_openalex': metrics['impact_factor_openalex'],
            'impact_factor_diff': metrics['impact_factor_diff'],
            
            # Статистические данные
            'total_articles': metrics['total_articles'],
            'if_denominator': metrics['if_denominator'],
            'total_crossref_citations': metrics['total_crossref_citations'],
            'total_openalex_citations': metrics['total_openalex_citations'],
            'if_crossref_numerator': metrics['if_crossref_numerator'],
            'if_openalex_numerator': metrics['if_openalex_numerator'],
            
            # Данные для отображения
            'articles_data': processed_articles,
            'articles_df': articles_df,
            
            # Общая информация
            'analysis_date': current_date.strftime('%Y-%m-%d %H:%M:%S'),
            'journal_field': journal_field,
            'self_citation_rate': 0.05,
            'total_self_citations': int(metrics['total_crossref_citations'] * 0.05),
            'issn': issn,
            'journal_name': journal_name,
            
            # Информация о параллельной обработке
            'parallel_processing': use_parallel,
            'parallel_workers': max_workers,
            
            # Статистика производительности
            'total_requests': total_requests,
            'failed_requests': failed_requests,
            'success_rate': success_rate,
            'processing_speed': processing_speed,
            'analysis_time_seconds': total_time,
            'analysis_time_formatted': f"{minutes} мин {seconds} сек",
            
            # Поля для совместимости с другими режимами
            'current_if': metrics['impact_factor_openalex'],  # Для совместимости
            'current_citescore': metrics['citescore_openalex'],  # Для совместимости
            'total_cites_if': metrics['if_openalex_numerator'],  # Для совместимости
            'total_articles_if': metrics['if_denominator'],  # Для совместимости
            'total_cites_cs': metrics['total_openalex_citations'],  # Для совместимости
            'total_articles_cs': metrics['total_articles'],  # Для совместимости
            
            # Пустые поля для совместимости
            'if_forecasts': {},
            'citescore_forecasts': {},
            'multipliers': {},
            'citation_distribution': {},
            'if_citation_data': [],
            'cs_citation_data': [],
            'if_publication_years': [],
            'cs_publication_years': [],
            'seasonal_coefficients': get_seasonal_coefficients(journal_field),
            'citation_model_data': [],
            
            # Периоды для отображения
            'if_publication_period': [from_date, until_date],
            'if_citation_period': [current_date - timedelta(days=18*30), current_date - timedelta(days=6*30)],
            'cs_publication_period': [from_date, until_date],
            'cs_citation_period': [from_date, until_date]
        }

        print(f"✅ Динамический анализ завершен успешно")
        print(f"📊 Результаты: IF Crossref={metrics['impact_factor_crossref']:.2f}, IF OpenAlex={metrics['impact_factor_openalex']:.2f}")
        print(f"📊 Результаты: CS Crossref={metrics['citescore_crossref']:.2f}, CS OpenAlex={metrics['citescore_openalex']:.2f}")

        return result

    except Exception as e:
        print(f"❌ Ошибка в calculate_metrics_dynamic для ISSN {issn}: {e}")
        import traceback
        traceback.print_exc()
        if progress_callback:
            progress_callback(1.0)
        return None

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
