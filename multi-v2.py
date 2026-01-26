"""
HH.RU Auto Response Bot - Ultimate TUI Edition v2
==================================================
Максимально информативный интерфейс с детальным отслеживанием
"""

import asyncio
import aiohttp
import ssl
from bs4 import BeautifulSoup
import re
import random
from datetime import datetime, timedelta
from glom import glom
import json
from pathlib import Path
import requests
from collections import deque
import urllib.parse
import time
import threading

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer, Grid
from textual.widgets import Header, Footer, Static, ProgressBar, Label, DataTable, Rule, Tabs, Tab, TabbedContent, \
    TabPane
from textual.reactive import reactive
from textual import work
from textual.worker import Worker, get_current_worker

from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich import box

# ============================================================
# ХРАНИЛИЩЕ ДАННЫХ
# ============================================================

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

APPLIED_FILE = DATA_DIR / "applied_vacancies.json"
TEST_REQUIRED_FILE = DATA_DIR / "test_required_vacancies.json"
DEBUG_LOG_FILE = DATA_DIR / "debug.log"


def log_debug(message: str):
    """Записать отладочное сообщение в файл"""
    with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] {message}\n")


def load_json(filepath: Path) -> dict:
    if filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_json(filepath: Path, data: dict):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def add_applied(account_name: str, vacancy_id: str, info: dict = None):
    data = load_json(APPLIED_FILE)
    if account_name not in data:
        data[account_name] = {}
    data[account_name][vacancy_id] = {
        "url": f"https://hh.ru/vacancy/{vacancy_id}",
        "title": (info or {}).get("title", ""),
        "company": (info or {}).get("company", ""),
        "salary_from": (info or {}).get("salary_from"),
        "salary_to": (info or {}).get("salary_to"),
        "at": datetime.now().isoformat()
    }
    save_json(APPLIED_FILE, data)


def add_test_vacancy(vacancy_id: str, title: str = "", company: str = ""):
    data = load_json(TEST_REQUIRED_FILE)
    if vacancy_id not in data:
        data[vacancy_id] = {
            "url": f"https://hh.ru/vacancy/{vacancy_id}",
            "title": title,
            "company": company,
            "at": datetime.now().isoformat()
        }
        save_json(TEST_REQUIRED_FILE, data)


def is_applied(account_name: str, vacancy_id: str) -> bool:
    return vacancy_id in load_json(APPLIED_FILE).get(account_name, {})


def is_test(vacancy_id: str) -> bool:
    return vacancy_id in load_json(TEST_REQUIRED_FILE)


def get_stats() -> dict:
    applied = load_json(APPLIED_FILE)
    tests = load_json(TEST_REQUIRED_FILE)

    total = sum(len(v) for v in applied.values())
    by_acc = {k: len(v) for k, v in applied.items()}

    return {"total": total, "tests": len(tests), "by_acc": by_acc}


def get_applied_list(limit: int = 50) -> list:
    """Получить список последних откликов"""
    applied = load_json(APPLIED_FILE)
    all_items = []

    for acc_name, vacancies in applied.items():
        for vid, info in vacancies.items():
            all_items.append({
                "account": acc_name,
                "vacancy_id": vid,
                "url": info.get("url", f"https://hh.ru/vacancy/{vid}"),
                "title": info.get("title", ""),
                "company": info.get("company", ""),
                "salary_from": info.get("salary_from"),
                "salary_to": info.get("salary_to"),
                "at": info.get("at", "")
            })

    # Сортируем по дате (новые первые)
    all_items.sort(key=lambda x: x.get("at", ""), reverse=True)
    return all_items[:limit]


def get_test_list(limit: int = 50) -> list:
    """Получить список вакансий с тестами"""
    tests = load_json(TEST_REQUIRED_FILE)
    items = []

    for vid, info in tests.items():
        items.append({
            "vacancy_id": vid,
            "url": info.get("url", f"https://hh.ru/vacancy/{vid}"),
            "title": info.get("title", ""),
            "company": info.get("company", ""),
            "at": info.get("at", "")
        })

    # Сортируем по дате (новые первые)
    items.sort(key=lambda x: x.get("at", ""), reverse=True)
    return items[:limit]
    tests = load_json(TEST_REQUIRED_FILE)
    return {
        "total": sum(len(v) for v in applied.values()),
        "tests": len(tests),
        "by_acc": {k: len(v) for k, v in applied.items()}
    }


# ============================================================
# АККАУНТЫ
# ============================================================

accounts_data = [
    {
        "name": "Demo Account A",
        "short": "ACCOUNT_A",
        "color": "cyan",
        "resume_hash": "<RESUME_HASH>",
        "letter": (
            "Здравствуйте!\n\n"
            "Я заинтересована в рассмотрении моей кандидатуры.\n\n"
            "С уважением,\n"
            "Имя Фамилия\n"
            "Контакты: <CONTACTS>"
        ),
        "urls": [
            "https://hh.ru/search/vacancy?resume=<RESUME_HASH>&order_by=publication_time&items_on_page=20",
            "https://hh.ru/search/vacancy?text=QA&area=1&items_on_page=20",
            "https://hh.ru/search/vacancy?text=Tester&area=1&items_on_page=20",
        ],
        "cookies": {
            "hhtoken": "<HHTOKEN>",
            "hhul": "<HHUL>",
            "crypted_id": "<CRYPTED_ID>",
            "_xsrf": "<XSRF_TOKEN>",
        },
    },
    {
        "name": "Demo Account B",
        "short": "ACCOUNT_B",
        "color": "magenta",
        "resume_hash": "<RESUME_HASH>",
        "letter": (
            "Здравствуйте!\n\n"
            "Прошу рассмотреть мой отклик на вакансию.\n\n"
            "С уважением,\n"
            "Имя Фамилия\n"
            "Контакты: <CONTACTS>"
        ),
        "urls": [
            "https://hh.ru/search/vacancy?resume=<RESUME_HASH>&order_by=publication_time&items_on_page=20",
            "https://hh.ru/search/vacancy?text=QA&area=1&items_on_page=20",
            "https://hh.ru/search/vacancy?text=Technical+Writer&area=1&items_on_page=20",
        ],
        "cookies": {
            "hhtoken": "<HHTOKEN>",
            "hhul": "<HHUL>",
            "crypted_id": "<CRYPTED_ID>",
            "_xsrf": "<XSRF_TOKEN>",
        },
    },
]



# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

class Config:
    """Глобальные настройки (можно менять в runtime)"""
    pages_per_url = 5  # Страниц с каждого поискового запроса
    max_concurrent = 5  # Максимум одновременных запросов
    response_delay = 3  # Задержка между откликами (секунды)
    pause_between_cycles = 120  # Пауза между циклами (секунды)
    limit_check_interval = 30  # Интервал проверки лимита (минуты)
    resume_touch_interval = 4  # Интервал поднятия резюме (часы)


CONFIG = Config()


