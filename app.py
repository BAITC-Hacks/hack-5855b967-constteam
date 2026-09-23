"""Интерфейс: сценарии в один клик, схема работы, карточки, вывод и ход работы агента.

Запуск: streamlit run app.py
"""
from __future__ import annotations

import html
import os
import time
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

from matcher.agent import run_agent
from matcher.data import CALENDAR_END, CALENDAR_START, DEFAULT_CSV, catalog_version, load_catalog
from matcher.engine import (
    FOUND, INVALID_QUERY, NO_CATEGORY_IN_CITY, NONE_PASS, REASON_TITLES,
    Query, compare_dates, fmt_date, fmt_money, hours_word, match,
)
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
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


_load_env_file()

FORMATS = ["свадьба", "той", "корпоратив", "конференция", "юбилей", "день рождения"]
LANGS = ["не важно", "русский", "казахский", "английский"]
E = html.escape

# Сценарии для демонстрации: только заполняют форму, алгоритм о них не знает
PRESETS = {
    "Ведущий на корпоратив": dict(city="Алматы", category="Ведущий", date=date(2026, 10, 10),
                                  fmt="корпоратив", budget=1_000_000, hours=5, lang="русский"),
    "То же, 11 октября": dict(city="Алматы", category="Ведущий", date=date(2026, 10, 11),
                              fmt="корпоратив", budget=1_000_000, hours=5, lang="русский"),
    "Редкая: флорист": dict(city="Алматы", category="Флорист", date=date(2026, 10, 10),
                            fmt="корпоратив", budget=250_000, hours=8, lang="русский"),
    "Декабрь: все заняты": dict(city="Астана", category="Ведущий", date=date(2026, 12, 24),
                                fmt="корпоратив", budget=1_000_000, hours=5, lang="русский"),
    "Нет категории в городе": dict(city="Астана", category="Декоратор", date=date(2026, 10, 10),
                                   fmt="корпоратив", budget=1_000_000, hours=5, lang="русский"),
}

