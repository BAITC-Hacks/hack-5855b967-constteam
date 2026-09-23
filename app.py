"""Интерфейс: форма запроса → статус → до трёх карточек с объяснениями.

Запуск: streamlit run app.py
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from matcher.data import CALENDAR_END, CALENDAR_START, DEFAULT_CSV, catalog_version, load_catalog
from matcher.engine import (
    FOUND, INVALID_QUERY, NO_CATEGORY_IN_CITY, NONE_PASS, REASON_TITLES,
    Query, compare_dates, fmt_date, fmt_money, match,
)
from matcher.agent import run_agent
from matcher.explain import apply_fallback


def _load_env_file() -> None:
    """Читает локальный .env (он в .gitignore). Уже заданные переменные не перезаписывает."""
    env = Path(__file__).resolve().parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env_file()

FORMATS = ["свадьба", "той", "корпоратив", "конференция", "юбилей", "день рождения"]
LANGS = ["не важно", "русский", "казахский", "английский"]

st.set_page_config(page_title="Подбор подрядчиков", page_icon="🎯", layout="centered")
st.markdown(
    """
    <style>
      .block-container {max-width: 860px; padding-top: 2rem;}
      .card-meta {color: #5b6470; font-size: 0.92rem; margin-bottom: .35rem;}
      .price {font-size: 1.05rem; font-weight: 600;}
      .tag {display:inline-block; padding:1px 8px; border-radius:10px; font-size:.78rem; margin-right:6px;}
      .tag-real {background:#e7f2ea; color:#1f5f33;}
      .tag-synth {background:#fdecd8; color:#8a4b0c;}
      .tag-src {background:#eef0f4; color:#3d4452;}
      .explain {font-size: 1.0rem; line-height: 1.5; margin: .4rem 0 .2rem 0;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_catalog():
    return load_catalog(DEFAULT_CSV), catalog_version(DEFAULT_CSV)


catalog, version = get_catalog()
cities = sorted({c.city for c in catalog})
categories = sorted({x for c in catalog for x in c.categories})

st.title("Подбор подрядчиков")
st.caption("Помогаем выбрать из каталога вашего города: до трёх подходящих подрядчиков и объяснение, "
           "почему каждый из них здесь. Это рекомендация, не бронирование.")

with st.form("query"):
    c1, c2 = st.columns(2)
    city = c1.selectbox("Город", cities, index=cities.index("Алматы") if "Алматы" in cities else 0)
    category = c2.selectbox("Категория подрядчика", categories,
                            index=categories.index("Ведущий") if "Ведущий" in categories else 0)
    c3, c4 = st.columns(2)
    event_date = c3.date_input("Дата мероприятия", value=date(2026, 10, 10),
                               min_value=date(2026, 1, 1), max_value=date(2027, 12, 31), format="DD.MM.YYYY")
    event_format = c4.selectbox("Тип мероприятия", FORMATS, index=FORMATS.index("корпоратив"))
    c5, c6, c7 = st.columns([1.3, 1, 1])
    budget = c5.number_input("Бюджет на этого подрядчика, ₸", min_value=0, value=1_000_000, step=50_000)
    hours = c6.number_input("Длительность, ч (0 — не важно)", min_value=0, max_value=24, value=5)
    language = c7.selectbox("Язык", LANGS, index=1)
    wish = st.text_input("Пожелание по стилю (необязательно)",
                         placeholder="например: живой юмор, минимализм, терраса")
    submitted = st.form_submit_button("Подобрать", type="primary", use_container_width=True)

st.caption(f"Календарь занятости известен на {fmt_date(CALENDAR_START)}–{fmt_date(CALENDAR_END)}.")


def render(result, report, t_match: float, total: float, pending: bool) -> None:
    """Рисует результат. pending=True — карточки уже готовы, агент ещё работает."""
    q = result.query

    # ---------- статус: три исхода различаются явно ----------
    if result.status == FOUND:
        st.success(f"**Подобрали.** {result.headline}", icon="✅")
    elif result.status == NO_CATEGORY_IN_CITY:
        st.warning(f"**В этом городе такой категории нет.** {result.headline}", icon="🗺️")
    elif result.status == NONE_PASS:
        st.error(f"**Кандидаты есть, но ни один не проходит по условиям.** {result.headline}", icon="⛔")
    elif result.status == INVALID_QUERY:
        st.warning(f"**Не можем проверить запрос.** {result.headline}", icon="📅")

    # ---------- вывод агента ----------
    if pending:
        st.info("Агент анализирует результат и пишет объяснения. Карточки ниже уже проверены кодом; "
                "тексты агента заменят объяснения из фактов, когда он закончит.", icon="⏳")
    elif report and report.summary:
        title = "Как выбрать (вывод агента)" if result.cards else "Вывод агента"
        st.info(f"**{title}.** {report.summary}", icon="🤖")

    # ---------- карточки ----------
    for card in result.cards:
        c = card.contractor
        with st.container(border=True):
            tag = ('<span class="tag tag-synth">синтетический профиль</span>' if c.synthetic
                   else '<span class="tag tag-real">реальный профиль</span>')
            src = ("объяснение агента, проверено" if card.explanation_source == "llm"
                   else "объяснение собрано из фактов профиля")
            st.markdown(f"#### {card.rank}. {c.name}")
            st.markdown(
                f'<div class="card-meta">{q.category} · {c.city} · {c.id}</div>'
                f'<div class="price">от {fmt_money(c.price_from)}</div>'
                f'<div class="card-meta">цена «от» — итоговая смета может быть выше</div>'
                f'{tag}<span class="tag tag-src">{src}</span>',
                unsafe_allow_html=True,
            )
            st.markdown(card.explanation)
            for note in card.data_notes:
                st.caption(f"⚠️ {note}")
            with st.expander(f"Почему на {card.rank}-м месте · {card.score} б."):
                for label, pts in card.score_parts:
                    st.markdown(f"- +{pts} — {label}")
                st.markdown("**Проверенные факты:** " + "; ".join(card.facts) + ".")
                st.markdown("**Описание автора профиля:**")
                st.caption(c.description)

    # ---------- почему меньше / почему никого ----------
    if result.status in (FOUND, NONE_PASS) and result.rejected:
        title = "Почему не остальные" if result.status == FOUND else "Почему никто не подошёл"
        expanded = result.status == NONE_PASS or result.passed_count < 3
        with st.expander(f"{title}: {len(result.rejected)} из {result.pool_size}", expanded=expanded):
            counts = "; ".join(f"{REASON_TITLES[r]} — {n}" for r, n in result.reason_counts.items())
            st.markdown(f"По условиям: {counts}.")
            st.caption("Один подрядчик может не пройти сразу по нескольким условиям, поэтому числа не складываются.")
            for line in result.details:
                st.markdown(f"- {line}")
    if result.not_shown:
        st.caption("Тоже проходят условия, но ниже по баллу: " + ", ".join(result.not_shown) + ".")

    if result.alternatives:
        st.markdown("**Что можно изменить** (посчитано кодом; условия запроса не меняются автоматически):")
        for a in result.alternatives:
            st.markdown(f"- {a.text}")

    if pending:
        return  # интерактивные элементы — только в окончательном виде

    # ---------- сравнение с другой датой ----------
    if result.status in (FOUND, NONE_PASS):
        with st.expander("Сравнить с другой датой — что меняет занятость"):
            other = st.date_input("Другая дата", value=min(q.event_date + timedelta(days=1), CALENDAR_END),
                                  min_value=CALENDAR_START, max_value=CALENDAR_END, format="DD.MM.YYYY",
                                  key="cmp_date")
            lines = compare_dates(catalog, q, other)
            if other == q.event_date:
                st.caption("Выберите другую дату.")
            elif lines:
                for line in lines:
                    st.markdown(f"- {line}")
            else:
                st.markdown("Состав подходящих не меняется: по занятости эти даты одинаковы.")

    # ---------- ход работы агента ----------
    if report and report.steps:
        with st.expander(f"Ход работы агента: шагов — {len(report.steps)}"):
            for i, stp in enumerate(report.steps, 1):
                args = ", ".join(f"{k}={v}" for k, v in stp.args.items())
                if stp.tool == "основной поиск (код)":
                    call = "**основной поиск (код)**"
                elif stp.tool in ("вызов модели", "лимит"):
                    call = f"**{stp.tool}**"
                else:
                    call = f"`{stp.tool}({args})`"
                ms = f" · {stp.ms} мс" if stp.ms else ""
                st.markdown(f"{i}. {call} → {stp.result}{ms}")
            st.caption("Состав и порядок карточек задаёт код. Агент исследует варианты и пишет тексты; "
                       "каждый его ответ проверяется.")

    # ---------- режим работы и время ----------
    st.divider()
    if report.mode == "agent":
        mode_text = f"агент: {report.model}, {report.latency_ms} мс, ответ прошёл проверку"
        if report.reason:
            mode_text += f" ({report.reason})"
    elif report.mode == "partial":
        mode_text = f"агент частично — {report.reason}"
    else:
        mode_text = f"резервный режим: {report.reason}"
    st.caption(f"{mode_text} · подбор {t_match*1000:.1f} мс · всего {total:.2f} с · версия данных {version}")


area = st.empty()

if submitted:
    q = Query(city=city, event_date=event_date, event_format=event_format, category=category,
              budget=int(budget), hours=int(hours) or None,
              language=None if language == "не важно" else language, wish=wish.strip())
    t0 = time.perf_counter()
    result = match(catalog, q)
    t_match = time.perf_counter() - t0
    apply_fallback(result.cards, q)
    # Сразу показываем проверенный результат, затем агент дописывает тексты
    with area.container():
        render(result, None, t_match, 0.0, pending=True)
    report = run_agent(catalog, result)
    total = time.perf_counter() - t0
    st.session_state["last"] = (result, report, t_match, total)
    area.empty()

if "last" not in st.session_state:
    area.info("Заполните параметры и нажмите «Подобрать».")
    st.stop()

with area.container():
    render(*st.session_state["last"], pending=False)