# ============================================================
# API ФУНКЦИИ
# ============================================================

def get_headers(xsrf: str) -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Origin": "https://hh.ru",
        "X-XsrfToken": xsrf
    }


def parse_ids(html: str) -> set:
    soup = BeautifulSoup(html, "html.parser")
    ids = set()
    for link in soup.find_all("a", href=re.compile(r"/vacancy/\d+")):
        m = re.search(r"/vacancy/(\d+)", link["href"])
        if m:
            ids.add(m.group(1))

    # Логируем результат парсинга
    log_debug(f"🔍 Парсинг: найдено {len(ids)} вакансий")
    if len(ids) > 0:
        log_debug(f"   ID: {', '.join(list(ids)[:5])}{'...' if len(ids) > 5 else ''}")
    else:
        # Если ничего не найдено, логируем структуру страницы
        log_debug(f"   ⚠️ Вакансии не найдены!")
        log_debug(f"   Всего ссылок <a>: {len(soup.find_all('a'))}")
        log_debug(f"   Ссылок с /vacancy/: {len([a for a in soup.find_all('a') if a.get('href') and '/vacancy/' in str(a.get('href'))])}")
    log_debug("")

    return ids


def extract_search_query(url: str) -> str:
    """Извлекает поисковый запрос из URL"""
    if "text=" in url:
        match = re.search(r"text=([^&]+)", url)
        if match:
            return urllib.parse.unquote_plus(match.group(1))
    if "resume=" in url:
        return "По резюме"
    return "Поиск"


async def fetch_page(session, url, sem):
    async with sem:
        try:
            await asyncio.sleep(0.2)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                html = await r.text()

                # Логируем результат
                log_debug(f"✅ URL: {url}")
                log_debug(f"   Статус: {r.status}")
                log_debug(f"   Размер: {len(html)} байт")
                log_debug(f"   Начало HTML: {html[:500]}")
                log_debug("")

                return html
        except Exception as e:
            # Логируем ошибку
            log_debug(f"❌ ОШИБКА при загрузке: {url}")
            log_debug(f"   Тип ошибки: {type(e).__name__}")
            log_debug(f"   Сообщение: {str(e)}")
            log_debug("")
            return ""


def send_response(acc: dict, vid: str) -> tuple:
    """Возвращает (результат, инфо)"""
    log_debug(f"📤 ОТПРАВКА ОТКЛИКА на вакансию {vid}")
    log_debug(f"   Аккаунт: {acc['name']}")

    headers = get_headers(acc["cookies"]["_xsrf"])
    files = {
        "resume_hash": (None, acc["resume_hash"]),
        "vacancy_id": (None, vid),
        "letterRequired": (None, "true"),
        "letter": (None, acc["letter"]),
        "lux": (None, "true"),
        "ignore_postponed": (None, "true"),
    }

    try:
        r = requests.post(
            "https://hh.ru/applicant/vacancy_response/popup",
            headers=headers, cookies=acc["cookies"], files=files, timeout=15
        )
        txt = r.text

        log_debug(f"   Ответ HTTP: {r.status_code}")
        log_debug(f"   Размер ответа: {len(txt)} байт")
        log_debug(f"   Начало ответа: {txt[:300]}")

        # СНАЧАЛА проверяем успешные отклики (статус 200)
        if r.status_code == 200:
            # Вариант 1: есть shortVacancy (стандартный успех)
            if "shortVacancy" in txt:
                try:
                    p = r.json()
                    info = {
                        "title": glom(p, "responseStatus.shortVacancy.name", default="?"),
                        "company": glom(p, "responseStatus.shortVacancy.company.name", default="?"),
                        "salary_from": glom(p, "responseStatus.shortVacancy.compensation.from", default=None),
                        "salary_to": glom(p, "responseStatus.shortVacancy.compensation.to", default=None),
                    }
                    log_debug(f"   ✅ РЕЗУЛЬТАТ: УСПЕШНО (с данными)")
                    log_debug(f"   Вакансия: {info.get('title', '?')}")
                    log_debug(f"   Компания: {info.get('company', '?')}")
                    log_debug("")
                    return "sent", info
                except Exception as e:
                    log_debug(f"   ✅ РЕЗУЛЬТАТ: УСПЕШНО (ошибка парсинга: {e})")
                    log_debug("")
                    return "sent", {}

            # Вариант 2: успешный ответ без shortVacancy (некоторые вакансии)
            if '"success":true' in txt or '"status":"ok"' in txt or '"responded":true' in txt:
                log_debug(f"   ✅ РЕЗУЛЬТАТ: УСПЕШНО (по маркеру)")
                log_debug("")
                return "sent", {}

            # Вариант 3: если статус 200 и нет явных ошибок, считаем это успехом
            # (некоторые вакансии возвращают успех без явных маркеров)
            log_debug(f"   ✅ РЕЗУЛЬТАТ: УСПЕШНО (предполагаемый)")
            log_debug("")
            return "sent", {}

        # Теперь проверяем ошибки (только если статус НЕ 200)
        if "negotiations-limit-exceeded" in txt:
            log_debug(f"   ❌ РЕЗУЛЬТАТ: ЛИМИТ ИСЧЕРПАН")
            log_debug("")
            return "limit", {}

        if "test-required" in txt:
            # Пытаемся извлечь информацию о вакансии
            info = {}
            if "shortVacancy" in txt:
                try:
                    p = r.json()
                    info = {
                        "title": glom(p, "responseStatus.shortVacancy.name", default=""),
                        "company": glom(p, "responseStatus.shortVacancy.company.name", default=""),
                    }
                except:
                    pass
            log_debug(f"   🧪 РЕЗУЛЬТАТ: ТЕСТ ТРЕБУЕТСЯ")
            log_debug(f"   Вакансия: {info.get('title', 'неизвестно')}")
            log_debug("")
            return "test", info

        if "alreadyApplied" in txt:
            log_debug(f"   🔄 РЕЗУЛЬТАТ: УЖЕ ОТКЛИКНУЛИСЬ")
            log_debug("")
            return "already", {}

        log_debug(f"   ❌ РЕЗУЛЬТАТ: ОШИБКА (статус {r.status_code})")
        log_debug(f"   Ответ: {txt[:200]}")
        log_debug("")
        return "error", {"raw": txt[:200]}  # Возвращаем часть ответа для отладки
    except Exception as e:
        log_debug(f"   ❌ РЕЗУЛЬТАТ: ИСКЛЮЧЕНИЕ")
        log_debug(f"   Тип: {type(e).__name__}")
        log_debug(f"   Сообщение: {str(e)}")
        log_debug("")
        return "error", {"exception": str(e)}


def check_limit(acc: dict) -> bool:
    """True если лимит активен"""
    headers = get_headers(acc["cookies"]["_xsrf"])
    try:
        r = requests.post(
            "https://hh.ru/applicant/vacancy_response/popup",
            headers=headers, cookies=acc["cookies"],
            files={"resume_hash": (None, acc["resume_hash"]), "vacancy_id": (None, "1")},
            timeout=10
        )
        return "negotiations-limit-exceeded" in r.text
    except:
        return True