st.set_page_config(page_title="Подбор подрядчиков · ИИ-агент", page_icon="🎯", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, .stButton button, input, textarea, select {
  font-family: 'Manrope', 'Segoe UI', Arial, sans-serif !important;
}
.block-container {padding-top: 1.6rem; max-width: 1240px;}
[data-testid="stSidebar"] {border-right: 1px solid #E4E1D6;}
[data-testid="stSidebar"] .stButton button {width: 100%; text-align: left; justify-content: flex-start;
  border: 1px solid #DAD6C8; background: #FFFFFF; font-weight: 600; padding: .45rem .75rem;}
[data-testid="stSidebar"] .stButton button:hover {border-color: #0F6E66; color: #0F6E66;}

.hero h1 {font-size: 2.05rem; font-weight: 800; letter-spacing: -.02em; margin: 0 0 .25rem 0; color:#141B26;}
.hero p {font-size: 1.1rem; color: #4A5261; margin: 0 0 .9rem 0;}
.pipe {display:flex; gap:.6rem; align-items:stretch; margin-bottom: 1.3rem; flex-wrap: wrap;}
.pipe .st {flex:1 1 220px; background:#FFFFFF; border:1px solid #E4E1D6; border-radius:12px; padding:.7rem .9rem;}
.pipe .n {display:inline-block; width:1.5rem; height:1.5rem; border-radius:50%; background:#0F6E66; color:#fff;
  text-align:center; font-weight:700; font-size:.85rem; line-height:1.5rem; margin-right:.4rem;}
.pipe .t {font-weight:700; color:#141B26;}
.pipe .d {font-size:.85rem; color:#5B6372; margin-top:.15rem; margin-left:1.95rem;}
.pipe .arrow {align-self:center; color:#A9A391; font-size:1.3rem;}

.status {border-radius:12px; padding:1rem 1.2rem; margin: .2rem 0 1rem 0; border-left: 6px solid;}
.status .h {font-size:1.35rem; font-weight:800; letter-spacing:-.01em;}
.status .s {font-size:1rem; margin-top:.15rem;}
.st-found {background:#E9F4EE; border-color:#1F8A4C; color:#123D25;}
.st-none {background:#FBEAEA; border-color:#C0392B; color:#5A1A13;}
.st-nocat {background:#FDF4E3; border-color:#D08A12; color:#5A3B05;}
.st-invalid {background:#EEF0F4; border-color:#6B7385; color:#2A3140;}

.advice {background:#FFFFFF; border:1px solid #CFE3DF; border-radius:12px; padding:.9rem 1.1rem; margin-bottom:1rem;}
.advice .h {font-weight:800; color:#0F6E66; margin-bottom:.25rem;}
.advice.pending {border-style:dashed; color:#5B6372;}

.card-h {display:flex; align-items:center; gap:.55rem; margin-bottom:.15rem;}
.rank {background:#141B26; color:#fff; border-radius:8px; font-weight:800; padding:.05rem .5rem; font-size:.95rem;}
.name {font-size:1.25rem; font-weight:800; color:#141B26; line-height:1.2;}
.meta {color:#6A7282; font-size:.85rem; margin-bottom:.45rem;}
.price {font-size:1.45rem; font-weight:800; color:#141B26; margin:.15rem 0 .1rem 0;}
.price small {font-size:.78rem; font-weight:500; color:#7A8292; margin-left:.35rem;}
.chips {margin:.5rem 0 .2rem 0;}
.chip {display:inline-block; border-radius:999px; padding:.12rem .55rem; font-size:.8rem; margin:0 .3rem .3rem 0; font-weight:600;}
.chip-ok {background:#E6F2EC; color:#17603A;}
.chip-na {background:#EEF0F4; color:#3F4757;}
.chip-warn {background:#FCEFD9; color:#7A4E07;}
.chip-real {background:#E3EEF9; color:#1D4E80;}
.chip-bad {background:#FBE3E1; color:#8A2318;}
.src {font-size:.78rem; color:#7A8292; margin-top:.35rem;}
.src.llm {color:#0F6E66; font-weight:600;}

.trace {display:flex; flex-wrap:wrap; gap:.4rem; align-items:center; margin:.3rem 0 .6rem 0;}
.step {background:#FFFFFF; border:1px solid #E4E1D6; border-radius:10px; padding:.35rem .6rem; font-size:.84rem;}
.step b {color:#141B26;}
.step .ms {color:#8A91A0; margin-left:.3rem;}
.step.err {border-color:#E3B4AE; background:#FDF1EF;}
.step.ok {border-color:#B8D8CC; background:#EEF7F3;}
.tarrow {color:#A9A391;}
.rej {font-size:.92rem; margin:.15rem 0;}
.foot {color:#7A8292; font-size:.8rem;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_catalog():
    return load_catalog(DEFAULT_CSV), catalog_version(DEFAULT_CSV)


@st.cache_resource
def warm_up_llm():
    # Загрузка SDK модели при открытии страницы, а не при первом запросе
    from matcher import llm
    return llm.warm_up()


catalog, version = get_catalog()
warm_up_llm()
cities = sorted({c.city for c in catalog})
categories = sorted({x for c in catalog for x in c.categories})


def agent_status() -> str:
    from matcher import llm
    p = llm.provider()
    if os.getenv("LLM_ENABLED", "1") == "0":
        return "⚪ Агент отключён — резервный режим"
    if not llm.has_key(p):
        return f"⚪ Нет ключа {llm.KEY_VARS[p]} — резервный режим"
    return f"🟢 ИИ-агент: {llm.model_name(p)}"


# ---------- форма и сценарии ----------
DEFAULTS = dict(city="Алматы", category="Ведущий", date=date(2026, 10, 10), fmt="корпоратив",
                budget=1_000_000, hours=5, lang="русский", wish="")
for k, v in DEFAULTS.items():
    st.session_state.setdefault(f"f_{k}", v)


def apply_preset(name: str) -> None:
    for k, v in PRESETS[name].items():
        st.session_state[f"f_{k}"] = v
    st.session_state["f_wish"] = ""
    st.session_state["autorun"] = True


with st.sidebar:
    st.markdown("### Примеры")
    for name in PRESETS:
        st.button(name, key=f"p_{name}", on_click=apply_preset, args=(name,))
    st.markdown("### Свой запрос")
    with st.form("query"):
        city = st.selectbox("Город", cities, key="f_city")
        category = st.selectbox("Категория", categories, key="f_category")
        event_date = st.date_input("Дата", min_value=date(2026, 1, 1), max_value=date(2027, 12, 31),
                                   format="DD.MM.YYYY", key="f_date",
                                   help=f"Занятость известна на {fmt_date(CALENDAR_START)}–{fmt_date(CALENDAR_END)}")
        event_format = st.selectbox("Мероприятие", FORMATS, key="f_fmt")
        budget = st.number_input("Бюджет, ₸", min_value=0, step=50_000, key="f_budget")
        hours = st.number_input("Часов (0 — не важно)", min_value=0, max_value=24, key="f_hours")
        language = st.selectbox("Язык", LANGS, key="f_lang")
        wish = st.text_input("Пожелание (необязательно)", placeholder="живой юмор, терраса…", key="f_wish")
        submitted = st.form_submit_button("Подобрать", type="primary", use_container_width=True)
    st.caption(agent_status())

# ---------- шапка ----------
st.markdown("""
<div class="hero">
  <h1>Подбор event-подрядчиков с ИИ-агентом</h1>
  <p>До трёх исполнителей из каталога вашего города — и чем каждый отличается.</p>
</div>
<div class="pipe">
  <div class="st"><span class="n">1</span><span class="t">Код отбирает</span><div class="d">дата, бюджет, формат, язык, часы</div></div>
  <div class="arrow">→</div>
  <div class="st"><span class="n">2</span><span class="t">ИИ-агент анализирует</span><div class="d">сравнивает, ищет варианты</div></div>
  <div class="arrow">→</div>
  <div class="st"><span class="n">3</span><span class="t">Код проверяет агента</span><div class="d">каждое число и факт</div></div>
</div>
""", unsafe_allow_html=True)


# ---------- отрисовка результата ----------

def match_chips(card, q) -> list[tuple[str, str]]:
    """Совпадения с запросом, проверенные кодом: есть в каждой карточке независимо от агента."""
    c = card.contractor
    left = q.budget - c.price_from
    chips = [("ok", f"свободен {q.event_date.strftime('%d.%m')}"),
             ("ok", "без запаса бюджета" if left == 0 else f"запас {fmt_money(left)}"),
             ("ok", q.event_format)]
    if q.language:
        chips.append(("ok", q.language))
    if q.hours:
        chips.append(("na", "часы не важны") if c.max_hours is None else ("ok", f"до {c.max_hours} ч"))
    return chips


def data_chips(card) -> list[tuple[str, str]]:
    """Только предупреждения: синтетический профиль, проставленные цена или город."""
    c = card.contractor
    out = [("warn", "синтетический профиль")] if c.synthetic else []
    if c.price_imputed:
        out.append(("warn", "цену уточнить"))
    if c.city_imputed:
        out.append(("warn", "город уточнить"))
    return out


def chips_html(chips) -> str:
    return "".join(f'<span class="chip chip-{k}">{E(t)}</span>' for k, t in chips)


def render_status(result) -> None:
    kind, title = {
        FOUND: ("found", "Подобрали"),
        NO_CATEGORY_IN_CITY: ("nocat", "В этом городе такой категории нет"),
        NONE_PASS: ("none", "Кандидаты есть, но ни один не проходит по условиям"),
        INVALID_QUERY: ("invalid", "Не можем проверить запрос"),
    }[result.status]
    st.markdown(f'<div class="status st-{kind}"><div class="h">{E(title)}</div>'
                f'<div class="s">{E(result.headline)}</div></div>', unsafe_allow_html=True)


def render_card(card, q) -> None:
    c = card.contractor
    with st.container(border=True):
        warn = data_chips(card)
        st.markdown(
            f'<div class="card-h"><span class="rank">{card.rank}</span><span class="name">{E(c.name)}</span></div>'
            f'<div class="price">от {E(fmt_money(c.price_from))}</div>'
            f'<div class="chips">{chips_html(match_chips(card, q))}{chips_html(warn)}</div>',
            unsafe_allow_html=True)
        st.markdown(card.explanation)
        src = "🤖 ИИ-агент, проверено кодом" if card.explanation_source == "llm" else "из фактов профиля"
        st.markdown(f'<div class="src{" llm" if card.explanation_source == "llm" else ""}">{src}</div>',
                    unsafe_allow_html=True)
        with st.expander(f"Почему №{card.rank} · {card.score} б."):
            for label, pts in card.score_parts:
                st.markdown(f"+{pts} · {label}")
            if card.differences:
                st.markdown("**Отличия:** " + "; ".join(card.differences) + ".")
            st.caption(f"{c.id} · описание автора профиля: {c.description}")


def render_trace(report) -> None:
    parts = []
    for stp in report.steps:
        if stp.tool == "основной поиск (код)":
            parts.append('<span class="step ok"><b>🔎 Поиск кодом</b></span>')
        elif stp.tool == "submit_answer":
            parts.append(f'<span class="step ok"><b>✅ Ответ сдан</b><span class="ms">{stp.ms} мс</span></span>')
        elif stp.tool in ("вызов модели", "лимит"):
            parts.append(f'<span class="step err"><b>⚠ {E(stp.result)}</b></span>')
        else:
            args = ", ".join(f"{k}={v}" for k, v in stp.args.items())
            ms = f'<span class="ms">{stp.ms} мс</span>' if stp.ms else ""
            parts.append(f'<span class="step"><b>🧰 {E(stp.tool)}</b>({E(args)}) → {E(stp.result)}{ms}</span>')
    st.markdown('<div class="trace">' + '<span class="tarrow">→</span>'.join(parts) + '</div>',
                unsafe_allow_html=True)


def plan_label(result) -> str:
    """Короткая подпись плана, который код задаёт агенту (см. matcher.agent.plan_for)."""
    if result.status == NO_CATEGORY_IN_CITY:
        return "категории в городе нет: агент смотрит другие города"
    if result.status == FOUND and result.passed_count >= 3:
        return "подходящих достаточно: агент сразу сравнивает"
    if result.status == FOUND:
        return "подходящих мало: агент проверяет другие условия"
    return "никто не подходит: агент ищет, что изменить"


def render(result, report, t_match: float, total: float, pending: bool) -> None:
    q = result.query
    render_status(result)

    # вывод агента
    if pending:
        st.markdown('<div class="advice pending"><div class="h">⏳ ИИ-агент анализирует…</div>'
                    'Карточки уже проверены кодом, тексты агента появятся через несколько секунд.</div>',
                    unsafe_allow_html=True)
    elif report and report.summary:
        title = "Как выбрать" if result.cards else "Что можно сделать"
        st.markdown(f'<div class="advice"><div class="h">🤖 {title}</div>{E(report.summary)}</div>',
                    unsafe_allow_html=True)

    # карточки рядом
    if result.cards:
        cols = st.columns(3)
        for col, card in zip(cols, result.cards):
            with col:
                render_card(card, q)
        st.caption("Цена «от» — итоговая смета может быть выше. Отметки совпадений проверены кодом.")

    # почему не остальные / почему никто
    if result.status in (FOUND, NONE_PASS) and result.rejected:
        title = "Почему не остальные" if result.status == FOUND else "Почему никто не подошёл"
        with st.expander(f"{title} — {len(result.rejected)} из {result.pool_size}",
                         expanded=result.status == NONE_PASS or result.passed_count < 3):
            for ch in result.rejected:
                chips = [("bad", REASON_TITLES[r]) for r in ch.failed]
                st.markdown(f'<div class="rej"><b>{E(ch.contractor.name)}</b> '
                            f'<span class="meta">от {E(fmt_money(ch.contractor.price_from))}</span> '
                            f'{chips_html(chips)}</div>', unsafe_allow_html=True)
            st.caption("Один подрядчик может не пройти сразу по нескольким условиям.")
    if result.not_shown:
        st.caption("Тоже проходят условия, но ниже по баллу: " + ", ".join(result.not_shown) + ".")

    if result.alternatives:
        with st.container(border=True):
            st.markdown("**Что можно изменить**")
            for a in result.alternatives:
                st.markdown(f"- {a.text}")

    if pending:
        return  # интерактивные элементы — только в окончательном виде

    # ход работы агента
    if report and report.steps:
        st.markdown(f"**Ход работы ИИ-агента** · {plan_label(result)}")
        render_trace(report)

    if result.status in (FOUND, NONE_PASS):
        with st.expander("Сравнить с другой датой"):
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

    if report.mode == "agent":
        cached = "повтор запроса" in (report.reason or "")
        mode_text = f"ИИ-агент {report.model} · " + ("ответ из кэша" if cached else f"{report.latency_ms / 1000:.1f} с")
    elif report.mode == "partial":
        mode_text = f"ИИ-агент частично: {report.reason}"
    else:
        mode_text = f"резервный режим: {report.reason}"
    st.markdown(f'<div class="foot">{E(mode_text)} · данные {E(version)}</div>', unsafe_allow_html=True)


# ---------- запуск подбора ----------
area = st.empty()
run_now = submitted or st.session_state.pop("autorun", False)

if run_now:
    s = st.session_state
    q = Query(city=s.f_city, event_date=s.f_date, event_format=s.f_fmt, category=s.f_category,
              budget=int(s.f_budget), hours=int(s.f_hours) or None,
              language=None if s.f_lang == "не важно" else s.f_lang, wish=(s.f_wish or "").strip())
    t0 = time.perf_counter()
    result = match(catalog, q)
    t_match = time.perf_counter() - t0
    apply_fallback(result.cards, q)
    with area.container():
        render(result, None, t_match, 0.0, pending=True)
    try:
        report = run_agent(catalog, result)
    except Exception as e:  # последняя страховка: демонстрация не должна падать
        from matcher.agent import AgentReport
        apply_fallback(result.cards, q)
        report = AgentReport("fallback", f"внутренняя ошибка агента ({type(e).__name__})")
    total = time.perf_counter() - t0
    st.session_state["last"] = (result, report, t_match, total)
    area.empty()

if "last" not in st.session_state:
    area.info("← Выберите пример слева или заполните свой запрос.")
    st.stop()

with area.container():
    render(*st.session_state["last"], pending=False)
