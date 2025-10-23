# Количество строк: 712
# Изменение: +247 строк (асинхронные запросы, batch OpenAlex, название журнала, время до первого цитирования)

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
            print(f"Загружен кэш для ключа: {cache_key}")
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
    print(f"Определение названия журнала для ISSN: {issn}")
    name = get_journal_name_from_crossref(issn)
    if name == "Неизвестный журнал":
        print("CrossRef не найден, пробуем OpenAlex...")
        name = get_journal_name_from_openalex(issn)
    print(f"Найдено название: {name}")
    return name

async def fetch_articles_async(session: aiohttp.ClientSession, issn: str, from_date: str, 
                             until_date: str, semaphore: asyncio.Semaphore) -> List[Dict]:
    """Асинхронное получение статей через CrossRef"""
    cache_key = get_cache_key("fetch_articles_async", issn, from_date, until_date)
    cached = load_from_cache(cache_key)
    if cached:
        print(f"Загружен кэш статей: {len(cached)}")
        return cached

    async with semaphore:
        items = []
        cursor = "*"
        excluded_types = {
            'editorial', 'letter', 'correction', 'retraction',
            'book-review', 'news', 'announcement', 'abstract'
        }
        current_page = 0

        while True:
            params = {
                'filter': f'issn:{issn},from-pub-date:{from_date},until-pub-date:{until_date}',
                'rows': 1000,
                'cursor': cursor,
                'mailto': 'example@example.com'
            }
            current_page += 1
            print(f"Страница {current_page} для {issn} ({from_date}–{until_date})")
            
            data = await fetch_json_async(session, base_url_crossref + "/works", params)
            if not data or 'message' not in data:
                break
                
            message = data['message']
            filtered_items = [
                item for item in message['items'] 
                if item.get('type', '').lower() not in excluded_types
            ]
            items.extend(filtered_items)
            print(f"Получено {len(filtered_items)} статей на странице {current_page}")
            
            cursor = message.get('next-cursor')
            if not cursor or len(message['items']) == 0:
                print(f"Завершено, всего {len(items)} статей")
                break
            await asyncio.sleep(0.2)  # Rate limiting

        if items:
            save_to_cache(items, cache_key)
        return items

async def fetch_citations_batch(session: aiohttp.ClientSession, dois: List[str], 
                              start_date: date, end_date: date, 
                              semaphore: asyncio.Semaphore) -> Dict[str, Dict]:
    """Batch-запрос цитирований для до 200 DOI"""
    if not dois:
        return {}
    
    # OpenAlex поддерживает до 200 DOI в filter
    doi_filter = ",".join([f"doi:{doi}" for doi in dois[:200]])
    url = f"{base_url_openalex}?filter=cited_by:{doi_filter}&per-page=200"
    
    async with semaphore:
        try:
            data = await fetch_json_async(session, url)
            if not data or not data.get('results'):
                return {doi: {'count': 0, 'total_count': 0, 'first_citation': None, 'is_self': False} 
                       for doi in dois}
            
            # Группируем по цитируемому DOI
            results = defaultdict(lambda: {'count': 0, 'first_citation': None, 'is_self_cites': 0})
            
            for work in data['results']:
                # Извлекаем цитируемый DOI из referenced_works
                referenced_works = work.get('referenced_works', [])
                if not referenced_works:
                    continue
                    
                # Берем первый referenced DOI (упрощение)
                cited_doi = None
                for ref in referenced_works:
                    if ref.startswith('https://doi.org/'):
                        cited_doi = ref.replace('https://doi.org/', '')
                        break
                
                if cited_doi and cited_doi in dois:
                    pub_date_str = work.get('publication_date')
                    if pub_date_str:
                        try:
                            cite_date = datetime.strptime(pub_date_str, '%Y-%m-%d').date()
                            if start_date <= cite_date <= end_date:
                                results[cited_doi]['count'] += 1
                                if (results[cited_doi]['first_citation'] is None or 
                                    cite_date < results[cited_doi]['first_citation']):
                                    results[cited_doi]['first_citation'] = cite_date
                        except ValueError:
                            pass
            
            # Получаем total_count для каждого DOI отдельно
            total_tasks = []
            for doi in dois:
                if doi not in results:
                    results[doi] = {'count': 0, 'first_citation': None, 'is_self_cites': 0}
                
                task = fetch_json_async(session, f"{base_url_openalex}?filter=doi:{doi}")
                total_tasks.append((doi, task))
            
            total_results = await asyncio.gather(*(task for _, task in total_tasks))
            
            for (doi, _), total_data in zip(total_tasks, total_results):
                if total_data and total_data.get('results'):
                    total_count = total_data['results'][0].get('cited_by_count', 0)
                    results[doi]['total_count'] = total_count
            
            # Простая проверка самоцитирования (по журналу)
            for doi in dois:
                results[doi]['is_self'] = results[doi]['is_self_cites'] > 0
            
            return dict(results)
            
        except Exception as e:
            print(f"Batch error для {len(dois)} DOI: {e}")
            return {doi: {'count': 0, 'total_count': 0, 'first_citation': None, 'is_self': False} for doi in dois}

