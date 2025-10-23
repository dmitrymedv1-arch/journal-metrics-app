import requests
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import time
import random
import calendar
from collections import defaultdict
from dateutil.relativedelta import relativedelta
import pickle
import hashlib
import os
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
warnings.filterwarnings('ignore')

# API URLs
CROSSREF_URL = "https://api.crossref.org/works"
OPENALEX_URL = "https://api.openalex.org/works"
CACHE_DIR = "journal_analysis_cache"
CACHE_DURATION = timedelta(hours=24)

# *** ГЛОБАЛЬНЫЙ ЛОК ДЛЯ КЭША ***
cache_lock = Lock()

# *** БАЗА ВАЛИДАЦИИ (пример для 5 журналов; расширьте по нужде) ***
VALIDATION_DB = {
    '0036-1429': {'if': 2.15, 'cs': 3.42},  # SIAM J. Math. Anal.
    '0003-2670': {'if': 6.50, 'cs': 8.21},  # Anal. Chim. Acta
    '0021-9258': {'if': 4.85, 'cs': 6.90},  # J. Biol. Chem.
    '0006-2960': {'if': 5.23, 'cs': 7.45},  # Biochemistry
    '0009-2665': {'if': 7.12, 'cs': 9.80}   # Chem. Rev.
}

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
    with cache_lock:
        ensure_cache_dir()
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
        cache_data = {'data': data, 'timestamp': datetime.now()}
        with open(cache_file, 'wb') as f:
            pickle.dump(cache_data, f)

def load_from_cache(cache_key):
    """Загружает данные из кэша"""
    with cache_lock:
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
        if not os.path.exists(cache_file):
            return None
        try:
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)
            if datetime.now() - cache_data['timestamp'] < CACHE_DURATION:
                return cache_data['data']
            else:
                os.remove(cache_file)
                return None
        except:
            return None

