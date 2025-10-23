# Количество строк: 682
# Изменение: +217 строк (асинхронные запросы, batch OpenAlex, название журнала, время до первого цитирования)

import asyncio
import aiohttp
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
from typing import List, Dict, Optional, Tuple
warnings.filterwarnings('ignore')

base_url_crossref = "https://api.crossref.org"
base_url_openalex = "https://api.openalex.org"
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
            return cache_data['data']
        else:
            os.remove(cache_file)
            return None
    except:
        return None

async def fetch_json_async(session: aiohttp.ClientSession, url: str, params: dict = None) -> Dict:
    """Асинхронный GET запрос"""
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            return await resp.json()
    except Exception as e:
        print(f"Ошибка асинхронного запроса {url}: {e}")
        return None

def get_journal_name_from_crossref(issn: str) -> str:
    """Получение названия журнала через CrossRef"""
    cache_key = get_cache_key("journal_name_crossref", issn)
    cached = load_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        url = f"{base_url_crossref}/journals/{issn}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            name = data['message'].get('title', 'Неизвестный журнал')
            save_to_cache(name, cache_key)
            return name
    except:
        pass
    return "Неизвестный журнал"

def get_journal_name_from_openalex(issn: str) -> str:
    """Получение названия журнала через OpenAlex"""
    cache_key = get_cache_key("journal_name_openalex", issn)
    cached = load_from_cache(cache_key)
    if cached:
        return cached
    
    try:
        url = f"{base_url_openalex}/journals?filter=issn:{issn}&per-page=1"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data['results']:
                name = data['results'][0].get('title', 'Неизвестный журнал')
                save_to_cache(name, cache_key)
                return name
    except:
        pass
    return "Неизвестный журнал"

def get_journal_name(issn: str) -> str:
    """Получение названия журнала (CrossRef → OpenAlex)"""
    name = get_journal_name_from_crossref(issn)
    if name == "Неизвестный журнал":
        name = get_journal_name_from_openalex(issn)
    return name

async def fetch_articles_async(session: aiohttp.ClientSession, issn: str, from_date: str, 
                             until_date: str, semaphore: asyncio.Semaphore) -> List[Dict]:
    """Асинхронное получение статей через CrossRef"""
    cache_key = get_cache_key("fetch_articles", issn, from_date, until_date)
    cached = load_from_cache(cache_key)
    if cached:
        return cached

    async with semaphore:
        items = []
        cursor = "*"
        excluded_types = {
            'editorial', 'letter', 'correction', 'retraction',
            'book-review', 'news', 'announcement', 'abstract'
        }

        while True:
            params = {
                'filter': f'issn:{issn},from-pub-date:{from_date},until-pub-date:{until_date}',
                'rows': 1000,
                'cursor': cursor,
                'mailto': 'example@example.com'
            }
            data = await fetch_json_async(session, base_url_crossref + "/works", params)
            if not data or 'message' not in data:
                break
                
            message = data['message']
            filtered_items = [
                item for item in message['items'] 
                if item.get('type', '').lower() not in excluded_types
            ]
            items.extend(filtered_items)
            
            cursor = message.get('next-cursor')
            if not cursor or len(message['items']) == 0:
                break
            await asyncio.sleep(0.1)

        if items:
            save_to_cache(items, cache_key)
        return items

async def fetch_citations_batch(session: aiohttp.ClientSession, dois: List[str], 
                              start_date: date, end_date: date, 
                              semaphore: asyncio.Semaphore) -> Dict[str, Dict]:
    """Batch-запрос цитирований для 200 DOI"""
    if not dois:
        return {}
    
    # Формируем filter для OpenAlex (до 200 DOI)
    doi_filter = ",".join([f"doi:{doi}" for doi in dois[:200]])
    url = f"{base_url_openalex}?filter=cited_by:{doi_filter}&per-page=100"
    
    async with semaphore:
        try:
            data = await fetch_json_async(session, url)
            if not data or not data.get('results'):
                return {doi: {'count': 0, 'total_count': 0, 'first_citation': None} 
                       for doi in dois}
            
            results = {}
            for work in data['results']:
                cited_doi = work.get('referenced_works', [None])[0]
                if cited_doi and cited_doi in dois:
                    pub_date = work.get('publication_date')
                    if pub_date:
                        try:
                            cite_date = datetime.strptime(pub_date, '%Y-%m-%d').date()
                            if start_date <= cite_date <= end_date:
                                results.setdefault(cited_doi, {'count': 0, 'total_count': 0, 'first_citation': None})
                                results[cited_doi]['count'] += 1
                                if results[cited_doi]['first_citation'] is None or cite_date < results[cited_doi]['first_citation']:
                                    results[cited_doi]['first_citation'] = cite_date
                        except:
                            pass
            
            # Заполняем отсутствующие DOI
            for doi in dois:
                if doi not in results:
                    results[doi] = {'count': 0, 'total_count': 0, 'first_citation': None}
            
            return results
        except Exception as e:
            print(f"Batch error: {e}")
            return {doi: {'count': 0, 'total_count': 0, 'first_citation': None} for doi in dois}