async def fetch_single_citation_details(session: aiohttp.ClientSession, doi: str, 
                                      start_date: date, end_date: date,
                                      journal_issn: str) -> Dict:
    """Детальный анализ для одного DOI"""
    cache_key = get_cache_key("single_citation", doi, start_date, end_date)
    cached = load_from_cache(cache_key)
    if cached:
        return cached
    
    url = f"{base_url_openalex}?filter=doi:{doi}"
    data = await fetch_json_async(session, url)
    
    if not data or not data.get('results'):
        result = {'doi': doi, 'count': 0, 'total_count': 0, 'first_citation': None, 'is_self': False}
        save_to_cache(result, cache_key)
        return result
    
    work = data['results'][0]
    total_count = work.get('cited_by_count', 0)
    work_id = work['id'].split('/')[-1]
    
    # Получаем цитирующие работы
    citations_url = f"{base_url_openalex}?filter=cites:{work_id}&per-page=200"
    citations_data = await fetch_json_async(session, citations_url)
    
    count = 0
    first_citation = None
    self_cites = 0
    
    if citations_data and citations_data.get('results'):
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
                        citation_issn = citation.get('primary_venue', {}).get('issn', [])
                        if isinstance(citation_issn, list) and journal_issn in citation_issn:
                            self_cites += 1
                except ValueError:
                    pass
    
    result = {
        'doi': doi, 
        'count': count, 
        'total_count': total_count, 
        'first_citation': first_citation,
        'is_self': self_cites > 0,
        'self_cites_count': self_cites
    }
    save_to_cache(result, cache_key)
    return result

async def process_dois_batch(session: aiohttp.ClientSession, dois: List[str], 
                           start_date: date, end_date: date, journal_issn: str,
                           semaphore: asyncio.Semaphore) -> List[Dict]:
    """Обработка батча DOI с детальным анализом"""
    # Batch для общего подсчета
    batch_results = await fetch_citations_batch(session, dois, start_date, end_date, semaphore)
    
    # Детальный анализ для каждого DOI
    detailed_tasks = [
        fetch_single_citation_details(session, doi, start_date, end_date, journal_issn)
        for doi in dois
    ]
    
    detailed_results = await asyncio.gather(*detailed_tasks)
    
    # Объединяем результаты
    final_results = []
    for doi, detailed in zip(dois, detailed_results):
        batch_count = batch_results.get(doi, {}).get('count', 0)
        final_results.append({
            **detailed,
            'batch_count': batch_count  # Для сравнения
        })
    
    return final_results

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
    
    if not validate_issn(issn):
        print(f"Неверный формат ISSN: {issn}")
        return []

    cache_key = get_cache_key("fetch_articles_sync", issn, from_date, until_date)
    if use_cache:
        cached_data = load_from_cache(cache_key)
        if cached_data is not None:
            if progress_callback:
                progress_callback(0.2)
            return cached_data

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    semaphore = asyncio.Semaphore(5)
    result = loop.run_until_complete(
        fetch_articles_enhanced_async(issn, from_date, until_date, semaphore)
    )
    loop.close()
    
    if use_cache and result:
        save_to_cache(result, cache_key)
    
    if progress_callback:
        progress_callback(0.2)
    
    return result