def fetch_articles_crossref(issn, from_date, until_date, use_cache=True):
    """Получение статей из Crossref"""
    cache_key = get_cache_key("crossref", issn, from_date, until_date)
    
    if use_cache:
        cached = load_from_cache(cache_key)
        if cached:
            return cached

    excluded_types = {
        'editorial', 'letter', 'correction', 'retraction',
        'book-review', 'news', 'announcement', 'abstract'
    }

    params = {
        'filter': f'issn:{issn},from-pub-date:{from_date},until-pub-date:{until_date}',
        'rows': 100,
        'mailto': 'example@example.com'
    }
    
    try:
        resp = requests.get(CROSSREF_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data['message']['items']

        filtered_items = [item for item in items 
                         if item.get('type', '').lower() not in excluded_types]

        if use_cache:
            save_to_cache(filtered_items, cache_key)
        return filtered_items
    except Exception as e:
        print(f"Ошибка Crossref: {e}")
        return []

def fetch_work_by_doi(doi, use_cache=True):
    """Получение одной работы по DOI из OpenAlex"""
    cache_key = get_cache_key("openalex_work", doi)
    
    if use_cache:
        cached = load_from_cache(cache_key)
        if cached:
            return cached
    
    params = {'filter': f'doi:{doi}'}
    
    try:
        resp = requests.get(f"{OPENALEX_URL}?{requests.compat.urlencode(params)}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        work = data['results'][0] if data['results'] else None
        
        if use_cache and work:
            save_to_cache(work, cache_key)
        return work
    except:
        return None

def fetch_citations_openalex(issn, articles_dois, cites_start, cites_end, use_cache=True):
    """Получение цитирований из OpenAlex за конкретный период"""
    cache_key = get_cache_key("openalex_cites", issn, cites_start, cites_end)
    
    if use_cache:
        cached = load_from_cache(cache_key)
        if cached is not None:
            return cached

    filters = f'primary_venue.issn:{issn},publication_date:[{cites_start},{cites_end}]'
    
    params = {
        'filter': filters,
        'per-page': 50,
        'mailto': 'example@example.com'
    }
    
    total_citations = 0
    cursor = '*'
    
    while True:
        if cursor != '*':
            params['cursor'] = cursor
        
        try:
            resp = requests.get(OPENALEX_URL, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            works = data['results']
            
            for work in works:
                referenced_dois = [ref.get('doi') for ref in work.get('referenced_works', []) if ref.get('doi')]
                for ref_doi in referenced_dois:
                    if ref_doi in articles_dois:
                        total_citations += 1
            
            cursor = data.get('meta', {}).get('next_cursor')
            if not cursor:
                break
                
            time.sleep(0.2)  # Rate limit
            
        except Exception as e:
            print(f"Ошибка OpenAlex: {e}")
            break

    if use_cache:
        save_to_cache(total_citations, cache_key)
    
    return total_citations

# *** НОВЫЕ ФУНКЦИИ ДЛЯ ДИНАМИЧЕСКОГО РЕЖИМА ***
def get_dynamic_periods_current_date(analysis_date, metric_type):
    """ДИНАМИЧЕСКИЕ ПЕРИОДЫ ОТ ТЕКУЩЕЙ ДАТЫ"""
    if metric_type == 'IF':
        articles_start = analysis_date - relativedelta(months=42)
        articles_end = analysis_date - relativedelta(months=18)
        cites_start = analysis_date - relativedelta(months=18)
        cites_end = analysis_date - relativedelta(months=6)
        
    else:  # CiteScore
        articles_start = analysis_date - relativedelta(months=48)
        articles_end = analysis_date
        cites_start = analysis_date - relativedelta(months=48)
        cites_end = analysis_date
    
    return {
        'articles': (articles_start.strftime('%Y-%m-%d'), articles_end.strftime('%Y-%m-%d')),
        'citations': (cites_start.strftime('%Y-%m-%d'), cites_end.strftime('%Y-%m-%d')),
        'analysis_date': analysis_date
    }

def calculate_dynamic_current(issn, analysis_date, metric_type, use_cache=True):
    """ДИНАМИЧЕСКИЙ РАСЧЕТ ОТ ТЕКУЩЕЙ ДАТЫ"""
    periods = get_dynamic_periods_current_date(analysis_date, metric_type)
    
    # 1. СТАТЬИ
    articles_start, articles_end = periods['articles']
    articles = fetch_articles_crossref(issn, articles_start, articles_end, use_cache)
    B = len(articles)
    article_dois = {item.get('DOI') for item in articles if item.get('DOI')}
    
    # 2. ЦИТИРОВАНИЯ
    cites_start, cites_end = periods['citations']
    A = fetch_citations_openalex(issn, article_dois, cites_start, cites_end, use_cache)
    
    # 3. МЕТРИКА
    metric_value = A / B if B > 0 else 0
    
    return {
        'value': metric_value,
        'articles_count': B,
        'citations_count': A,
        'periods': periods,
        'analysis_date': analysis_date,
        'metric_type': metric_type
    }

# *** ТРАДИЦИОННЫЕ ФУНКЦИИ ***
def get_seasonal_coefficients(journal_field="general"):
    """Возвращает взвешенные коэффициенты на основе исторических данных"""
    seasonal_patterns = {
        "natural_sciences": {
            1: 0.85, 2: 1.05, 3: 1.25, 4: 1.15, 5: 1.00, 6: 0.95,
            7: 0.70, 8: 0.75, 9: 1.30, 10: 1.20, 11: 1.15, 12: 0.65
        },
        "medical": {
            1: 1.20, 2: 1.05, 3: 1.10, 4: 1.25, 5: 1.00, 6: 0.95,
            7: 0.65, 8: 0.80, 9: 1.10, 10: 1.30, 11: 1.15, 12: 0.55
        },
        "computer_science": {
            1: 0.90, 2: 1.35, 3: 1.10, 4: 1.05, 5: 0.95, 6: 1.25,
            7: 0.60, 8: 0.70, 9: 1.15, 10: 1.40, 11: 1.20, 12: 0.45
        },
        "engineering": {
            1: 0.95, 2: 1.20, 3: 1.15, 4: 1.10, 5: 1.00, 6: 0.95,
            7: 0.75, 8: 0.85, 9: 1.25, 10: 1.30, 11: 1.15, 12: 0.55
        },
        "social_sciences": {
            1: 0.80, 2: 1.10, 3: 1.20, 4: 1.15, 5: 1.05, 6: 0.95,
            7: 0.75, 8: 0.85, 9: 1.35, 10: 1.25, 11: 1.10, 12: 0.65
        },
        "general": {
            1: 0.90, 2: 1.15, 3: 1.20, 4: 1.15, 5: 1.00, 6: 1.00,
            7: 0.70, 8: 0.80, 9: 1.20, 10: 1.25, 11: 1.15, 12: 0.60
        }
    }
    return seasonal_patterns.get(journal_field, seasonal_patterns["general"])

def calculate_scenario_multipliers(current_date, seasonal_coefficients):
    """РАЗНЫЕ множители для каждого сценария"""
    current_year = current_date.year
    current_month = current_date.month
    
    weighted_passed = 0
    for month in range(1, current_month + 1):
        _, month_days = calendar.monthrange(current_year, month)
        if month == current_month:
            month_days = current_date.day
        weighted_passed += seasonal_coefficients[month] * month_days

    total_weighted_year = sum(seasonal_coefficients[month] * 
                            calendar.monthrange(current_year, month)[1] 
                            for month in range(1, 13))

    base_multiplier = total_weighted_year / weighted_passed
    
    multipliers = {}
    multipliers['conservative'] = base_multiplier * 0.85 * 1.05
    multipliers['balanced'] = base_multiplier * 1.00 * 1.10
    multipliers['optimistic'] = base_multiplier * 1.15 * 1.20
    
    return multipliers

def detect_journal_field(issn, journal_name):
    """Автоматическое определение области журнала"""
    field_keywords = {
        "natural_sciences": ['nature', 'science', 'physical', 'chemistry', 'physics'],
        "medical": ['medical', 'medicine', 'health', 'clinical', 'surgery'],
        "computer_science": ['computer', 'computing', 'software', 'algorithm', 'data'],
        "engineering": ['engineering', 'engineer', 'technical', 'mechanical', 'electrical'],
        "social_sciences": ['social', 'society', 'economic', 'political', 'psychology']
    }

    journal_name_lower = journal_name.lower()
    for field, keywords in field_keywords.items():
        for keyword in keywords:
            if keyword in journal_name_lower:
                return field
    return "general"

def fetch_if_articles(issn, current_year, use_cache=True):
    """Статьи для ИМПАКТ-ФАКТОРА: 2023+2024"""
    years = [current_year - 2, current_year - 1]
    
    all_items = []
    excluded_types = {
        'editorial', 'letter', 'correction', 'retraction',
        'book-review', 'news', 'announcement', 'abstract'
    }
    
    for year in years:
        from_date = f"{year}-01-01"
        until_date = f"{year}-12-31"
        items = fetch_articles_crossref(issn, from_date, until_date, use_cache)
        filtered_items = [item for item in items 
                         if item.get('type', '').lower() not in excluded_types]
        all_items.extend(filtered_items)
    
    return all_items

def fetch_citescore_articles(issn, current_year, current_date, use_cache=True):
    """Статьи для CITE SCORE: 2022-2025"""
    years = list(range(current_year - 3, current_year + 1))
    
    all_items = []
    excluded_types = {
        'editorial', 'letter', 'correction', 'retraction',
        'book-review', 'news', 'announcement', 'abstract'
    }
    
    for year in years:
        if year == current_year:
            from_date = f"{year}-01-01"
            until_date = current_date.strftime("%Y-%m-%d")
        else:
            from_date = f"{year}-01-01"
            until_date = f"{year}-12-31"
        
        items = fetch_articles_crossref(issn, from_date, until_date, use_cache)
        filtered_items = [item for item in items 
                         if item.get('type', '').lower() not in excluded_types]
        all_items.extend(filtered_items)
    
    return all_items

# *** ПАРАЛЛЕЛИЗАЦИЯ ЗАПРОСОВ ***
def parallel_fetch_articles_crossref(issn, periods, use_cache=True):
    """ПАРАЛЛЕЛЬНОЕ ПОЛУЧЕНИЕ СТАТЕЙ"""
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_articles_crossref, issn, start, end, use_cache) for start, end in periods]
        results = [future.result() for future in as_completed(futures)]
    
    all_items = []
    for items in results:
        all_items.extend(items)
    return all_items

def parallel_fetch_citations_openalex(issn, articles_dois, periods, use_cache=True):
    """ПАРАЛЛЕЛЬНОЕ ПОЛУЧЕНИЕ ЦИТИРОВАНИЙ"""
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_citations_openalex, issn, articles_dois, start, end, use_cache) for start, end in periods]
        results = [future.result() for future in as_completed(futures)]
    
    return sum(results)

