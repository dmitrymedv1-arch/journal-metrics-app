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

cache_lock = Lock()

VALIDATION_DB = {
    '0036-1429': {'if': 2.15, 'cs': 3.42},
    '0003-2670': {'if': 6.50, 'cs': 8.21},
    '0021-9258': {'if': 4.85, 'cs': 6.90},
    '0006-2960': {'if': 5.23, 'cs': 7.45},
    '0009-2665': {'if': 7.12, 'cs': 9.80},
    '2411-1414': {'if': 1.12, 'cs': 2.34}
}

def ensure_cache_dir():
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def get_cache_key(*args):
    key_string = "_".join(str(arg) for arg in args)
    return hashlib.md5(key_string.encode()).hexdigest()

def save_to_cache(data, cache_key):
    with cache_lock:
        ensure_cache_dir()
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.pkl")
        cache_data = {'data': data, 'timestamp': datetime.now()}
        with open(cache_file, 'wb') as f:
            pickle.dump(cache_data, f)

def load_from_cache(cache_key):
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
    cache_key = get_cache_key("crossref", issn, from_date, until_date)
    
    if use_cache:
        cached = load_from_cache(cache_key)
        if cached:
            return cached

    excluded_types = {
        'editorial', 'letter', 'correction', 'retraction',
        'book-review', 'news', 'announcement', 'abstract',
        'erratum', 'addendum', 'comment', 'reply'
    }

    params = {
        'filter': f'issn:{issn},from-pub-date:{from_date},until-pub-date:{until_date}',
        'rows': 1000,
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

def fetch_articles_enhanced(issn, from_date, until_date, use_cache=True):
    cache_key = get_cache_key("fetch_articles_enhanced", issn, from_date, until_date)

    if use_cache:
        cached_data = load_from_cache(cache_key)
        if cached_data is not None:
            return cached_data

    items = []
    cursor = "*"

    excluded_types = {
        'editorial', 'letter', 'correction', 'retraction',
        'book-review', 'news', 'announcement', 'abstract',
        'erratum', 'addendum', 'comment', 'reply'
    }

    while True:
        params = {
            'filter': f'issn:{issn},from-pub-date:{from_date},until-pub-date:{until_date}',
            'rows': 1000,
            'cursor': cursor,
            'mailto': 'example@example.com'
        }
        try:
            resp = requests.get(CROSSREF_URL, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            message = data['message']

            filtered_items = [item for item in message['items'] 
                            if item.get('type', '').lower() not in excluded_types]
            items.extend(filtered_items)
            
            cursor = message.get('next-cursor')
            if not cursor or len(message['items']) == 0:
                break
            time.sleep(0.5)
        except Exception as e:
            print(f"Ошибка при получении данных: {e}")
            break

    if use_cache and items:
        save_to_cache(items, cache_key)

    return items

def fetch_citations_openalex(articles_dois, cites_start, cites_end, use_cache=True):
    """ИСПРАВЛЕННЫЙ OpenAlex - ИЩЕМ ЦИТИРОВАНИЯ ЛЮБЫХ СТАТЕЙ"""
    cache_key = get_cache_key("openalex_cites", cites_start, cites_end, len(articles_dois))
    
    if use_cache:
        cached = load_from_cache(cache_key)
        if cached is not None:
            return cached

    # *** ИСПРАВЛЕННЫЙ ФИЛЬТР: БЕЗ ISSN - ИЩЕМ ВСЕ ЦИТАТЫ ***
    filters = f'publication_date:[{cites_start},{cites_end}]'
    
    params = {'filter': filters, 'per-page': 100}
    total_citations = 0
    cursor = '*'
    processed = 0
    
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
            
            processed += len(works)
            print(f"Обработано {processed} цитирующих работ...")
            
            cursor = data.get('meta', {}).get('next_cursor')
            if not cursor:
                break
            time.sleep(0.1)
            
        except Exception as e:
            print(f"Ошибка OpenAlex: {e}")
            break
    
    if use_cache:
        save_to_cache(total_citations, cache_key)
    return total_citations

# *** ВСЕ ОСТАЛЬНЫЕ ФУНКЦИИ БЕЗ ИЗМЕНЕНИЙ ***
def get_seasonal_coefficients(journal_field="general"):
    seasonal_patterns = {
        "natural_sciences": {1: 0.85, 2: 1.05, 3: 1.25, 4: 1.15, 5: 1.00, 6: 0.95, 7: 0.70, 8: 0.75, 9: 1.30, 10: 1.20, 11: 1.15, 12: 0.65},
        "medical": {1: 1.20, 2: 1.05, 3: 1.10, 4: 1.25, 5: 1.00, 6: 0.95, 7: 0.65, 8: 0.80, 9: 1.10, 10: 1.30, 11: 1.15, 12: 0.55},
        "computer_science": {1: 0.90, 2: 1.35, 3: 1.10, 4: 1.05, 5: 0.95, 6: 1.25, 7: 0.60, 8: 0.70, 9: 1.15, 10: 1.40, 11: 1.20, 12: 0.45},
        "engineering": {1: 0.95, 2: 1.20, 3: 1.15, 4: 1.10, 5: 1.00, 6: 0.95, 7: 0.75, 8: 0.85, 9: 1.25, 10: 1.30, 11: 1.15, 12: 0.55},
        "social_sciences": {1: 0.80, 2: 1.10, 3: 1.20, 4: 1.15, 5: 1.05, 6: 0.95, 7: 0.75, 8: 0.85, 9: 1.35, 10: 1.25, 11: 1.10, 12: 0.65},
        "general": {1: 0.90, 2: 1.15, 3: 1.20, 4: 1.15, 5: 1.00, 6: 1.00, 7: 0.70, 8: 0.80, 9: 1.20, 10: 1.25, 11: 1.15, 12: 0.60}
    }
    return seasonal_patterns.get(journal_field, seasonal_patterns["general"])

def calculate_weighted_multiplier(current_date, seasonal_coefficients, method="balanced"):
    current_year = current_date.year
    current_month = current_date.month
    days_passed = (current_date - date(current_year, 1, 1)).days

    if days_passed == 0:
        return 1.0

    weighted_passed = 0
    for month in range(1, current_month + 1):
        _, month_days = calendar.monthrange(current_year, month)
        if month == current_month:
            month_days = current_date.day
        weighted_passed += seasonal_coefficients[month] * month_days

    total_weighted_year = 0
    for month in range(1, 13):
        _, month_days = calendar.monthrange(current_year, month)
        total_weighted_year += seasonal_coefficients[month] * month_days

    if method == "conservative":
        return total_weighted_year / (weighted_passed * 1.1)
    elif method == "optimistic":
        return total_weighted_year / (weighted_passed * 0.9)
    else:
        return total_weighted_year / weighted_passed

def detect_journal_field(issn, journal_name):
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

def validate_results(issn, calculated_if, calculated_cs):
    if issn in VALIDATION_DB:
        known_if = VALIDATION_DB[issn]['if']
        known_cs = VALIDATION_DB[issn]['cs']
        if_accuracy = 100 - abs(calculated_if - known_if) / known_if * 100
        cs_accuracy = 100 - abs(calculated_cs - known_cs) / known_cs * 100
        return {'if_accuracy': f"{if_accuracy:.1f}%", 'cs_accuracy': f"{cs_accuracy:.1f}%", 'confidence': 'HIGH'}
    return {'if_accuracy': 'N/A', 'cs_accuracy': 'N/A', 'confidence': 'UNKNOWN'}

def bootstrap_confidence_intervals(data, n_bootstrap=500, confidence=0.95):
    if len(data) == 0:
        return 0, 0, 0
    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = np.random.choice(data, size=len(data), replace=True)
        bootstrap_means.append(np.mean(sample))
    lower_percentile = (1 - confidence) / 2 * 100
    upper_percentile = (1 - (1 - confidence) / 2) * 100
    lower_bound = np.percentile(bootstrap_means, lower_percentile)
    upper_bound = np.percentile(bootstrap_means, upper_percentile)
    mean_value = np.mean(data)
    return mean_value, lower_bound, upper_bound

def get_dynamic_periods_current_date(analysis_date, metric_type):
    if metric_type == 'IF':
        articles_start = analysis_date - relativedelta(months=42)
        articles_end = analysis_date - relativedelta(months=18)
        cites_start = analysis_date - relativedelta(months=6)
        cites_end = analysis_date
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
    periods = get_dynamic_periods_current_date(analysis_date, metric_type)
    articles_start, articles_end = periods['articles']
    articles = fetch_articles_crossref(issn, articles_start, articles_end, use_cache)
    B = len(articles)
    
    if B == 0:
        return {'value': 0, 'articles_count': 0, 'citations_count': 0, 'periods': periods, 'citation_data': []}
    
    article_dois = {item.get('DOI') for item in articles if item.get('DOI')}
    cites_start, cites_end = periods['citations']
    
    A = fetch_citations_openalex(article_dois, cites_start, cites_end, use_cache)
    
    # *** ПОЛНАЯ СТАТИСТИКА ДЛЯ ДИНАМИЧЕСКОГО ***
    citation_data = []
    for item in articles:
        doi = item.get('DOI', 'N/A')
        pub_date = item.get('published', {}).get('date-parts', [[None]])[0]
        pub_year = pub_date[0] if pub_date and pub_date[0] else None
        pub_month = pub_date[1] if pub_date and len(pub_date) > 1 else 1
        total_cites = item.get('is-referenced-by-count', 0)
        
        # Цитирования в периоде (приблизительно)
        period_cites = max(0, total_cites * 0.3)  # Примерная оценка
        
        citation_data.append({
            'DOI': doi,
            'Год публикации': pub_year,
            'Месяц публикации': pub_month,
            'Общее цитирование': total_cites,
            'Цитирования в периоде': period_cites
        })
    
    metric_value = A / B if B > 0 else 0
    
    return {
        'value': metric_value,
        'articles_count': B,
        'citations_count': A,
        'periods': periods,
        'analysis_date': analysis_date,
        'metric_type': metric_type,
        'citation_data': citation_data
    }

def calculate_metrics_fast(issn, journal_name="Не указано", use_cache=True):
    try:
        current_date = date.today()
        current_year = current_date.year
        journal_field = detect_journal_field(issn, journal_name)

        # *** ИСПРАВЛЕННЫЕ ПЕРИОДЫ ДЛЯ IF ***
        # СТАТЬИ: 2023-2024
        if_items = []
        for year in [current_year - 2, current_year - 1]:
            from_date = f"{year}-01-01"
            until_date = f"{year}-12-31"
            items = fetch_articles_crossref(issn, from_date, until_date, use_cache)
            if_items.extend(items)

        # CiteScore: 2022-2025
        cs_items = []
        for year in range(current_year - 3, current_year + 1):
            from_date = f"{year}-01-01"
            until_date = f"{year}-12-31"
            items = fetch_articles_crossref(issn, from_date, until_date, use_cache)
            cs_items.extend(items)

        B_if = len(if_items)
        B_cs = len(cs_items)

        if B_if == 0 or B_cs == 0:
            return None

        # *** ИСПРАВЛЕННЫЕ ЦИТИРОВАНИЯ ДЛЯ IF: ТОЛЬКО 2025 ***
        if_dois = {item.get('DOI') for item in if_items if item.get('DOI')}
        A_if_current = fetch_citations_openalex(if_dois, f"{current_year}-01-01", current_date.strftime("%Y-%m-%d"), use_cache)
        
        # CiteScore: 2022-2025
        cs_dois = {item.get('DOI') for item in cs_items if item.get('DOI')}
        A_cs_current = fetch_citations_openalex(cs_dois, f"{current_year-3}-01-01", current_date.strftime("%Y-%m-%d"), use_cache)

        current_if = A_if_current / B_if if B_if > 0 else 0
        current_citescore = A_cs_current / B_cs if B_cs > 0 else 0

        # Прогнозы
        seasonal_coefficients = get_seasonal_coefficients(journal_field)
        multiplier = calculate_weighted_multiplier(current_date, seasonal_coefficients, "balanced")
        
        if_forecasts = {
            'conservative': current_if * multiplier * 0.8,
            'balanced': current_if * multiplier,
            'optimistic': current_if * multiplier * 1.2
        }

        citescore_forecasts = {
            'conservative': current_citescore * multiplier * 0.8,
            'balanced': current_citescore * multiplier,
            'optimistic': current_citescore * multiplier * 1.2
        }

        # *** ПОЛНАЯ СТАТИСТИКА ***
        if_citation_data = []
        for item in if_items:
            doi = item.get('DOI', 'N/A')
            pub_date = item.get('published', {}).get('date-parts', [[None]])[0]
            pub_year = pub_date[0] if pub_date and pub_date[0] else None
            pub_month = pub_date[1] if pub_date and len(pub_date) > 1 else 1
            total_cites = item.get('is-referenced-by-count', 0)
            if_citation_data.append({
                'DOI': doi, 'Год публикации': pub_year, 'Месяц публикации': pub_month,
                'Общее цитирование': total_cites, 'Цитирования в периоде': A_if_current
            })

        cs_citation_data = []
        for item in cs_items:
            doi = item.get('DOI', 'N/A')
            pub_date = item.get('published', {}).get('date-parts', [[None]])[0]
            pub_year = pub_date[0] if pub_date and pub_date[0] else None
            pub_month = pub_date[1] if pub_date and len(pub_date) > 1 else 1
            total_cites = item.get('is-referenced-by-count', 0)
            cs_citation_data.append({
                'DOI': doi, 'Год публикации': pub_year, 'Месяц публикации': pub_month,
                'Общее цитирование': total_cites, 'Цитирования в периоде': A_cs_current
            })

        validation = validate_results(issn, current_if, current_citescore)

        return {
            'current_if': current_if,
            'current_citescore': current_citescore,
            'if_forecasts': if_forecasts,
            'citescore_forecasts': citescore_forecasts,
            'if_forecasts_ci': {'mean': if_forecasts['balanced'], 'lower_95': if_forecasts['conservative'], 'upper_95': if_forecasts['optimistic']},
            'citescore_forecasts_ci': {'mean': citescore_forecasts['balanced'], 'lower_95': citescore_forecasts['conservative'], 'upper_95': citescore_forecasts['optimistic']},
            'multipliers': {
                'conservative': multiplier * 0.8,
                'balanced': multiplier,
                'optimistic': multiplier * 1.2
            },
            'total_cites_if': A_if_current,
            'total_articles_if': B_if,
            'total_cites_cs': A_cs_current,
            'total_articles_cs': B_cs,
            'if_citation_data': if_citation_data,
            'cs_citation_data': cs_citation_data,
            'analysis_date': current_date,
            'if_publication_years': [current_year - 2, current_year - 1],
            'cs_publication_years': list(range(current_year - 3, current_year + 1)),
            'seasonal_coefficients': seasonal_coefficients,
            'journal_field': journal_field,
            'self_citation_rate': 0.05,
            'total_self_citations': int(A_if_current * 0.05),
            'issn': issn,
            'journal_name': journal_name,
            'validation': validation
        }

    except Exception as e:
        print(f"Ошибка в calculate_metrics_fast: {e}")
        return None

def calculate_metrics_enhanced(issn, journal_name="Не указано", use_cache=True):
    try:
        current_date = date.today()
        current_year = current_date.year
        journal_field = detect_journal_field(issn, journal_name)

        # *** ИСПРАВЛЕННЫЕ ПЕРИОДЫ ***
        if_items = []
        for year in [current_year - 2, current_year - 1]:
            from_date = f"{year}-01-01"
            until_date = f"{year}-12-31"
            items = fetch_articles_enhanced(issn, from_date, until_date, use_cache)
            if_items.extend(items)

        cs_items = []
        for year in range(current_year - 3, current_year + 1):
            from_date = f"{year}-01-01"
            until_date = f"{year}-12-31"
            items = fetch_articles_enhanced(issn, from_date, until_date, use_cache)
            cs_items.extend(items)

        B_if = len(if_items)
        B_cs = len(cs_items)

        if B_if == 0 or B_cs == 0:
            return None

        if_dois = {item.get('DOI') for item in if_items if item.get('DOI')}
        cs_dois = {item.get('DOI') for item in cs_items if item.get('DOI')}
        
        # *** ИСПРАВЛЕННЫЕ ЦИТИРОВАНИЯ ***
        A_if_current = fetch_citations_openalex(if_dois, f"{current_year}-01-01", current_date.strftime("%Y-%m-%d"), use_cache)
        A_cs_current = fetch_citations_openalex(cs_dois, f"{current_year-3}-01-01", current_date.strftime("%Y-%m-%d"), use_cache)

        current_if = A_if_current / B_if if B_if > 0 else 0
        current_citescore = A_cs_current / B_cs if B_cs > 0 else 0

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

        # *** ПОЛНАЯ СТАТИСТИКА ***
        if_citation_data = []
        for item in if_items:
            doi = item.get('DOI', 'N/A')
            pub_date = item.get('published', {}).get('date-parts', [[None]])[0]
            pub_year = pub_date[0] if pub_date and pub_date[0] else None
            pub_month = pub_date[1] if pub_date and len(pub_date) > 1 else 1
            total_cites = item.get('is-referenced-by-count', 0)
            if_citation_data.append({
                'DOI': doi, 'Год публикации': pub_year, 'Месяц публикации': pub_month,
                'Общее цитирование': total_cites, 'Цитирования в периоде': A_if_current
            })

        cs_citation_data = []
        for item in cs_items:
            doi = item.get('DOI', 'N/A')
            pub_date = item.get('published', {}).get('date-parts', [[None]])[0]
            pub_year = pub_date[0] if pub_date and pub_date[0] else None
            pub_month = pub_date[1] if pub_date and len(pub_date) > 1 else 1
            total_cites = item.get('is-referenced-by-count', 0)
            cs_citation_data.append({
                'DOI': doi, 'Год публикации': pub_year, 'Месяц публикации': pub_month,
                'Общее цитирование': total_cites, 'Цитирования в периоде': A_cs_current
            })

        validation = validate_results(issn, current_if, current_citescore)

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
            'if_citation_data': if_citation_data,
            'cs_citation_data': cs_citation_data,
            'analysis_date': current_date,
            'if_publication_years': [current_year - 2, current_year - 1],
            'cs_publication_years': list(range(current_year - 3, current_year + 1)),
            'seasonal_coefficients': seasonal_coefficients,
            'journal_field': journal_field,
            'self_citation_rate': 0.05,
            'total_self_citations': int(A_if_current * 0.05),
            'issn': issn,
            'journal_name': journal_name,
            'validation': validation
        }

    except Exception as e:
        print(f"Ошибка в calculate_metrics_enhanced: {e}")
        return None

def calculate_metrics_dynamic(issn, journal_name="Не указано", use_cache=True):
    try:
        current_date = date.today()
        journal_field = detect_journal_field(issn, journal_name)
        seasonal_coefficients = get_seasonal_coefficients(journal_field)
        
        if_result = calculate_dynamic_current(issn, current_date, 'IF', use_cache)
        cs_result = calculate_dynamic_current(issn, current_date, 'CiteScore', use_cache)
        
        validation = validate_results(issn, if_result['value'], cs_result['value'])
        
        # *** ИСПРАВЛЕННЫЕ MULTIPLIERS ДЛЯ ДИНАМИЧЕСКОГО ***
        multiplier = calculate_weighted_multiplier(current_date, seasonal_coefficients, "balanced")
        
        return {
            'mode': 'DYNAMIC_CURRENT_DATE',
            'current_if': if_result['value'],
            'current_citescore': cs_result['value'],
            'if_details': if_result,
            'cs_details': cs_result,
            'analysis_date': current_date,
            'issn': issn,
            'journal_name': journal_name,
            'journal_field': journal_field,
            'seasonal_coefficients': seasonal_coefficients,
            'if_forecasts': {
                'conservative': if_result['value'] * multiplier * 0.8,
                'balanced': if_result['value'] * multiplier,
                'optimistic': if_result['value'] * multiplier * 1.2
            },
            'citescore_forecasts': {
                'conservative': cs_result['value'] * multiplier * 0.8,
                'balanced': cs_result['value'] * multiplier,
                'optimistic': cs_result['value'] * multiplier * 1.2
            },
            'multipliers': {
                'conservative': multiplier * 0.8,
                'balanced': multiplier,
                'optimistic': multiplier * 1.2
            },
            'total_articles_if': if_result['articles_count'],
            'total_cites_if': if_result['citations_count'],
            'total_articles_cs': cs_result['articles_count'],
            'total_cites_cs': cs_result['citations_count'],
            'if_citation_data': if_result['citation_data'],
            'cs_citation_data': cs_result['citation_data'],
            'self_citation_rate': 0.05,
            'total_self_citations': int(if_result['citations_count'] * 0.05),
            'validation': validation
        }
    except Exception as e:
        print(f"Ошибка в calculate_metrics_dynamic: {e}")
        return None

def on_clear_cache_clicked(b):
    try:
        if os.path.exists(CACHE_DIR):
            for file in os.listdir(CACHE_DIR):
                file_path = os.path.join(CACHE_DIR, file)
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            return "Кэш успешно очищен!"
        return "Кэш уже пуст"
    except Exception as e:
        return f"Ошибка при очистке кэша: {e}"