async def calculate_metrics_async(issn: str, journal_name: str, mode: str = "enhanced", 
                                progress_callback=None) -> Optional[Dict]:
    """Асинхронный расчет метрик"""
    if progress_callback:
        progress_callback(0.0)
        print(f"Запуск {mode} анализа для ISSN {issn}")
    
    current_date = date.today()
    current_year = current_date.year
    journal_field = detect_journal_field(issn, journal_name)

    if progress_callback:
        progress_callback(0.05)

    # Определяем периоды
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
        # Точные периоды для enhanced
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
        print("Начало сбора статей из Crossref...")

    # Получение статей
    async with aiohttp.ClientSession() as session:
        semaphore = asyncio.Semaphore(10)
        
        # Статьи для ИФ
        print(f"Сбор статей для ИФ: {if_article_start}–{if_article_end}")
        if_items = await fetch_articles_async(
            session, issn, 
            if_article_start.strftime('%Y-%m-%d'), 
            if_article_end.strftime('%Y-%m-%d'), 
            semaphore
        )
        
        # Статьи для CiteScore
        print(f"Сбор статей для CS: {cs_article_start}–{cs_article_end}")
        cs_items = await fetch_articles_async(
            session, issn,
            cs_article_start.strftime('%Y-%m-%d'),
            cs_article_end.strftime('%Y-%m-%d'),
            semaphore
        )

    B_if = len(if_items)
    B_cs = len(cs_items)
    print(f"Статьи для ИФ: {B_if}, для CS: {B_cs}")
    
    if progress_callback:
        progress_callback(0.3)

    if B_if == 0 or B_cs == 0:
        print(f"Нет статей для анализа: IF={B_if}, CS={B_cs}")
        return None
    
    if progress_callback:
        progress_callback(0.35)
        print("Начало анализа цитирований через OpenAlex...")

    # Извлекаем DOI и получаем ISSN журнала
    if_dois = [item.get('DOI') for item in if_items if item.get('DOI') != 'N/A']
    cs_dois = [item.get('DOI') for item in cs_items if item.get('DOI') != 'N/A']
    all_dois = list(set(if_dois + cs_dois))
    
    # Получаем ISSN журнала из первой статьи
    journal_issn = None
    if if_items:
        journal_issn = if_items[0].get('ISSN', [issn])[0] if isinstance(if_items[0].get('ISSN'), list) else issn

    if progress_callback:
        progress_callback(0.4)

    # Batch обработка цитирований (по 200 DOI)
    citation_results = []
    batch_size = 200
    
    for i in range(0, len(all_dois), batch_size):
        batch_dois = all_dois[i:i+batch_size]
        print(f"Обработка батча {i//batch_size + 1}/{(len(all_dois)-1)//batch_size + 1} ({len(batch_dois)} DOI)")
        
        batch_result = await process_dois_batch(
            session, batch_dois, if_citation_start, if_citation_end, journal_issn, semaphore
        )
        citation_results.extend(batch_result)
        
        if progress_callback:
            batch_progress = 0.4 + 0.5 * (i + len(batch_dois)) / len(all_dois)
            progress_callback(batch_progress)
    
    if progress_callback:
        progress_callback(0.9)
        print("Расчет метрик...")

    # Преобразуем результаты в словарь
    citation_dict = {r['doi']: r for r in citation_results}
    
    # Строим данные для таблиц ИФ
    if_citation_data = []
    A_if_current = 0
    self_citations_if = 0
    
    for item in if_items:
        doi = item.get('DOI', 'N/A')
        crossref_cites = item.get('is-referenced-by-count', 0)
        pub_year = item.get('published', {}).get('date-parts', [[None]])[0][0]
        
        if doi != 'N/A' and doi in citation_dict:
            cit = citation_dict[doi]
            A_if_current += cit['count']
            self_citations_if += cit['self_cites_count']
            
            first_citation_str = cit['first_citation'].strftime('%Y-%m-%d') if cit['first_citation'] else None
            
            if_citation_data.append({
                'DOI': doi,
                'Год публикации': pub_year,
                'Цитирования (Crossref)': crossref_cites,
                'Цитирования (OpenAlex)': cit['total_count'],
                'Цитирования в периоде': cit['count'],
                'Время до первого цитирования': first_citation_str,
                'Самоцитирование': 'Да' if cit['is_self'] else 'Нет',
                'Количество самоцитирований': cit['self_cites_count']
            })
        else:
            if_citation_data.append({
                'DOI': doi,
                'Год публикации': pub_year,
                'Цитирования (Crossref)': crossref_cites,
                'Цитирования (OpenAlex)': 0,
                'Цитирования в периоде': 0,
                'Время до первого цитирования': None,
                'Самоцитирование': 'Нет',
                'Количество самоцитирований': 0
            })
    
    # Строим данные для таблиц CS
    cs_citation_data = []
    A_cs_current = 0
    self_citations_cs = 0
    
    for item in cs_items:
        doi = item.get('DOI', 'N/A')
        crossref_cites = item.get('is-referenced-by-count', 0)
        pub_year = item.get('published', {}).get('date-parts', [[None]])[0][0]
        
        if doi != 'N/A' and doi in citation_dict:
            cit = citation_dict[doi]
            A_cs_current += cit['count']
            self_citations_cs += cit['self_cites_count']
            
            first_citation_str = cit['first_citation'].strftime('%Y-%m-%d') if cit['first_citation'] else None
            
            cs_citation_data.append({
                'DOI': doi,
                'Год публикации': pub_year,
                'Цитирования (Crossref)': crossref_cites,
                'Цитирования (OpenAlex)': cit['total_count'],
                'Цитирования в периоде': cit['count'],
                'Время до первого цитирования': first_citation_str,
                'Самоцитирование': 'Да' if cit['is_self'] else 'Нет',
                'Количество самоцитирований': cit['self_cites_count']
            })
        else:
            cs_citation_data.append({
                'DOI': doi,
                'Год публикации': pub_year,
                'Цитирования (Crossref)': crossref_cites,
                'Цитирования (OpenAlex)': 0,
                'Цитирования в периоде': 0,
                'Время до первого цитирования': None,
                'Самоцитирование': 'Нет',
                'Количество самоцитирований': 0
            })

    current_if = A_if_current / B_if if B_if > 0 else 0
    current_citescore = A_cs_current / B_cs if B_cs > 0 else 0

    if progress_callback:
        progress_callback(1.0)
        print("Анализ завершен")

    # Для точного режима добавляем прогнозы
    if mode == "enhanced":
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

        multipliers = {
            'conservative': multiplier_conservative,
            'balanced': multiplier_balanced,
            'optimistic': multiplier_optimistic
        }

        citation_distribution = dict(seasonal_coefficients)
        if_publication_years = [current_year - 2, current_year - 1]
        cs_publication_years = list(range(current_year - 3, current_year + 1))
    else:
        if_forecasts = citescore_forecasts = multipliers = {}
        citation_distribution = {}
        if_publication_years = None
        cs_publication_years = None

    return {
        'current_if': current_if,
        'current_citescore': current_citescore,
        'if_forecasts': if_forecasts,
        'citescore_forecasts': citescore_forecasts,
        'multipliers': multipliers,
        'total_cites_if': A_if_current,
        'total_articles_if': B_if,
        'total_cites_cs': A_cs_current,
        'total_articles_cs': B_cs,
        'self_citations_if': self_citations_if,
        'self_citations_cs': self_citations_cs,
        'citation_distribution': citation_distribution,
        'if_citation_data': if_citation_data,
        'cs_citation_data': cs_citation_data,
        'analysis_date': current_date,
        'if_publication_period': [if_article_start, if_article_end],
        'if_citation_period': [if_citation_start, if_citation_end],
        'cs_publication_period': [cs_article_start, cs_article_end],
        'cs_citation_period': [cs_citation_start, cs_citation_end],
        'if_publication_years': if_publication_years,
        'cs_publication_years': cs_publication_years,
        'seasonal_coefficients': seasonal_coefficients if mode == "enhanced" else {},
        'journal_field': journal_field,
        'self_citation_rate': self_citations_if / max(A_if_current, 1),
        'issn': issn,
        'journal_name': journal_name,
        'mode': mode,
        'citation_model_data': []
    }

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
    """УСОВЕРШЕНСТВОВАННАЯ функция для расчета метрик"""
    # Автоматическое определение названия
    if journal_name == "Не указано":
        journal_name = get_journal_name(issn)
    
    print(f"Запуск calculate_metrics_enhanced для ISSN {issn}, журнал: {journal_name}")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(
        calculate_metrics_async(issn, journal_name, "enhanced", progress_callback)
    )
    loop.close()
    return result