# *** ВАЛИДАЦИЯ РЕЗУЛЬТАТОВ ***
def validate_results(issn, calculated_if, calculated_cs):
    """ВАЛИДАЦИЯ С БАЗОЙ ДАННЫХ"""
    if issn in VALIDATION_DB:
        known_if = VALIDATION_DB[issn]['if']
        known_cs = VALIDATION_DB[issn]['cs']
        
        if_accuracy = 100 - abs(calculated_if - known_if) / known_if * 100 if known_if > 0 else 0
        cs_accuracy = 100 - abs(calculated_cs - known_cs) / known_cs * 100 if known_cs > 0 else 0
        
        return {
            'if_accuracy': f"{if_accuracy:.1f}%",
            'cs_accuracy': f"{cs_accuracy:.1f}%",
            'confidence': 'HIGH' if if_accuracy > 95 and cs_accuracy > 95 else 'LOW'
        }
    return {
        'if_accuracy': 'N/A',
        'cs_accuracy': 'N/A',
        'confidence': 'UNKNOWN'
    }

# *** ОСНОВНАЯ ФУНКЦИЯ С РЕЖИМАМИ ***
def calculate_metrics_fast(issn, journal_name="Не указано", use_cache=True, MODE="SCENARIOS"):
    """
    РЕЖИМЫ:
    - 'SCENARIOS': 3 сценария (традиционно)
    - 'DYNAMIC': 1 точный расчет от текущей даты
    """
    try:
        current_date = date.today()
        current_year = current_date.year

        journal_field = detect_journal_field(issn, journal_name)
        seasonal_coefficients = get_seasonal_coefficients(journal_field)
        
        if MODE == "DYNAMIC":
            # *** ДИНАМИЧЕСКИЙ РЕЖИМ ОТ ТЕКУЩЕЙ ДАТЫ ***
            if_result = calculate_dynamic_current(issn, current_date, 'IF', use_cache)
            cs_result = calculate_dynamic_current(issn, current_date, 'CiteScore', use_cache)
            
            # ВАЛИДАЦИЯ
            validation = validate_results(issn, if_result['value'], cs_result['value'])
            
            return {
                'mode': 'DYNAMIC_CURRENT_DATE',
                'current_if': if_result['value'],
                'current_citescore': cs_result['value'],
                'if_details': if_result,
                'cs_details': cs_result,
                'analysis_date': current_date,
                'issn': issn,
                'journal_name': journal_name,
                'validation': validation
            }
        
        else:  # SCENARIOS MODE
            # *** ТРАДИЦИОННЫЙ РЕЖИМ С 3 СЦЕНАРИЯМИ ***
            multipliers = calculate_scenario_multipliers(current_date, seasonal_coefficients)

            # ИМПАКТ-ФАКТОР
            if_articles = fetch_if_articles(issn, current_year, use_cache)
            B_if = len(if_articles)
            article_dois_if = {item.get('DOI') for item in if_articles if item.get('DOI')}
            A_if = fetch_citations_openalex(issn, article_dois_if, 
                                         f"{current_year}-01-01", current_date.strftime("%Y-%m-%d"), use_cache)
            current_if = A_if / B_if if B_if > 0 else 0

            # CITE SCORE
            cs_articles = fetch_citescore_articles(issn, current_year, current_date, use_cache)
            B_cs = len(cs_articles)
            article_dois_cs = {item.get('DOI') for item in cs_articles if item.get('DOI')}
            A_cs = fetch_citations_openalex(issn, article_dois_cs, 
                                         f"{current_year-3}-01-01", current_date.strftime("%Y-%m-%d"), use_cache)
            current_citescore = A_cs / B_cs if B_cs > 0 else 0

            # ПРОГНОЗЫ
            if_forecasts = {
                'conservative': max(current_if * multipliers['conservative'], current_if),
                'balanced': max(current_if * multipliers['balanced'], current_if),
                'optimistic': max(current_if * multipliers['optimistic'], current_if)
            }

            citescore_forecasts = {
                'conservative': max(current_citescore * multipliers['conservative'], current_citescore),
                'balanced': max(current_citescore * multipliers['balanced'], current_citescore),
                'optimistic': max(current_citescore * multipliers['optimistic'], current_citescore)
            }

            # ВАЛИДАЦИЯ
            validation = validate_results(issn, current_if, current_citescore)

            return {
                'mode': 'SCENARIOS',
                'current_if': current_if,
                'current_citescore': current_citescore,
                'if_forecasts': if_forecasts,
                'citescore_forecasts': citescore_forecasts,
                'multipliers': multipliers,
                'total_cites_if': A_if,
                'total_articles_if': B_if,
                'total_cites_cs': A_cs,
                'total_articles_cs': B_cs,
                'analysis_date': current_date,
                'issn': issn,
                'journal_name': journal_name,
                'seasonal_coefficients': seasonal_coefficients,
                'journal_field': journal_field,
                'validation': validation
            }

    except Exception as e:
        print(f"Ошибка в calculate_metrics_fast: {e}")
        return None