async def fetch_single_citation_details(session: aiohttp.ClientSession, doi: str, 
                                      start_date: date, end_date: date) -> Dict:
    """Детали для одного DOI (если batch не покрыл)"""
    url = f"{base_url_openalex}?filter=doi:{doi}"
    data = await fetch_json_async(session, url)
    if not data or not data.get('results'):
        return {'doi': doi, 'count': 0, 'total_count': 0, 'first_citation': None, 'is_self': False}
    
    work = data['results'][0]
    total_count = work.get('cited_by_count', 0)
    work_id = work['id'].split('/')[-1]
    
    # Проверяем самоцитирование (упрощенно: цитирования из того же журнала)
    citations_url = f"{base_url_openalex}?filter=cites:{work_id}&per-page=100"
    citations_data = await fetch_json_async(session, citations_url)
    
    count = 0
    first_citation = None
    is_self = False
    
    if citations_data and citations_data.get('results'):
        journal_issn = work.get('primary_venue', {}).get('issn', [])
        if isinstance(journal_issn, list):
            journal_issn = journal_issn[0] if journal_issn else None
        
        for citation in citations_data['results']:
            cite_date_str = citation.get('publication_date')
            if cite_date_str:
                try:
                    cite_date = datetime.strptime(cite_date_str, '%Y-%m-%d').date()
                    if start_date <= cite_date <= end_date:
                        count += 1
                        if first_citation is None or cite_date < first_citation:
                            first_citation = cite_date
                        
                        # Проверка самоцитирования
                        if journal_issn and citation.get('primary_venue', {}).get('issn', []) == [journal_issn]:
                            is_self = True
                except:
                    pass
    
    return {
        'doi': doi, 
        'count': count, 
        'total_count': total_count, 
        'first_citation': first_citation,
        'is_self': is_self
    }

async def process_dois_batch(session: aiohttp.ClientSession, dois: List[str], 
                           start_date: date, end_date: date, semaphore: asyncio.Semaphore) -> List[Dict]:
    """Обработка батча DOI"""
    results = await fetch_citations_batch(session, dois, start_date, end_date, semaphore)
    
    # Для детального анализа делаем single запросы
    detailed_results = []
    tasks = []
    for doi in dois:
        task = fetch_single_citation_details(session, doi, start_date, end_date)
        tasks.append(task)
    
    detailed_batch = await asyncio.gather(*tasks)
    detailed_results.extend(detailed_batch)
    
    return detailed_results

async def fetch_articles_enhanced_async(issn: str, from_date: str, until_date: str, 
                                      semaphore: asyncio.Semaphore) -> List[Dict]:
    """Асинхронное получение статей"""
    async with aiohttp.ClientSession() as session:
        return await fetch_articles_async(session, issn, from_date, until_date, semaphore)

def fetch_articles_enhanced(issn: str, from_date: str, until_date: str, use_cache=True, 
                          progress_callback=None) -> List[Dict]:
    """Синхронная обертка для совместимости"""
    if progress_callback:
        progress_callback(0.1)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    semaphore = asyncio.Semaphore(5)
    result = loop.run_until_complete(
        fetch_articles_enhanced_async(issn, from_date, until_date, semaphore)
    )
    loop.close()
    
    if progress_callback:
        progress_callback(0.2)
    
    return result