def touch_resume(acc: dict) -> tuple:
    """
    Поднять резюме в поиске.
    Возвращает (success: bool, message: str)
    """
    headers = get_headers(acc["cookies"]["_xsrf"])
    resume_hash = acc["resume_hash"]

    url_touch = "https://hh.ru/applicant/resumes/touch"

    touch_files = {
        "resume": (None, resume_hash),
        "undirectable": (None, "true")
    }

    try:
        response = requests.post(
            url_touch,
            headers=headers,
            cookies=acc["cookies"],
            files=touch_files,
            timeout=10
        )

        if response.status_code == 200:
            return True, "Резюме поднято!"
        elif response.status_code == 429:
            return False, "Слишком часто (429)"
        else:
            return False, f"HTTP {response.status_code}"

    except Exception as e:
        return False, f"Ошибка: {str(e)[:30]}"


# ============================================================
# СОСТОЯНИЕ АККАУНТА
# ============================================================

class AccountState:
    """Полное состояние аккаунта для отображения"""

    def __init__(self, acc_data: dict):
        self.acc = acc_data
        self.name = acc_data["name"]
        self.short = acc_data["short"]
        self.color = acc_data["color"]

        # Основной статус
        self.status = "idle"  # idle, collecting, applying, limit, waiting, checking
        self.status_detail = ""

        # Статистика сессии
        self.sent = 0
        self.skipped = 0
        self.tests = 0
        self.errors = 0
        self.already_applied = 0
        self.found_vacancies = 0  # Всего найдено вакансий за сессию

        # Текущая операция
        self.current_phase = ""  # "Сбор вакансий", "Отправка откликов", "Ожидание"
        self.current_url = ""
        self.current_url_idx = 0
        self.total_urls = len(acc_data["urls"])
        self.current_page = 0
        self.total_pages = CONFIG.pages_per_url

        # Текущая вакансия
        self.current_vacancy_id = ""
        self.current_vacancy_title = ""
        self.current_vacancy_company = ""
        self.current_vacancy_idx = 0
        self.total_vacancies = 0

        # Собранные вакансии по URL
        self.vacancies_by_url = {}  # url -> count
        self.vacancies_queue = []

        # Лимит
        self.limit_exceeded = False
        self.limit_reset_time = None

        # Автоподнятие резюме
        self.resume_touch_enabled = True
        self.last_resume_touch = None
        self.next_resume_touch = None
        self.resume_touch_status = ""

        # Таймеры
        self.last_action_time = None
        self.cycle_start_time = None
        self.wait_until = None

        # История последних действий
        self.action_history = deque(maxlen=5)

        # Последние успешные отклики
        self.recent_responses = deque(maxlen=10)


# ============================================================
# ВИДЖЕТЫ
# ============================================================