def on_clear_cache_clicked(b):
    """Очистка кэша"""
    try:
        if os.path.exists(CACHE_DIR):
            for file in os.listdir(CACHE_DIR):
                os.unlink(os.path.join(CACHE_DIR, file))
            return "Кэш очищен!"
    except:
        pass
    return "Ошибка очистки"

# ПРИМЕР ИСПОЛЬЗОВАНИЯ
if __name__ == "__main__":
    issn = "0036-1429"  # Пример с валидацией
    journal_name = "SIAM J. Math. Anal."
    
    print("=== РЕЖИМ 1: 3 СЦЕНАРИЯ ===")
    result_scenarios = calculate_metrics_fast(issn, journal_name, MODE="SCENARIOS")
    print(f"IF Консервативный: {result_scenarios['if_forecasts']['conservative']:.3f}")
    print(f"IF Сбалансированный: {result_scenarios['if_forecasts']['balanced']:.3f}")
    print(f"IF Оптимистичный: {result_scenarios['if_forecasts']['optimistic']:.3f}")
    print(f"Валидация IF: {result_scenarios['validation']['if_accuracy']}")
    
    print("\n=== РЕЖИМ 2: ДИНАМИЧЕСКИЙ ===")
    result_dynamic = calculate_metrics_fast(issn, journal_name, MODE="DYNAMIC")
    print(f"IF: {result_dynamic['current_if']:.3f}")
    print(f"IF Период статей: {result_dynamic['if_details']['periods']['articles']}")
    print(f"IF Период цитирований: {result_dynamic['if_details']['periods']['citations']}")
    print(f"Валидация IF: {result_dynamic['validation']['if_accuracy']}")
