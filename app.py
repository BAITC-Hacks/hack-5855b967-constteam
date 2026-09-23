"""PODBOR: one-screen event matching with a verifiable tool-using agent."""
from __future__ import annotations

import html
import json
import os
import time
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from matcher import llm
from matcher.agent import AgentReport, run_agent
from matcher.data import CALENDAR_END, CALENDAR_START, DEFAULT_CSV, catalog_version, load_catalog
from matcher.engine import FOUND, NONE_PASS, NO_CATEGORY_IN_CITY, INVALID_QUERY, REASON_TITLES, Query, compare_dates, fmt_date, fmt_money, match
from matcher.explain import apply_fallback, evidence_for
from matcher.variants import VariantRegistry, query_dict

ROOT = Path(__file__).resolve().parent
E = html.escape


def load_env():
    path = ROOT / '.env'
    allowed = {'LLM_PROVIDER', 'LLM_MODEL', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'AGENT_DEADLINE', 'LLM_ENABLED'}
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.split('=', 1)
                if k.strip() in allowed and v.strip():
                    os.environ.setdefault(k.strip(), v.strip().strip('\"\''))


load_env()
st.set_page_config(page_title='PODBOR — ваш event, ваши условия', page_icon='◈', layout='wide')
st.markdown((ROOT / 'assets' / 'style.html').read_text(encoding='utf-8'), unsafe_allow_html=True)


@st.cache_resource
def read_catalog(version):
    return load_catalog()


version = catalog_version()
catalog = read_catalog(version)
prov = llm.provider()
has_ai = llm.has_key(prov) and os.getenv('LLM_ENABLED', '1') != '0'
if has_ai:
    llm.warm_up()
cities = sorted({c.city for c in catalog})
categories = sorted({cat for c in catalog for cat in c.categories})
formats = ['корпоратив', 'свадьба', 'той', 'конференция', 'юбилей', 'день рождения']
languages = ['Не важно', 'русский', 'казахский', 'английский']

DEFAULT = dict(city='Алматы', category='Ведущий', day=date(2026, 10, 10), fmt='корпоратив', budget=1_000_000, hours=5, language='русский', wish='')
PRESETS = {
    'Ведущий · 10 октября': DEFAULT,
    'Та же задача · 11 октября': {**DEFAULT, 'day': date(2026, 10, 11)},
    'Флорист · один вариант': {**DEFAULT, 'category': 'Флорист', 'budget': 250_000, 'hours': 8},
    'Декабрь · все заняты': {**DEFAULT, 'city': 'Астана', 'day': date(2026, 12, 24)},
    'Декоратор · нет в городе': {**DEFAULT, 'city': 'Астана', 'category': 'Декоратор'},
    'Зал · нужен другой бюджет': {**DEFAULT, 'category': 'Банкетный зал', 'day': date(2026, 10, 7)},
}
for key, value in DEFAULT.items():
    st.session_state.setdefault('q_' + key, value)


def preset_change():
    name = st.session_state.example
    if name in PRESETS:
        for k, v in PRESETS[name].items():
            st.session_state['q_' + k] = v
        st.session_state.run_requested = True


def apply_variant(q):
    values = dict(city=q.city, category=q.category, day=q.event_date, fmt=q.event_format,
                  budget=q.budget, hours=q.hours or 0, language=q.language or 'Не важно', wish=q.wish)
    for k, v in values.items():
        st.session_state['q_' + k] = v
    st.session_state.run_requested = True
    st.session_state.example = 'Свой запрос'