class DetailedAccountPanel(Static):
    """Детальная панель аккаунта"""

    def __init__(self, state: AccountState, **kwargs):
        super().__init__(**kwargs)
        self.state = state
        self.border_title = f" {state.short} "

    def compose(self) -> ComposeResult:
        yield Static(id="account-detail-content")

    def render_content(self) -> Text:
        s = self.state
        lines = []

        # === СТАТУС ===
        status_map = {
            "idle": ("⏸️", "ОЖИДАНИЕ", "dim"),
            "collecting": ("📥", "СБОР ВАКАНСИЙ", "cyan"),
            "applying": ("📤", "ОТПРАВКА ОТКЛИКОВ", "green"),
            "limit": ("🚫", "ЛИМИТ ИСЧЕРПАН", "red"),
            "waiting": ("⏳", "ПАУЗА", "yellow"),
            "checking": ("🔍", "ПРОВЕРКА ЛИМИТА", "cyan"),
        }
        icon, status_text, style = status_map.get(s.status, ("❓", "НЕИЗВЕСТНО", "white"))

        lines.append(f"[bold {style}]{icon} {status_text}[/bold {style}]")
        if s.status_detail:
            lines.append(f"[dim]{s.status_detail}[/dim]")
        lines.append("")

        # === ТЕКУЩАЯ ОПЕРАЦИЯ ===
        if s.status == "collecting":
            lines.append("[bold]📋 Сбор вакансий:[/bold]")
            # Текущий URL
            query = extract_search_query(s.current_url) if s.current_url else "—"
            lines.append(f"  Запрос: [cyan]{query}[/cyan]")
            lines.append(f"  URL: [dim]{s.current_url_idx + 1}/{s.total_urls}[/dim]")
            lines.append(f"  Страница: [dim]{s.current_page}/{s.total_pages}[/dim]")

            # Прогресс-бар сбора
            if s.total_urls > 0:
                pct = int((s.current_url_idx * s.total_pages + s.current_page) / (s.total_urls * s.total_pages) * 100)
                bar = self._progress_bar(pct, 20)
                lines.append(f"  {bar} {pct}%")

            # Собрано по запросам
            if s.vacancies_by_url:
                lines.append("")
                lines.append("[bold]📊 Найдено по запросам:[/bold]")
                for url, count in list(s.vacancies_by_url.items())[-3:]:
                    query = extract_search_query(url)
                    lines.append(f"  [dim]•[/dim] {query}: [green]{count}[/green]")

        elif s.status == "applying":
            lines.append("[bold]📤 Отправка откликов:[/bold]")

            # Прогресс
            if s.total_vacancies > 0:
                pct = int(s.current_vacancy_idx / s.total_vacancies * 100)
                bar = self._progress_bar(pct, 20)
                lines.append(f"  {bar} {pct}%")
                lines.append(f"  [dim]{s.current_vacancy_idx}/{s.total_vacancies} вакансий[/dim]")

            # Текущая вакансия
            lines.append("")
            lines.append("[bold]🎯 Текущая вакансия:[/bold]")
            if s.current_vacancy_id:
                lines.append(f"  ID: [cyan]{s.current_vacancy_id}[/cyan]")
                lines.append(f"  [dim]hh.ru/vacancy/{s.current_vacancy_id}[/dim]")
                if s.current_vacancy_title:
                    title = s.current_vacancy_title[:40] + "..." if len(
                        s.current_vacancy_title) > 40 else s.current_vacancy_title
                    lines.append(f"  [bold white]{title}[/bold white]")
                if s.current_vacancy_company:
                    company = s.current_vacancy_company[:35] + "..." if len(
                        s.current_vacancy_company) > 35 else s.current_vacancy_company
                    lines.append(f"  [dim]@ {company}[/dim]")
            else:
                lines.append("  [dim]Ожидание ответа...[/dim]")

        elif s.status == "limit":
            lines.append("[bold red]🚫 Лимит откликов исчерпан[/bold red]")
            if s.limit_reset_time:
                remaining = s.limit_reset_time - datetime.now()
                if remaining.total_seconds() > 0:
                    mins = int(remaining.total_seconds() // 60)
                    secs = int(remaining.total_seconds() % 60)
                    lines.append(f"  Следующая попытка через: [yellow]{mins}м {secs}с[/yellow]")
                    lines.append(f"  Время проверки: [dim]{s.limit_reset_time.strftime('%H:%M:%S')}[/dim]")
                else:
                    lines.append("  [cyan]Проверка лимита...[/cyan]")

        elif s.status == "waiting":
            if s.wait_until:
                remaining = (s.wait_until - datetime.now()).total_seconds()
                if remaining > 0:
                    lines.append(f"  Осталось: [yellow]{int(remaining)}с[/yellow]")

        # === АВТОПОДНЯТИЕ РЕЗЮМЕ (компактно) ===
        lines.append("")
        resume_status = ""
        if s.last_resume_touch:
            time_ago = (datetime.now() - s.last_resume_touch).total_seconds()
            if time_ago < 3600:
                ago_str = f"{int(time_ago // 60)}м"
            else:
                ago_str = f"{int(time_ago // 3600)}ч{int((time_ago % 3600) // 60)}м"

            if "✅" in s.resume_touch_status or "Поднято" in s.resume_touch_status:
                resume_status = f"[green]✅[/green] {ago_str} назад"
            else:
                resume_status = f"[yellow]⚠[/yellow] {ago_str} назад"
        else:
            resume_status = "[dim]—[/dim]"

        next_touch = ""
        if s.next_resume_touch:
            remaining = (s.next_resume_touch - datetime.now()).total_seconds()
            if remaining > 0:
                hours = int(remaining // 3600)
                mins = int((remaining % 3600) // 60)
                next_touch = f"[cyan]{s.next_resume_touch.strftime('%H:%M')}[/cyan] ({hours}ч{mins}м)"
            else:
                next_touch = "[green]сейчас![/green]"
        else:
            next_touch = "[dim]скоро[/dim]"

        lines.append(f"[bold]📤 Резюме:[/bold] {resume_status} → {next_touch}")

        # === СТАТИСТИКА СЕССИИ ===
        lines.append("")
        lines.append("[bold]📈 Статистика сессии:[/bold]")

        stats_line = f"  [green]✅ {s.sent}[/green]  [magenta]🧪 {s.tests}[/magenta]  [blue]🔄 {s.already_applied}[/blue]  [red]❌ {s.errors}[/red]"
        lines.append(stats_line)

        # === ПОСЛЕДНИЕ ДЕЙСТВИЯ ===
        if s.action_history:
            lines.append("")
            lines.append("[bold]📜 Последние действия:[/bold]")
            for action in list(s.action_history)[-3:]:
                lines.append(f"  [dim]{action}[/dim]")

        return Text.from_markup("\n".join(lines))

    def _progress_bar(self, percent: int, width: int = 20) -> str:
        filled = int(percent / 100 * width)
        empty = width - filled
        return f"[green]{'█' * filled}[/green][dim]{'░' * empty}[/dim]"

    def refresh_content(self):
        try:
            self.query_one("#account-detail-content", Static).update(self.render_content())
        except:
            pass


class GlobalStatsPanel(Static):
    """Глобальная статистика"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session_start = datetime.now()
        self.account_states = []  # Будет установлено из App
        self.border_title = " 📊 Общая статистика "

    def compose(self) -> ComposeResult:
        yield Static(id="global-stats-content")

    def render_content(self) -> Text:
        elapsed = datetime.now() - self.session_start
        mins = int(elapsed.total_seconds() / 60)
        secs = int(elapsed.total_seconds() % 60)

        # Считаем из состояний аккаунтов
        total_sent = sum(s.sent for s in self.account_states)
        total_skipped = sum(s.skipped for s in self.account_states)
        total_tests = sum(s.tests for s in self.account_states)
        total_errors = sum(s.errors for s in self.account_states)
        total_already = sum(s.already_applied for s in self.account_states)
        total_found = sum(s.found_vacancies for s in self.account_states)

        # Скорость
        elapsed_mins = max(1, elapsed.total_seconds() / 60)
        rate = total_sent / elapsed_mins

        # Загрузка из хранилища
        storage_stats = get_stats()

        lines = [
            "[bold cyan]⏱️ Время работы:[/bold cyan]",
            f"  {mins:02d}:{secs:02d}",
            "",
            "[bold green]📊 За сессию:[/bold green]",
            f"  🔍 Найдено вакансий: [cyan]{total_found}[/cyan]",
            f"  ✅ Новых откликов: [green]{total_sent}[/green]",
            f"  🧪 Требуют тест: [magenta]{total_tests}[/magenta]",
            f"  🔄 Уже откликались: [blue]{total_already}[/blue]",
            f"  ❌ Ошибок: [red]{total_errors}[/red]",
            "",
            "[bold blue]💾 Всего в базе:[/bold blue]",
            f"  ✉️ Откликов: [blue]{storage_stats['total']}[/blue]",
            f"  🧪 Тестовых: [magenta]{storage_stats['tests']}[/magenta]",
        ]

        # По аккаунтам (из сессии)
        if self.account_states:
            lines.append("")
            lines.append("[bold]👥 По аккаунтам:[/bold]")
            for s in self.account_states:
                lines.append(f"  [{s.color}]{s.short}[/{s.color}]: 🔍{s.found_vacancies} ✅{s.sent} 🧪{s.tests}")

        return Text.from_markup("\n".join(lines))

    def refresh_content(self):
        try:
            self.query_one("#global-stats-content", Static).update(self.render_content())
        except:
            pass


class RecentResponsesPanel(Static):
    """Последние попытки откликов"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.responses = deque(maxlen=20)
        self.border_title = " 📬 Последние попытки (новые вверху) "

    def compose(self) -> ComposeResult:
        yield Static("[dim]Ожидание...[/dim]", id="recent-content")

    def add_response(self, acc_short: str, acc_color: str, vacancy_id: str, title: str, company: str, result: str,
                     salary: str = ""):
        """result: sent, test, already, limit, error"""
        result_icons = {
            "sent": "✅",
            "test": "🧪",
            "already": "🔄",
            "limit": "🚫",
            "error": "❌",
        }
        self.responses.appendleft({
            "time": datetime.now().strftime("%H:%M:%S"),
            "acc": acc_short,
            "color": acc_color,
            "id": vacancy_id,
            "title": title,
            "company": company,
            "salary": salary,
            "result": result,
            "icon": result_icons.get(result, "❓"),
        })

    def render_content(self) -> Text:
        if not self.responses:
            return Text.from_markup("[dim]Ожидание...[/dim]")

        lines = []
        # responses уже в правильном порядке (новые первые) благодаря appendleft
        for r in list(self.responses)[:15]:  # Увеличим до 15 для большей истории
            title = r["title"][:30] + "..." if len(r["title"]) > 30 else r["title"]
            if not title or title == "?":
                title = f"ID: {r['id']}"
            company = r["company"][:18] + "..." if len(r["company"]) > 18 else r["company"]

            lines.append(f"[dim]{r['time']}[/dim] [{r['color']}]●[/{r['color']}] {r['icon']} {title}")
            if company and company != "?":
                lines.append(f"  [dim]@ {company}[/dim]")

        return Text.from_markup("\n".join(lines))

    def refresh_content(self):
        try:
            self.query_one("#recent-content", Static).update(self.render_content())
        except:
            pass


class ActivityLogPanel(Static):
    """Лог всей активности"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.messages = deque(maxlen=100)
        self.border_title = " 📜 Лог активности (новые вверху) "

    def compose(self) -> ComposeResult:
        yield Static("[dim]Запуск...[/dim]", id="log-content")

    def add(self, acc_short: str, acc_color: str, message: str, level: str = "info"):
        """level: info, success, warning, error"""
        ts = datetime.now().strftime("%H:%M:%S")

        level_styles = {
            "info": "white",
            "success": "green",
            "warning": "yellow",
            "error": "red",
        }
        style = level_styles.get(level, "white")

        if acc_short:
            self.messages.append(f"[dim]{ts}[/dim] [{acc_color}]{acc_short}[/{acc_color}] [{style}]{message}[/{style}]")
        else:
            self.messages.append(f"[dim]{ts}[/dim] [{style}]{message}[/{style}]")

    def refresh_content(self):
        try:
            # Показываем последние 30 сообщений В ОБРАТНОМ ПОРЯДКЕ (новые вверху)
            recent = list(self.messages)[-30:]
            recent.reverse()
            content = "\n".join(recent)
            self.query_one("#log-content", Static).update(Text.from_markup(content))
        except:
            pass


class AppliedVacanciesPanel(Static):
    """Панель со списком откликов"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.border_title = " ✅ Отклики "

    def compose(self) -> ComposeResult:
        yield Static(id="applied-list-content")

    def render_content(self) -> Text:
        items = get_applied_list(100)

        if not items:
            return Text.from_markup("[dim]Нет откликов[/dim]")

        lines = [f"[bold green]✅ Всего откликов: {len(items)}[/bold green]", ""]

        for item in items[:40]:
            # Название
            title = item.get("title", "")
            if title:
                title = title[:50] + "..." if len(title) > 50 else title
            else:
                title = f"ID: {item['vacancy_id']}"

            # Компания
            company = item.get("company", "")
            if company:
                company = company[:30] + "..." if len(company) > 30 else company
                company = f" @ {company}"

            # Время
            try:
                dt = datetime.fromisoformat(item["at"])
                time_str = dt.strftime("%d.%m %H:%M")
            except:
                time_str = ""

            # Зарплата
            salary = ""
            if item.get("salary_from") or item.get("salary_to"):
                sf = item.get("salary_from", "")
                st = item.get("salary_to", "")
                if sf and st:
                    salary = f" [green]💰{sf}-{st}[/green]"
                elif sf:
                    salary = f" [green]💰от {sf}[/green]"
                elif st:
                    salary = f" [green]💰до {st}[/green]"

            # Аккаунт
            acc = item.get("account", "")
            acc_short = acc.split("(")[1].rstrip(")") if "(" in acc else acc[:10]

            # Одна компактная строка
            lines.append(f"[dim]{time_str}[/dim] [{acc_short}] [bold]{title}[/bold]{company}{salary}")
            lines.append(f"  [cyan dim]hh.ru/vacancy/{item['vacancy_id']}[/cyan dim]")

        if len(items) > 40:
            lines.append(f"[dim]... и ещё {len(items) - 40}[/dim]")

        return Text.from_markup("\n".join(lines))

    def refresh_content(self):
        try:
            self.query_one("#applied-list-content", Static).update(self.render_content())
        except:
            pass


class TestVacanciesPanel(Static):
    """Панель со списком вакансий с тестами"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.border_title = " 🧪 Вакансии с тестами "

    def compose(self) -> ComposeResult:
        yield Static(id="test-list-content")

    def render_content(self) -> Text:
        items = get_test_list(100)

        if not items:
            return Text.from_markup("[dim]Нет вакансий с тестами[/dim]")

        lines = [f"[bold magenta]🧪 Всего вакансий с тестами: {len(items)}[/bold magenta]", ""]

        for item in items[:40]:
            # Название
            title = item.get("title", "")
            if title:
                title = title[:55] + "..." if len(title) > 55 else title
            else:
                title = f"ID: {item['vacancy_id']}"

            # Компания
            company = item.get("company", "")
            if company:
                company = company[:30] + "..." if len(company) > 30 else company
                company = f" @ {company}"

            # Время
            try:
                dt = datetime.fromisoformat(item["at"])
                time_str = dt.strftime("%d.%m %H:%M")
            except:
                time_str = ""

            # Компактная строка
            lines.append(f"[dim]{time_str}[/dim] [bold]{title}[/bold]{company}")
            lines.append(f"  [cyan dim]hh.ru/vacancy/{item['vacancy_id']}[/cyan dim]")

        if len(items) > 40:
            lines.append(f"[dim]... и ещё {len(items) - 40}[/dim]")

        return Text.from_markup("\n".join(lines))

    def refresh_content(self):
        try:
            self.query_one("#test-list-content", Static).update(self.render_content())
        except:
            pass


class VacancyQueuePanel(Static):
    """Очередь вакансий на обработку"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.queues = {}  # acc_short -> list of vacancy_ids
        self.border_title = " 📋 Очереди вакансий (с прокруткой) "

    def compose(self) -> ComposeResult:
        yield Static("[dim]Очереди пусты[/dim]", id="queue-content")

    def update_queue(self, acc_short: str, acc_color: str, vacancies: list, current_idx: int = 0):
        self.queues[acc_short] = {
            "vacancies": vacancies,
            "current": current_idx,
            "color": acc_color,
        }
        # Обновление будет через таймер в app

    def render_content(self) -> Text:
        if not self.queues or all(len(d["vacancies"]) == 0 for d in self.queues.values()):
            return Text.from_markup("[dim]Очереди пусты[/dim]")

        lines = []
        for acc_short, data in self.queues.items():
            total = len(data["vacancies"])
            if total == 0:
                continue
            current = data["current"]
            remaining = total - current
            color = data["color"]

            lines.append(f"[{color}]{acc_short}[/{color}]: [green]{remaining}[/green] в очереди")

            # Показать следующие 15 вакансий (увеличено для прокрутки)
            upcoming = data["vacancies"][current:current + 15]
            for i, vid in enumerate(upcoming):
                marker = "►" if i == 0 else "○"
                lines.append(f"  [{color}]{marker}[/{color}] {vid}")

            if remaining > 15:
                lines.append(f"  [dim]... ещё {remaining - 15}[/dim]")

            lines.append("")

        return Text.from_markup("\n".join(lines)) if lines else Text.from_markup("[dim]Очереди пусты[/dim]")

    def refresh_content(self):
        try:
            self.query_one("#queue-content", Static).update(self.render_content())
        except:
            pass


# ============================================================
# ГЛАВНОЕ ПРИЛОЖЕНИЕ
# ============================================================

class HHBotApp(App):
    """Главное TUI приложение v2"""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 4 2;
        grid-columns: 1fr 1fr 1fr 1fr;
        grid-rows: 1fr 1fr;
        padding: 0;
    }

    .account-panel {
        border: solid $primary;
        padding: 1;
        margin: 0;
        height: 100%;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }

    #account-0 {
        border: solid cyan;
        column-span: 2;
    }

    #account-1 {
        border: solid magenta;
        column-span: 2;
    }

    #global-stats {
        border: solid green;
        padding: 1;
        margin: 0;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }

    #vacancy-queue {
        border: solid blue;
        padding: 1;
        margin: 0;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }

    #recent-responses {
        border: solid yellow;
        padding: 1;
        margin: 0;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }

    #activity-log {
        border: solid $secondary;
        padding: 1;
        margin: 0;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }

    #applied-panel {
        border: solid green;
        padding: 1;
        margin: 0;
        column-span: 4;
        row-span: 2;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }

    #tests-panel {
        border: solid magenta;
        padding: 1;
        margin: 0;
        column-span: 4;
        row-span: 2;
        overflow-y: auto;
        scrollbar-size: 1 1;
    }

    #footer {
        dock: bottom;
        height: 2;
        background: $primary-darken-3;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Выход"),
        ("p", "pause", "Пауза"),
        ("1", "setting_1", "Страниц"),
        ("2", "setting_2", "Задержка"),
        ("3", "setting_3", "Пауза цикла"),
        ("4", "setting_4", "Проверка лимита"),
        ("a", "show_applied", "Отклики"),
        ("t", "show_tests", "Тесты"),
        ("m", "show_main", "Главная"),
    ]

    current_view = reactive("main")  # main, applied, tests

    def __init__(self):
        super().__init__()
        self.account_states = [AccountState(acc) for acc in accounts_data]
        self.account_panels = []
        self.running = True
        self.paused = False

    def compose(self) -> ComposeResult:
        # Верхний ряд - панели аккаунтов
        for i, state in enumerate(self.account_states):
            panel = DetailedAccountPanel(state, id=f"account-{i}", classes="account-panel")
            self.account_panels.append(panel)
            yield panel

        # Нижний ряд - вспомогательные панели
        self.global_stats = GlobalStatsPanel(id="global-stats")
        yield self.global_stats

        self.vacancy_queue = VacancyQueuePanel(id="vacancy-queue")
        yield self.vacancy_queue

        self.recent_responses = RecentResponsesPanel(id="recent-responses")
        yield self.recent_responses

        self.activity_log = ActivityLogPanel(id="activity-log")
        yield self.activity_log

        # Панели для отдельных видов (изначально скрыты)
        self.applied_panel = AppliedVacanciesPanel(id="applied-panel")
        self.applied_panel.display = False
        yield self.applied_panel

        self.tests_panel = TestVacanciesPanel(id="tests-panel")
        self.tests_panel.display = False
        yield self.tests_panel

        # Footer с настройками
        yield Static(id="footer")

    def on_mount(self) -> None:
        # Передаём ссылку на account_states в global_stats
        self.global_stats.account_states = self.account_states

        # Логируем старт сессии
        log_debug("=" * 80)
        log_debug("🚀 НОВАЯ СЕССИЯ ЗАПУЩЕНА")
        log_debug("=" * 80)
        log_debug(f"Аккаунтов: {len(self.account_states)}")
        for state in self.account_states:
            log_debug(f"  - {state.name}: {len(state.acc['urls'])} URL")
        log_debug("")

        self.activity_log.add("", "", "🚀 Бот запущен", "success")

        # Запуск воркеров
        for i, state in enumerate(self.account_states):
            self.run_account_worker(i, state)

        # Таймер обновления UI (каждые 300мс для плавности)
        self.set_interval(0.3, self.refresh_ui)

    def refresh_ui(self):
        """Обновление всех панелей"""
        # Обновляем footer с настройками
        self._update_footer()

        if self.current_view == "main":
            for panel in self.account_panels:
                panel.refresh_content()
            self.global_stats.refresh_content()
            self.vacancy_queue.refresh_content()
            self.recent_responses.refresh_content()
            self.activity_log.refresh_content()
        elif self.current_view == "applied":
            self.applied_panel.refresh_content()
        elif self.current_view == "tests":
            self.tests_panel.refresh_content()

    def _update_footer(self):
        """Обновить footer с настройками"""
        try:
            pause_status = "[yellow]⏸ ПАУЗА[/yellow]" if self.paused else "[green]▶ РАБОТА[/green]"
            footer_text = (
                f"{pause_status} │ "
                f"[dim]1[/dim] Стр:[cyan]{CONFIG.pages_per_url}[/cyan] │ "
                f"[dim]2[/dim] Задерж:[cyan]{CONFIG.response_delay}с[/cyan] │ "
                f"[dim]3[/dim] Пауза:[cyan]{CONFIG.pause_between_cycles}с[/cyan] │ "
                f"[dim]4[/dim] Лимит:[cyan]{CONFIG.limit_check_interval}м[/cyan] │ "
                f"[dim]Q[/dim] Выход [dim]P[/dim] Пауза [dim]A[/dim] Отклики [dim]T[/dim] Тесты [dim]M[/dim] Главная"
            )
            self.query_one("#footer", Static).update(Text.from_markup(footer_text))
        except:
            pass

    @work(exclusive=False, thread=True)
    def run_account_worker(self, idx: int, state: AccountState) -> None:
        """Воркер для аккаунта"""
        worker = get_current_worker()
        acc = state.acc

        while not worker.is_cancelled and self.running:
            # Пауза
            while self.paused and not worker.is_cancelled:
                state.status = "idle"
                state.status_detail = "Пауза пользователем"
                time.sleep(1)

            if worker.is_cancelled:
                break

            now = datetime.now()

            # === АВТОПОДНЯТИЕ РЕЗЮМЕ ===
            if state.resume_touch_enabled:
                should_touch = False
                if state.next_resume_touch is None:
                    should_touch = True  # Первый запуск
                elif now >= state.next_resume_touch:
                    should_touch = True

                if should_touch:
                    self.activity_log.add(state.short, state.color, "📤 Поднимаю резюме...", "info")
                    success, message = touch_resume(acc)

                    if success:
                        state.resume_touch_status = "✅ Поднято!"
                        state.last_resume_touch = now
                        state.next_resume_touch = now + timedelta(hours=4)
                        self.activity_log.add(state.short, state.color,
                                              f"✅ Резюме поднято! Следующее в {state.next_resume_touch.strftime('%H:%M')}",
                                              "success")
                    else:
                        state.resume_touch_status = f"⏳ {message}"
                        state.next_resume_touch = now + timedelta(hours=4)
                        self.activity_log.add(state.short, state.color,
                                              f"📤 {message}. Повтор в {state.next_resume_touch.strftime('%H:%M')}",
                                              "warning")

            # === ПРОВЕРКА ЛИМИТА ===
            if state.limit_exceeded:
                if state.limit_reset_time and now >= state.limit_reset_time:
                    state.status = "checking"
                    state.status_detail = "Проверка сброса лимита..."
                    self.activity_log.add(state.short, state.color, "🔍 Проверяю сброс лимита...", "info")

                    if not check_limit(acc):
                        state.limit_exceeded = False
                        state.limit_reset_time = None
                        state.status_detail = ""
                        self.activity_log.add(state.short, state.color, "✅ Лимит сброшен! Продолжаю работу", "success")
                        # Не делаем continue - сразу переходим к сбору вакансий
                    else:
                        state.limit_reset_time = now + timedelta(minutes=CONFIG.limit_check_interval)
                        state.status = "limit"
                        state.status_detail = f"Проверка в {state.limit_reset_time.strftime('%H:%M')}"
                        self.activity_log.add(state.short, state.color,
                                              f"⏳ Лимит ещё активен, попробую в {state.limit_reset_time.strftime('%H:%M')}",
                                              "warning")
                        time.sleep(60)
                        continue
                else:
                    state.status = "limit"
                    time.sleep(30)  # Проверяем состояние каждые 30 секунд
                    continue

            # === СБОР ВАКАНСИЙ ===
            state.status = "collecting"
            state.status_detail = "Начинаю сбор..."
            state.cycle_start_time = now
            state.vacancies_by_url = {}

            log_debug("-" * 80)
            log_debug(f"📥 НАЧАЛО СБОРА: {state.name}")
            log_debug(f"   Время: {now.strftime('%H:%M:%S')}")
            log_debug("-" * 80)

            self.activity_log.add(state.short, state.color, "📥 Начинаю сбор вакансий", "info")

            all_vacancies = []

            for url_idx, url in enumerate(acc["urls"]):
                if worker.is_cancelled or not self.running or self.paused:
                    break

                state.current_url = url
                state.current_url_idx = url_idx
                query = extract_search_query(url)
                state.status_detail = f"Запрос: {query}"

                log_debug(f"📍 URL {url_idx + 1}/{len(acc['urls'])}: {query}")
                log_debug(f"   {url}")

                self.activity_log.add(state.short, state.color, f"Сканирую: {query}", "info")

                url_vacancies = asyncio.run(self._collect_from_url(state, url))
                state.vacancies_by_url[url] = len(url_vacancies)
                all_vacancies.extend(url_vacancies)

                self.activity_log.add(state.short, state.color, f"📊 {query}: найдено {len(url_vacancies)} вакансий", "info")
                state.action_history.append(f"{query}: найдено {len(url_vacancies)}")

            # Уникальные вакансии
            unique_vacancies = set(all_vacancies)
            total_collected = len(unique_vacancies)

            self.activity_log.add(state.short, state.color,
                                  f"📊 Всего собрано: {len(all_vacancies)} ({total_collected} уникальных)",
                                  "info")

            if not unique_vacancies:
                state.status = "waiting"
                state.status_detail = "Нет вакансий"
                state.wait_until = now + timedelta(minutes=2)
                self.activity_log.add(state.short, state.color, "⚠️ Не найдено ни одной вакансии, пауза 2 мин", "warning")
                time.sleep(120)
                continue

            # Фильтрация
            filtered = []
            already_count = 0
            test_count = 0

            for vid in unique_vacancies:
                if is_applied(acc["name"], vid):
                    already_count += 1
                    state.already_applied += 1
                elif is_test(vid):
                    test_count += 1
                    state.tests += 1
                else:
                    filtered.append(vid)

            self.activity_log.add(state.short, state.color,
                                  f"🔍 Фильтрация: ✅ уже {already_count}, 🧪 тест {test_count}, 🆕 новые {len(filtered)}",
                                  "info")

            if not filtered:
                state.status = "waiting"
                state.status_detail = "Нет новых вакансий"
                state.wait_until = now + timedelta(minutes=2)
                self.activity_log.add(state.short, state.color,
                                      f"⚠️ Все вакансии уже обработаны ({already_count} откликов, {test_count} тестов), пауза 2 мин",
                                      "warning")
                time.sleep(120)
                continue

            random.shuffle(filtered)
            state.vacancies_queue = filtered
            state.total_vacancies = len(filtered)
            state.found_vacancies += len(all_vacancies)  # Увеличиваем счётчик найденных

            self.activity_log.add(state.short, state.color,
                                  f"✅ Найдено {len(filtered)} новых вакансий для отклика!",
                                  "success")
            self.vacancy_queue.update_queue(state.short, state.color, filtered, 0)

            # === ОТПРАВКА ОТКЛИКОВ ===
            state.status = "applying"
            state.status_detail = f"0/{state.total_vacancies}"

            for i, vid in enumerate(filtered):
                if worker.is_cancelled or not self.running or self.paused or state.limit_exceeded:
                    break

                state.current_vacancy_idx = i + 1
                state.current_vacancy_id = vid
                state.current_vacancy_title = ""  # Сбросим, обновится после ответа
                state.current_vacancy_company = ""
                state.status_detail = f"{i + 1}/{state.total_vacancies}"

                self.vacancy_queue.update_queue(state.short, state.color, filtered, i)
                self.activity_log.add(state.short, state.color, f"📤 Отправляю отклик: {vid}", "info")

                # Отправка
                result, info = send_response(acc, vid)

                if result == "sent":
                    state.sent += 1
                    add_applied(acc["name"], vid, info)

                    title = info.get("title", "Неизвестно")
                    company = info.get("company", "?")
                    sal_from = info.get("salary_from")
                    sal_to = info.get("salary_to")
                    salary = ""
                    if sal_from or sal_to:
                        salary = f"{sal_from or '?'} - {sal_to or '?'}"

                    state.current_vacancy_title = title
                    state.current_vacancy_company = company
                    state.action_history.append(f"✅ {title[:30]}")

                    self.recent_responses.add_response(state.short, state.color, vid, title, company, "sent", salary)
                    self.activity_log.add(state.short, state.color, f"✅ {title[:40]} @ {company[:20]}", "success")

                elif result == "test":
                    state.tests += 1
                    title = info.get("title", "")
                    company = info.get("company", "")
                    add_test_vacancy(vid, title, company)
                    display_title = title[:40] if title else vid
                    state.action_history.append(f"🧪 {display_title[:25]}")
                    self.recent_responses.add_response(state.short, state.color, vid, title, company, "test")
                    self.activity_log.add(state.short, state.color, f"🧪 Тест: {display_title}", "warning")

                elif result == "already":
                    state.already_applied += 1
                    add_applied(acc["name"], vid)
                    state.action_history.append(f"🔄 {vid}")
                    self.recent_responses.add_response(state.short, state.color, vid, "", "", "already")
                    # Логируем каждый 10-й чтобы не спамить
                    if state.already_applied % 10 == 0:
                        self.activity_log.add(state.short, state.color,
                                              f"🔄 Уже откликались: {state.already_applied} шт", "info")

                elif result == "limit":
                    state.limit_exceeded = True
                    state.limit_reset_time = now + timedelta(minutes=CONFIG.limit_check_interval)
                    state.status = "limit"
                    state.status_detail = f"Проверка в {state.limit_reset_time.strftime('%H:%M')}"
                    self.activity_log.add(state.short, state.color,
                                          f"🚫 ЛИМИТ! Повторная попытка в {state.limit_reset_time.strftime('%H:%M')}",
                                          "error")
                    break

                elif result == "error":
                    state.errors += 1
                    state.action_history.append(f"❌ {vid}")
                    self.recent_responses.add_response(state.short, state.color, vid, "", "", "error")
                    # Показываем часть ответа для отладки
                    raw = info.get("raw", "")[:80] if info else ""
                    exc = info.get("exception", "") if info else ""
                    debug_info = raw or exc or "unknown"
                    self.activity_log.add(state.short, state.color, f"❌ {vid}: {debug_info}", "error")

                time.sleep(CONFIG.response_delay)

            # Очистка
            state.current_vacancy_id = ""
            state.current_vacancy_title = ""
            state.current_vacancy_company = ""
            self.vacancy_queue.update_queue(state.short, state.color, [], 0)

            if not state.limit_exceeded:
                state.status = "waiting"
                state.status_detail = "Цикл завершён"
                state.wait_until = datetime.now() + timedelta(seconds=CONFIG.pause_between_cycles)
                self.activity_log.add(state.short, state.color,
                                      f"⏳ Цикл завершён, пауза {CONFIG.pause_between_cycles}с", "info")
                time.sleep(CONFIG.pause_between_cycles)

    async def _collect_from_url(self, state: AccountState, url: str) -> list:
        """Сбор вакансий с одного URL"""
        acc = state.acc
        headers = get_headers(acc["cookies"]["_xsrf"])
        sem = asyncio.Semaphore(CONFIG.max_concurrent)

        log_debug(f"🔑 Cookies: hhtoken={acc['cookies']['hhtoken'][:10]}...")
        log_debug(f"   _xsrf={acc['cookies']['_xsrf'][:10]}...")

        vacancies = []

        # Создаём SSL context без проверки сертификата
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        connector = aiohttp.TCPConnector(ssl=ssl_context)

        async with aiohttp.ClientSession(headers=headers, cookies=acc["cookies"], connector=connector) as session:
            sep = "&" if "?" in url else "?"

            for page in range(CONFIG.pages_per_url):
                state.current_page = page + 1
                page_url = f"{url}{sep}page={page}"

                html = await fetch_page(session, page_url, sem)
                if html:
                    ids = parse_ids(html)
                    vacancies.extend(ids)
                    # Логируем только если ничего не найдено (для отладки)
                    if not ids and page == 0:
                        self.activity_log.add(state.short, state.color,
                                              f"⚠️ Страница {page + 1}: вакансии не найдены (HTML: {len(html)} байт)",
                                              "warning")
                else:
                    self.activity_log.add(state.short, state.color,
                                          f"❌ Страница {page + 1}: ошибка загрузки",
                                          "error")

        return vacancies

    def action_quit(self) -> None:
        self.running = False
        self.exit()

    def action_refresh(self) -> None:
        self.global_stats.refresh_content()
        self.activity_log.add("", "", "🔄 Статистика обновлена", "info")

    def action_pause(self) -> None:
        self.paused = not self.paused
        if self.paused:
            self.activity_log.add("", "", "⏸️ Пауза", "warning")
        else:
            self.activity_log.add("", "", "▶️ Продолжение", "success")

    def action_setting_1(self) -> None:
        """Изменить количество страниц на запрос"""
        values = [1, 3, 5, 10, 15, 20]
        current = CONFIG.pages_per_url
        try:
            idx = values.index(current)
            CONFIG.pages_per_url = values[(idx + 1) % len(values)]
        except:
            CONFIG.pages_per_url = 5
        self.activity_log.add("", "", f"⚙️ Страниц/запрос: {CONFIG.pages_per_url}", "info")

    def action_setting_2(self) -> None:
        """Изменить задержку между откликами"""
        values = [1, 2, 3, 5, 10]
        current = CONFIG.response_delay
        try:
            idx = values.index(current)
            CONFIG.response_delay = values[(idx + 1) % len(values)]
        except:
            CONFIG.response_delay = 3
        self.activity_log.add("", "", f"⚙️ Задержка отклика: {CONFIG.response_delay}с", "info")

    def action_setting_3(self) -> None:
        """Изменить паузу между циклами"""
        values = [30, 60, 120, 180, 300]
        current = CONFIG.pause_between_cycles
        try:
            idx = values.index(current)
            CONFIG.pause_between_cycles = values[(idx + 1) % len(values)]
        except:
            CONFIG.pause_between_cycles = 120
        self.activity_log.add("", "", f"⚙️ Пауза цикла: {CONFIG.pause_between_cycles}с", "info")

    def action_setting_4(self) -> None:
        """Изменить интервал проверки лимита"""
        values = [15, 30, 45, 60]
        current = CONFIG.limit_check_interval
        try:
            idx = values.index(current)
            CONFIG.limit_check_interval = values[(idx + 1) % len(values)]
        except:
            CONFIG.limit_check_interval = 30
        self.activity_log.add("", "", f"⚙️ Проверка лимита: {CONFIG.limit_check_interval}м", "info")

    def _switch_view(self, view: str):
        """Переключение вида"""
        self.current_view = view

        # Скрываем/показываем панели
        main_panels = [self.global_stats, self.vacancy_queue, self.recent_responses,
                       self.activity_log]
        for panel in self.account_panels:
            panel.display = (view == "main")
        for panel in main_panels:
            panel.display = (view == "main")

        self.applied_panel.display = (view == "applied")
        self.tests_panel.display = (view == "tests")

        # Обновляем активную панель
        if view == "applied":
            self.applied_panel.refresh_content()
        elif view == "tests":
            self.tests_panel.refresh_content()

    def action_show_main(self) -> None:
        """Показать главный экран"""
        self._switch_view("main")

    def action_show_applied(self) -> None:
        """Показать список откликов"""
        self._switch_view("applied")

    def action_show_tests(self) -> None:
        """Показать список тестов"""
        self._switch_view("tests")


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    app = HHBotApp()
    app.run()