def calculate_metrics_dynamic(issn, journal_name="Не указано", use_cache=True, progress_callback=None):
    """ДИНАМИЧЕСКАЯ функция для расчета метрик"""
    # Автоматическое определение названия
    if journal_name == "Не указано":
        journal_name = get_journal_name(issn)
    
    print(f"Запуск calculate_metrics_dynamic для ISSN {issn}, журнал: {journal_name}")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(
        calculate_metrics_async(issn, journal_name, "dynamic", progress_callback)
    )
    loop.close()
    return result

def calculate_metrics_fast(issn, journal_name="Не указано", use_cache=True):
    """БЫСТРАЯ функция для расчета метрик через Crossref"""
    if journal_name == "Не указано":
        journal_name = get_journal_name(issn)
    
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
                'Время до первого цитирования': None,
                'Самоцитирование': 'Нет',
                'Количество самоцитирований': 0
            } for item in if_items
        ]

        cs_citation_data = [
            {
                'DOI': item.get('DOI', 'N/A'),
                'Год публикации': item.get('published', {}).get('date-parts', [[None]])[0][0],
                'Цитирования (Crossref)': item.get('is-referenced-by-count', 0),
                'Цитирования (OpenAlex)': 0,
                'Цитирования в периоде': 0,
                'Время до первого цитирования': None,
                'Самоцитирование': 'Нет',
                'Количество самоцитирований': 0
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
            'self_citations_if': 0,
            'self_citations_cs': 0,
            'citation_distribution': dict(seasonal_coefficients),
            'if_citation_data': if_citation_data,
            'cs_citation_data': cs_citation_data,
            'analysis_date': current_date,
            'if_publication_years': if_publication_years,
            'cs_publication_years': cs_publication_years,
            'seasonal_coefficients': seasonal_coefficients,
            'journal_field': journal_field,
            'self_citation_rate': 0.05,
            'issn': issn,
            'journal_name': journal_name,
            'mode': 'fast',
            'citation_model_data': []
        }

    except Exception as e:
        print(f"Ошибка в calculate_metrics_fast: {e}")
        return None

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