with st.sidebar:
    st.markdown('<div class="brand"><span class="brand-mark">◈</span> PODBOR<span class="brand-ai">AI</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="side-caption">EVENT-ПОДРЯДЧИКИ КАЗАХСТАНА</div>', unsafe_allow_html=True)
    st.selectbox('Быстрые примеры', ['Свой запрос', *PRESETS], key='example', on_change=preset_change)
    st.markdown('### Ваше мероприятие')
    with st.form('request'):
        st.selectbox('Город', cities, key='q_city')
        st.selectbox('Кого ищем', categories, key='q_category')
        st.date_input('Дата', key='q_day', min_value=CALENDAR_START, max_value=CALENDAR_END, format='DD.MM.YYYY')
        st.selectbox('Формат', formats, key='q_fmt')
        st.number_input('Бюджет на подрядчика, ₸', min_value=1, max_value=100_000_000, step=50_000, key='q_budget')
        c1, c2 = st.columns([1, 1.2])
        with c1:
            st.number_input('Часов', min_value=0, max_value=24, key='q_hours', help='0 — не ограничивать длительность')
        with c2:
            st.selectbox('Язык', languages, key='q_language')
        st.text_input('Что для вас важно?', placeholder='Например: спокойная подача', key='q_wish', max_chars=300,
                      help='Пожелание помогает сравнить описания; выполнение пожелания не гарантируется.')
        submit = st.form_submit_button('Найти подрядчиков →', type='primary', use_container_width=True)
    st.caption('Календарь: 23 сентября — 31 декабря 2026. Цена «от» требует уточнения.')
    with st.expander('Подключение AI'):
        st.write(f'Модель: {llm.model_name(prov)}')
        st.caption('Ключ настроен. Реальный статус появится после запроса.' if has_ai else 'Сейчас работает локальный режим. Добавьте свой ключ в .env по инструкции README.')
        st.caption('Ключ не нужно вводить в интерфейсе или отправлять в чат.')


def current_query():
    s = st.session_state
    return Query(s.q_city, s.q_day, s.q_fmt, s.q_category, int(s.q_budget), int(s.q_hours) or None,
                 None if s.q_language == 'Не важно' else s.q_language, s.q_wish.strip())


def pill(text, cls=''):
    return f'<span class="pill {cls}">{E(str(text))}</span>'


st.markdown('''<div class="hero"><div class="eyebrow">МЕНЬШЕ ПОИСКА. БОЛЬШЕ ЯСНОСТИ.</div>
<h1>Ваше событие.<br><span>Ваши три кандидата.</span></h1>
<p>Кто подходит, чем отличается и что изменить, если никто не подошёл.</p></div>
<div class="journey"><span><b>01</b> Проверяем условия</span><i>→</i><span><b>02</b> AI выбирает аргументы</span><i>→</i><span><b>03</b> Вы принимаете решение</span></div>''', unsafe_allow_html=True)


def draw_card(card, q):
    c = card.contractor
    headroom = q.budget - c.price_from
    accent = 'card-top' if card.rank == 1 else ''
    badges = pill(f'Свободен {q.event_date:%d.%m}', 'mint') + pill(q.event_format)
    if q.language:
        badges += pill(q.language)
    if q.hours:
        badges += pill(f'до {c.max_hours} ч' if c.max_hours is not None else 'Часы не применимы')
    notes = ''
    if c.synthetic:
        notes += pill('Синтетический профиль', 'amber')
    if c.price_imputed:
        notes += pill('Цена проставлена', 'amber')
    if c.city_imputed:
        notes += pill('Город проставлен', 'amber')
    source = 'Аргументы выбрал AI · ссылки проверены' if card.explanation_source == 'llm' else 'Объяснение из данных каталога'
    body = f'''<article class="candidate {accent}"><div class="candidate-top"><span class="rank">0{card.rank}</span><span class="small-label">СООТВЕТСТВУЕТ УСЛОВИЯМ</span></div>
    <h3>{E(c.name)}</h3><div class="location">{E(q.category)} · {E(c.city)}</div>
    <div class="price"><small>от</small> {E(fmt_money(c.price_from))}</div>
    <div class="headroom">{'Без запаса до бюджета' if not headroom else 'До бюджета остаётся ' + E(fmt_money(headroom))}</div>
    <div class="pills">{badges}</div><div class="reason-title">ПОЧЕМУ В ВЫБОРКЕ</div>
    <p class="explanation">{E(card.explanation)}</p><div class="data-notes">{notes}</div>
    <div class="source">{E(source)}</div></article>'''
    st.markdown(body, unsafe_allow_html=True)
    with st.expander(f'Источники и позиция №{card.rank}'):
        st.caption(f'ID: {c.id}. Баллы — соответствие запросу и полнота данных, не рейтинг качества.')
        for label, points in card.score_parts:
            st.write(f'+{points} · {label}')
        st.write('Описание автора профиля:')
        st.text(c.description)
        for note in card.data_notes:
            st.caption(note)