async def calculate_metrics_async(issn: str, journal_name: str, mode: str = "enhanced", 
                                progress_callback=None) -> Optional[Dict]:
    """Асинхронный расчет метрик"""
    if progress_callback:
        progress_callback(0.0)
    
    current_date = date.today()
    journal_field = detect_journal_field(issn, journal_name)
    
    if progress_callback:
        progress_callback(0.05)
    
    # Определяем периоды
    current_year = current_date.year
    
    if mode == "dynamic":
        # Динамические периоды
        if_citation_start = current_date - timedelta(days=18*30)
        if_citation_end = current_date - timedelta(days=6*30)
        if_article_start = current_date - timedelta(days=42*30)
        if_article_end = current_date - timedelta(days=18*30)
        cs_citation_start = current_date - timedelta(days=52*30)
        cs_citation_end = current_date - timedelta(days=4*30)
        cs_article_start = cs_citation_start
        cs_article_end = cs_citation_end
    else:
        # Точные периоды
        if_article_start = date(current_year-2, 1, 1)
        if_article_end = date(current_year-1, 12, 31)
        if_citation_start = date(current_year, 1, 1)
        if_citation_end = date(current_year, 12, 31)
        cs_article_start = date(current_year-3, 1, 1)
        cs_article_end = date(current_year, 12, 31)
        cs_citation_start = cs_article_start
        cs_citation_end = cs_article_end
    
    if progress_callback:
        progress_callback(0.1)
    
    # Получение статей
    async with aiohttp.ClientSession() as session:
        semaphore = asyncio.Semaphore(10)
        
        # Статьи для ИФ
        if_items = await fetch_articles_async(
            session, issn, 
            if_article_start.strftime('%Y-%m-%d'), 
            if_article_end.strftime('%Y-%m-%d'), 
            semaphore
        )
        
        # Статьи для CiteScore
        cs_items = await fetch_articles_async(
            session, issn,
            cs_article_start.strftime('%Y-%m-%d'),
            cs_article_end.strftime('%Y-%m-%d'),
            semaphore
        )
    
    B_if = len(if_items)
    B_cs = len(cs_items)
    
    if progress_callback:
        progress_callback(0.3)
    
    if B_if == 0 or B_cs == 0:
        return None
    
    # Извлекаем DOI
    if_dois = [item.get('DOI') for item in if_items if item.get('DOI')]
    cs_dois = [item.get('DOI') for item in cs_items if item.get('DOI')]
    
    if progress_callback:
        progress_callback(0.4)
    
    # Batch обработка цитирований
    all_dois = list(set(if_dois + cs_dois))
    batch_size = 200
    citation_results = []
    
    for i in range(0, len(all_dois), batch_size):
        batch_dois = all_dois[i:i+batch_size]
        batch_result = await process_dois_batch(session, batch_dois, 
                                              if_citation_start, if_citation_end, semaphore)
        citation_results.extend(batch_result)
        
        if progress_callback:
            progress = 0.4 + 0.5 * (i + len(batch_dois)) / len(all_dois)
            progress_callback(progress)
    
    if progress_callback:
        progress_callback(0.9)
    
    # Преобразуем результаты
    citation_dict = {r['doi']: r for r in citation_results}
    
    # Строим данные для таблиц
    if_citation_data = []
    cs_citation_data = []
    A_if_current = 0
    A_cs_current = 0
    self_citations_if = 0
    self_citations_cs = 0
    
    for item in if_items:
        doi = item.get('DOI', 'N/A')
        crossref_cites = item.get('is-referenced-by-count', 0)
        pub_year = item.get('published', {}).get('date-parts', [[None]])[0][0]
        
        if doi in citation_dict:
            cit = citation_dict[doi]
            A_if_current += cit['count']
            if cit['is_self']:
                self_citations_if += cit['count']
            
            if_citation_data.append({
                'DOI': doi,
                'Год публикации': pub_year,
                'Цитирования (Crossref)': crossref_cites,
                'Цитирования (OpenAlex)': cit['total_count'],
                'Цитирования в периоде': cit['count'],
                'Время до первого цитирования': cit['first_citation'],
                'Самоцитирование': 'Да' if cit['is_self'] else 'Нет'
            })
        else:
            if_citation_data.append({
                'DOI': doi, 'Год публикации': pub_year,
                'Цитирования (Crossref)': crossref_cites, 'Цитирования (OpenAlex)': 0,
                'Цитирования в периоде': 0, 'Время до первого цитирования': None,
                'Самоцитирование': 'Нет'
            })
    
    for item in cs_items:
        doi = item.get('DOI', 'N/A')
        crossref_cites = item.get('is-referenced-by-count', 0)
        pub_year = item.get('published', {}).get('date-parts', [[None]])[0][0]
        
        if doi in citation_dict:
            cit = citation_dict[doi]
            A_cs_current += cit['count']
            if cit['is_self']:
                self_citations_cs += cit['count']
            
            cs_citation_data.append({
                'DOI': doi,
                'Год публикации': pub_year,
                'Цитирования (Crossref)': crossref_cites,
                'Цитирования (OpenAlex)': cit['total_count'],
                'Цитирования в периоде': cit['count'],
                'Время до первого цитирования': cit['first_citation'],
                'Самоцитирование': 'Да' if cit['is_self'] else 'Нет'
            })
        else:
            cs_citation_data.append({
                'DOI': doi, 'Год публикации': pub_year,
                'Цитирования (Crossref)': crossref_cites, 'Цитирования (OpenAlex)': 0,
                'Цитирования в периоде': 0, 'Время до первого цитирования': None,
                'Самоцитирование': 'Нет'
            })
    
    current_if = A_if_current / B_if if B_if > 0 else 0
    current_citescore = A_cs_current / B_cs if B_cs > 0 else 0
    
    if progress_callback:
        progress_callback(1.0)
    
    return {
        'current_if': current_if,
        'current_citescore': current_citescore,
        'total_cites_if': A_if_current,
        'total_articles_if': B_if,
        'total_cites_cs': A_cs_current,
        'total_articles_cs': B_cs,
        'self_citations_if': self_citations_if,
        'self_citations_cs': self_citations_cs,
        'if_citation_data': if_citation_data,
        'cs_citation_data': cs_citation_data,
        'analysis_date': current_date,
        'if_publication_period': [if_article_start, if_article_end],
        'if_citation_period': [if_citation_start, if_citation_end],
        'cs_publication_period': [cs_article_start, cs_article_end],
        'cs_citation_period': [cs_citation_start, cs_citation_end],
        'journal_field': journal_field,
        'issn': issn,
        'journal_name': journal_name,
        'mode': mode
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

def calculate_metrics_enhanced(issn, journal_name="Не указано", use_cache=True, progress_callback=None):
    """Точный анализ"""
    # Автоматическое определение названия
    if journal_name == "Не указано":
        journal_name = get_journal_name(issn)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(
        calculate_metrics_async(issn, journal_name, "enhanced", progress_callback)
    )
    loop.close()
    return result

def calculate_metrics_dynamic(issn, journal_name="Не указано", use_cache=True, progress_callback=None):
    """Динамический анализ"""
    # Автоматическое определение названия
    if journal_name == "Не указано":
        journal_name = get_journal_name(issn)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(
        calculate_metrics_async(issn, journal_name, "dynamic", progress_callback)
    )
    loop.close()
    return result

def calculate_metrics_fast(issn, journal_name="Не указано", use_cache=True):
    """Быстрый анализ (остается синхронным для скорости)"""
    if journal_name == "Не указано":
        journal_name = get_journal_name(issn)
    
    # Упрощенная версия без OpenAlex
    current_date = date.today()
    current_year = current_date.year
    
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
        return None
    
    A_if_current = sum(item.get('is-referenced-by-count', 0) for item in if_items)
    A_cs_current = sum(item.get('is-referenced-by-count', 0) for item in cs_items)
    
    current_if = A_if_current / B_if if B_if > 0 else 0
    current_citescore = A_cs_current / B_cs if B_cs > 0 else 0
    
    seasonal_coefficients = get_seasonal_coefficients(detect_journal_field(issn, journal_name))
    multiplier = 1.0  # Упрощенный множитель
    
    if_citation_data = [{
        'DOI': item.get('DOI', 'N/A'),
        'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
        'Цитирования (Crossref)': item.get('is-referenced-by-count', 0),
        'Цитирования (OpenAlex)': 0,
        'Цитирования в периоде': 0,
        'Время до первого цитирования': None,
        'Самоцитирование': 'Нет'
    } for item in if_items]
    
    cs_citation_data = [{
        'DOI': item.get('DOI', 'N/A'),
        'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
        'Цитирования (Crossref)': item.get('is-referenced-by-count', 0),
        'Цитирования (OpenAlex)': 0,
        'Цитирования в периоде': 0,
        'Время до первого цитирования': None,
        'Самоцитирование': 'Нет'
    } for item in cs_items]
    
    return {
        'current_if': current_if,
        'current_citescore': current_citescore,
        'total_cites_if': A_if_current,
        'total_articles_if': B_if,
        'total_cites_cs': A_cs_current,
        'total_articles_cs': B_cs,
        'self_citations_if': 0,
        'self_citations_cs': 0,
        'if_citation_data': if_citation_data,
        'cs_citation_data': cs_citation_data,
        'analysis_date': current_date,
        'if_publication_years': if_publication_years,
        'cs_publication_years': cs_publication_years,
        'journal_field': detect_journal_field(issn, journal_name),
        'issn': issn,
        'journal_name': journal_name,
        'mode': 'fast'
    }

def on_clear_cache_clicked(b):
    """Функция для очистки кэша"""
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