def draw_result(result, report, elapsed, pending=False):
    q = result.query
    conditions = [q.city, q.category, fmt_date(q.event_date), q.event_format, 'до ' + fmt_money(q.budget)]
    if q.hours:
        conditions.append(f'{q.hours} ч')
    if q.language:
        conditions.append(q.language)
    st.markdown('<div class="request-line"><span class="tiny-label">ВАШ ЗАПРОС</span><div>' + ''.join(pill(x) for x in conditions) + '</div></div>', unsafe_allow_html=True)
    if q.wish:
        st.caption('Пожелание: ' + q.wish)
    if result.status == FOUND:
        title = f'{result.passed_count} подходят. Сравните {len(result.cards)}.' if result.passed_count >= 3 else f'Подходит {result.passed_count} из {result.pool_size}.'
        subtitle = 'Дата, бюджет и обязательные условия проверены по каталогу.'
        color = 'success'
    elif result.status == NO_CATEGORY_IN_CITY:
        title, subtitle, color = 'Такой категории в городе пока нет.', result.headline, 'empty'
    elif result.status == INVALID_QUERY:
        title, subtitle, color = 'Уточните условия запроса.', result.headline, 'empty'
    else:
        title, subtitle, color = 'Сейчас нет совпадений. Есть следующий шаг.', result.headline, 'empty'
    st.markdown(f'<div class="result-title {color}"><h2>{E(title)}</h2><p>{E(subtitle)}</p></div>', unsafe_allow_html=True)
    if pending:
        st.caption('◌ AI изучает аргументы и проверяет варианты. Основной подбор уже готов.')
    if result.cards:
        cols = st.columns(len(result.cards))
        for col, card in zip(cols, result.cards):
            with col:
                draw_card(card, q)
        st.caption('Цена «от» — не окончательная смета. Утверждения в описаниях принадлежат авторам профилей.')
    if pending:
        return
    registry = VariantRegistry(catalog, q)
    options = []
    if report and report.recommendations:
        # Recheck even cached report before showing executable actions.
        for v in report.recommendations:
            fresh = registry.register(v.query)
            if fresh.passed_count:
                options.append(fresh)
    options_from_agent = bool(options)
    if not options and result.status in (NONE_PASS, FOUND) and result.passed_count < 3:
        options = registry.suggestions(limit=3)
    if options:
        st.markdown('<div class="section-heading"><span class="eyebrow">ЕСТЬ РЕШЕНИЕ</span><h3>Измените условия — увидите кандидатов</h3></div>', unsafe_allow_html=True)
        st.caption('AI выбрал варианты; каждый повторно проверен по всем условиям.' if options_from_agent else 'Варианты рассчитаны кодом. Все изменения внутри одной строки применяются вместе.')
        for idx, v in enumerate(options[:3]):
            with st.container(border=True):
                left, right = st.columns([4, 1])
                with left:
                    st.write(v.text)
                with right:
                    st.button('Применить →', key=f'variant_{idx}_{v.id}', on_click=apply_variant, args=(v.query,), use_container_width=True)
    elif result.status == NONE_PASS:
        st.info('Среди проверенных изменений решения нет. Можно вручную изменить формат или категорию. Подходящих исполнителей мы не добавляем искусственно.')
    if result.status == NO_CATEGORY_IN_CITY:
        elsewhere = sorted({c.city for c in catalog if q.category in c.categories})
        if elsewhere:
            st.info('Категория есть в: ' + ', '.join(elsewhere) + '. Это наличие профилей; остальные условия нужно проверить отдельно.')
    if result.rejected:
        with st.expander(f'Почему не остальные · {len(result.rejected)} из {result.pool_size}'):
            for rejected in result.rejected:
                reasons = ''.join(pill(REASON_TITLES[r], 'rose') for r in rejected.failed)
                st.markdown(f'<div class="rejected"><div><strong>{E(rejected.contractor.name)}</strong><span>от {E(fmt_money(rejected.contractor.price_from))}</span></div><div class="pills">{reasons}</div></div>', unsafe_allow_html=True)
            st.caption('Причины могут пересекаться: у одного профиля бывает несколько ограничений.')
    if result.not_shown:
        st.caption('Тоже соответствуют условиям: ' + ', '.join(result.not_shown) + '. Равные баллы разрешаются по ID.')
    if result.status in (FOUND, NONE_PASS):
        with st.expander('Что изменится на другую дату?'):
            other = st.date_input('Сравнить с датой', value=min(q.event_date + timedelta(days=1), CALENDAR_END),
                                  min_value=CALENDAR_START, max_value=CALENDAR_END, format='DD.MM.YYYY', key='compare_' + q.event_date.isoformat())
            lines = compare_dates(catalog, q, other)
            if lines:
                for line in lines:
                    st.write('• ' + line)
            else:
                st.caption('Набор подходящих при остальных исходных условиях не меняется.')
    mode = ('AI: аргументы и варианты по ссылкам' if report.mode == 'agent' else 'AI частично · часть ответа отклонена' if report.mode == 'partial' else 'Локальный режим · факты каталога')
    timer = 'повтор из кэша' if report.cached else f'{elapsed:.2f} с'
    st.markdown(f'<div class="footer-status"><span class="status-dot"></span>{E(mode)}<span class="footer-right">{E(timer)} · каталог {E(version)}</span></div>', unsafe_allow_html=True)
    with st.expander('Для жюри: как работает подбор и AI-агент'):
        st.write('**CSV → строгие ограничения → стабильное ранжирование → AI выбирает ссылки на аргументы и проверяет варианты → код проверяет ссылки → результат.**')
        st.caption('AI не меняет порядок карточек. Свободный текст модели не публикуется; это ограничение защиты от выдуманных рекомендаций. Описания профилей остаются заявлениями их авторов.')
        if report.reason:
            st.info(report.reason)
        st.write(f'Модель: {report.model or "не вызывалась"}. AI: {report.latency_ms} мс. Полный подбор: {elapsed:.2f} с.')
        for step in report.steps:
            st.write(f'**{step.tool}** · {step.result}')
            if step.args:
                st.json(step.args, expanded=False)
        if report.tested_variants:
            st.json(report.tested_variants, expanded=False)
        st.caption(f'{len(catalog)} профилей · {len(categories)} категорий · синтетических: {sum(c.synthetic for c in catalog)}. На показанном запросе подходят {result.passed_count}, показаны {len(result.cards)}.')
    export = {'query': query_dict(q), 'catalog_version': version, 'status': result.status,
              'passed_count': result.passed_count, 'cards': [{'id': c.contractor.id, 'name': c.contractor.name,
              'price_from_kzt': c.contractor.price_from, 'explanation': c.explanation} for c in result.cards],
              'alternatives': [v.public() for v in options], 'ai_mode': report.mode}
    st.download_button('Скачать результат · JSON', json.dumps(export, ensure_ascii=False, indent=2), 'podbor-result.json', 'application/json')


run_now = submit or st.session_state.pop('run_requested', False)
area = st.empty()
if 'last' not in st.session_state and not run_now:
    # Useful first screen without spending an API call on a page visit.
    q = current_query()
    start = time.perf_counter()
    result = match(catalog, q)
    report = run_agent(catalog, result, use_llm=False)
    report.reason = 'Стартовый пример рассчитан локально. Нажмите «Найти подрядчиков», чтобы запустить AI.'
    st.session_state.last = (result, report, time.perf_counter() - start)
if run_now:
    q = current_query()
    start = time.perf_counter()
    result = match(catalog, q)
    apply_fallback(result.cards, q)
    with area.container():
        draw_result(result, None, 0, pending=True)
    report = run_agent(catalog, result)
    st.session_state.last = (result, report, time.perf_counter() - start)
    area.empty()
with area.container():
    draw_result(*st.session_state.last)
