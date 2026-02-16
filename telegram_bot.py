"""
Telegram бот для автоматизации откликов на hh.ru
Использует браузерную автоматизацию через Playwright для реального взаимодействия с сайтом
"""

import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

from playwright.async_api import async_playwright, Browser, Page, BrowserContext
import logging

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),  # Вывод в консоль
        logging.FileHandler('bot.log', encoding='utf-8')  # Вывод в файл
    ]
)
logger = logging.getLogger(__name__)
logger.info("Логирование инициализировано")

# Константы для состояний разговора
SETTING_TOKEN, SETTING_RESUME, SETTING_LETTER, SETTING_URL = range(4)

# Пути к файлам данных
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
CONFIG_FILE = DATA_DIR / "bot_config.json"
APPLIED_FILE = DATA_DIR / "applied_vacancies.json"
STATS_FILE = DATA_DIR / "stats.json"


class HHBot:
    """Основной класс бота для работы с hh.ru"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.config = self.load_config()
        self.stats = self.load_stats()
        self.is_running = False
        self.current_task = None
        
    def load_config(self) -> Dict:
        """Загрузить конфигурацию из файла"""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Ошибка загрузки конфига: {e}")
        return {
            "hhtoken": "",
            "hhul": "",
            "crypted_id": "",
            "_xsrf": "",
            "resume_hash": "",
            "letter": "",
            "search_urls": [],
            "pages_per_url": 5,
            "response_delay": 3,
            "resume_touch_interval_hours": 4
        }
    
    def save_config(self):
        """Сохранить конфигурацию в файл"""
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def load_stats(self) -> Dict:
        """Загрузить статистику"""
        if STATS_FILE.exists():
            try:
                with open(STATS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "total_responses": 0,
            "total_tests": 0,
            "total_errors": 0,
            "last_resume_touch": None,
            "last_response_time": None
        }
    
    def save_stats(self):
        """Сохранить статистику"""
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=2)
    
    def load_applied(self) -> set:
        """Загрузить список уже откликнутых вакансий"""
        if APPLIED_FILE.exists():
            try:
                with open(APPLIED_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get("vacancy_ids", []))
            except:
                pass
        return set()
    
    def add_applied(self, vacancy_id: str):
        """Добавить вакансию в список откликнутых"""
        data = {"vacancy_ids": list(self.load_applied())}
        data["vacancy_ids"].append(vacancy_id)
        with open(APPLIED_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    async def init_browser(self):
        """Инициализировать браузер"""
        if self.browser is None:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            )
            self.page = await self.context.new_page()
            logger.info("Браузер инициализирован")
    
    async def close_browser(self):
        """Закрыть браузер"""
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        self.browser = None
        self.context = None
        self.page = None
        logger.info("Браузер закрыт")
    
    async def set_cookies(self):
        """Установить cookies для авторизации"""
        required_tokens = {
            "hhtoken": self.config.get("hhtoken"),
            "hhul": self.config.get("hhul"),
            "crypted_id": self.config.get("crypted_id"),
            "_xsrf": self.config.get("_xsrf")
        }
        
        missing_tokens = [key for key, value in required_tokens.items() if not value]
        
        if missing_tokens:
            logger.error(f"Отсутствуют токены: {', '.join(missing_tokens)}")
            logger.info(f"Текущие токены: hhtoken={bool(required_tokens['hhtoken'])}, "
                       f"hhul={bool(required_tokens['hhul'])}, "
                       f"crypted_id={bool(required_tokens['crypted_id'])}, "
                       f"_xsrf={bool(required_tokens['_xsrf'])}")
            return False
        
        await self.page.goto("https://hh.ru")
        await self.context.add_cookies([
            {
                "name": "hhtoken",
                "value": self.config["hhtoken"],
                "domain": ".hh.ru",
                "path": "/"
            },
            {
                "name": "hhul",
                "value": self.config["hhul"],
                "domain": ".hh.ru",
                "path": "/"
            },
            {
                "name": "crypted_id",
                "value": self.config["crypted_id"],
                "domain": ".hh.ru",
                "path": "/"
            },
            {
                "name": "_xsrf",
                "value": self.config["_xsrf"],
                "domain": ".hh.ru",
                "path": "/"
            }
        ])
        await self.page.goto("https://hh.ru")
        await self.page.wait_for_timeout(2000)
        logger.info("Cookies установлены")
        return True
    
    async def touch_resume(self) -> tuple[bool, str]:
        """Поднять резюме в поиске через браузер"""
        try:
            resume_hash = self.config.get("resume_hash")
            if not resume_hash:
                return False, "Не указан resume_hash"
            
            await self.init_browser()
            await self.set_cookies()
            
            # Переходим на страницу резюме
            url = f"https://hh.ru/resume/{resume_hash}"
            await self.page.goto(url)
            await self.page.wait_for_timeout(2000)
            
            # Ищем кнопку "Поднять в поиске"
            try:
                # Пробуем найти кнопку по тексту
                button = await self.page.query_selector('button:has-text("Поднять в поиске")')
                if not button:
                    button = await self.page.query_selector('button:has-text("Поднять резюме")')
                if not button:
                    # Пробуем найти по классу или data-атрибуту
                    button = await self.page.query_selector('[data-qa="resume-update-button"]')
                
                if button:
                    await button.click()
                    await self.page.wait_for_timeout(2000)
                    
                    # Проверяем успешность
                    success_text = await self.page.query_selector('text="Резюме поднято"')
                    if success_text:
                        self.stats["last_resume_touch"] = datetime.now().isoformat()
                        self.save_stats()
                        return True, "Резюме успешно поднято!"
                    else:
                        return True, "Команда выполнена (статус не подтверждён)"
                else:
                    return False, "Кнопка 'Поднять в поиске' не найдена"
            except Exception as e:
                logger.error(f"Ошибка при клике на кнопку: {e}")
                return False, f"Ошибка: {str(e)[:100]}"
        except Exception as e:
            logger.error(f"Ошибка поднятия резюме: {e}")
            return False, f"Ошибка: {str(e)[:100]}"
    
    def normalize_search_url(self, url: str) -> str:
        """Нормализовать URL поиска вакансий"""
        url = url.strip()
        
        # Если это уже полный URL hh.ru
        if url.startswith('https://hh.ru') or url.startswith('http://hh.ru'):
            return url
        
        # Если это относительный URL
        if url.startswith('/'):
            return f"https://hh.ru{url}"
        
        # Если это поисковый запрос без URL (только текст)
        # Преобразуем в URL поиска
        if not url.startswith('http'):
            # Кодируем поисковый запрос
            from urllib.parse import quote_plus
            encoded_query = quote_plus(url)
            return f"https://hh.ru/search/vacancy?text={encoded_query}"
        
        return url
    
    async def get_vacancy_ids_from_page(self, url: str) -> List[str]:
        """Получить список ID вакансий со страницы поиска"""
        try:
            # Нормализуем URL
            normalized_url = self.normalize_search_url(url)
            logger.info(f"Загрузка страницы: {normalized_url}")
            
            # Проверяем, что это валидный URL
            if not normalized_url.startswith('http'):
                logger.error(f"Некорректный URL: {normalized_url}")
                return []
            
            try:
                await self.page.goto(normalized_url, wait_until='networkidle', timeout=30000)
            except Exception as nav_error:
                logger.warning(f"Ошибка навигации (пробую с load): {nav_error}")
                try:
                    await self.page.goto(normalized_url, wait_until='load', timeout=30000)
                except Exception as e:
                    logger.error(f"Не удалось загрузить страницу: {e}")
                    return []
            
            await self.page.wait_for_timeout(2000)
            
            # Ждём загрузки списка вакансий (с несколькими попытками)
            try:
                await self.page.wait_for_selector('a[href*="/vacancy/"]', timeout=15000)
            except:
                # Пробуем альтернативные селекторы
                try:
                    await self.page.wait_for_selector('[data-qa="vacancy-serp__vacancy"]', timeout=5000)
                except:
                    logger.warning("Не найдены вакансии на странице, возможно страница пуста или требует авторизации")
                    # Проверяем, может быть это страница авторизации
                    page_content = await self.page.content()
                    if 'авторизац' in page_content.lower() or 'login' in page_content.lower():
                        logger.error("Требуется авторизация - проверьте токены")
                    return []
            
            # Получаем все ссылки на вакансии
            links = await self.page.query_selector_all('a[href*="/vacancy/"]')
            vacancy_ids = set()
            
            for link in links:
                try:
                    href = await link.get_attribute('href')
                    if href:
                        # Обрабатываем относительные и абсолютные ссылки
                        if href.startswith('/'):
                            href = f"https://hh.ru{href}"
                        match = re.search(r'/vacancy/(\d+)', href)
                        if match:
                            vacancy_ids.add(match.group(1))
                except Exception as e:
                    logger.debug(f"Ошибка при обработке ссылки: {e}")
                    continue
            
            logger.info(f"Найдено {len(vacancy_ids)} уникальных вакансий на странице")
            return list(vacancy_ids)
        except Exception as e:
            logger.error(f"Ошибка получения вакансий с URL {url}: {e}", exc_info=True)
            return []
    
    async def send_response_to_vacancy(self, vacancy_id: str) -> tuple[str, str]:
        """
        Отправить отклик на вакансию через браузер
        Возвращает (результат, сообщение)
        """
        try:
            await self.init_browser()
            await self.set_cookies()
            
            # Переходим на страницу вакансии
            url = f"https://hh.ru/vacancy/{vacancy_id}"
            await self.page.goto(url)
            await self.page.wait_for_timeout(2000)
            
            # Ищем кнопку "Откликнуться"
            try:
                # Различные варианты селекторов для кнопки отклика
                button_selectors = [
                    'button[data-qa="vacancy-response-link-top"]',
                    'button:has-text("Откликнуться")',
                    'a[data-qa="vacancy-response-link-top"]',
                    '[data-qa="vacancy-response-link-top"]',
                    'button.resume-search-item__action-button',
                ]
                
                button = None
                for selector in button_selectors:
                    try:
                        button = await self.page.query_selector(selector)
                        if button:
                            break
                    except:
                        continue
                
                if not button:
                    # Пробуем найти любую кнопку с текстом "Откликнуться"
                    buttons = await self.page.query_selector_all('button, a')
                    for btn in buttons:
                        text = await btn.inner_text()
                        if text and "Откликнуться" in text:
                            button = btn
                            break
                
                if not button:
                    return "error", "Кнопка 'Откликнуться' не найдена"
                
                # Кликаем на кнопку
                await button.click()
                await self.page.wait_for_timeout(2000)
                
                # Ждём появления формы отклика
                try:
                    await self.page.wait_for_selector('textarea, [data-qa="vacancy-response-letter-input"]', timeout=5000)
                except:
                    pass
                
                # Заполняем сопроводительное письмо
                letter = self.config.get("letter", "")
                if letter:
                    textarea_selectors = [
                        'textarea[data-qa="vacancy-response-letter-input"]',
                        'textarea',
                        '[data-qa="vacancy-response-letter-input"]'
                    ]
                    
                    for selector in textarea_selectors:
                        try:
                            textarea = await self.page.query_selector(selector)
                            if textarea:
                                await textarea.fill(letter)
                                break
                        except:
                            continue
                
                # Выбираем резюме если нужно
                resume_hash = self.config.get("resume_hash")
                if resume_hash:
                    try:
                        resume_select = await self.page.query_selector(f'input[value="{resume_hash}"]')
                        if resume_select:
                            await resume_select.click()
                    except:
                        pass
                
                # Отправляем отклик
                submit_selectors = [
                    'button[data-qa="vacancy-response-submit-button"]',
                    'button:has-text("Отправить отклик")',
                    'button:has-text("Откликнуться")',
                    'button[type="submit"]'
                ]
                
                submit_button = None
                for selector in submit_selectors:
                    try:
                        submit_button = await self.page.query_selector(selector)
                        if submit_button:
                            break
                    except:
                        continue
                
                if submit_button:
                    await submit_button.click()
                    await self.page.wait_for_timeout(3000)
                    
                    # Проверяем результат
                    page_text = await self.page.content()
                    
                    if "уже откликались" in page_text.lower() or "already" in page_text.lower():
                        return "already", "Уже откликались на эту вакансию"
                    elif "тест" in page_text.lower() or "test" in page_text.lower():
                        self.stats["total_tests"] = self.stats.get("total_tests", 0) + 1
                        self.save_stats()
                        return "test", "Требуется пройти тест"
                    elif "лимит" in page_text.lower() or "limit" in page_text.lower():
                        return "limit", "Достигнут лимит откликов"
                    else:
                        self.stats["total_responses"] = self.stats.get("total_responses", 0) + 1
                        self.stats["last_response_time"] = datetime.now().isoformat()
                        self.save_stats()
                        self.add_applied(vacancy_id)
                        return "success", "Отклик успешно отправлен!"
                else:
                    return "error", "Кнопка отправки не найдена"
                    
            except Exception as e:
                logger.error(f"Ошибка при отправке отклика: {e}")
                return "error", f"Ошибка: {str(e)[:100]}"
        except Exception as e:
            logger.error(f"Ошибка отправки отклика: {e}")
            return "error", f"Ошибка: {str(e)[:100]}"
    
    async def process_vacancies(self, callback=None):
        """Обработать вакансии из всех URL"""
        logger.info("process_vacancies начат")
        
        if not self.config.get("search_urls"):
            logger.warning("Нет настроенных URL для поиска")
            return "Нет настроенных URL для поиска"
        
        try:
            logger.info("Инициализация браузера...")
            await self.init_browser()
            logger.info("Установка cookies...")
            cookies_set = await self.set_cookies()
            if not cookies_set:
                missing = []
                if not self.config.get("hhtoken"):
                    missing.append("hhtoken")
                if not self.config.get("hhul"):
                    missing.append("hhul")
                if not self.config.get("crypted_id"):
                    missing.append("crypted_id")
                if not self.config.get("_xsrf"):
                    missing.append("_xsrf")
                
                error_msg = f"❌ Ошибка: не удалось установить cookies.\n\n"
                if missing:
                    error_msg += f"Отсутствуют токены: {', '.join(missing)}\n\n"
                    error_msg += f"Зайдите в ⚙️ Настройки → 🔑 Токены HH и добавьте недостающие токены."
                else:
                    error_msg += "Проверьте токены в настройках."
                
                logger.error(f"Не удалось установить cookies. Отсутствуют: {missing}")
                return error_msg
            
            all_vacancies = []
            applied = self.load_applied()
            logger.info(f"Загружено {len(applied)} уже откликнутых вакансий")
            
            # Собираем вакансии
            urls = self.config["search_urls"]
            logger.info(f"Обработка {len(urls)} URL для поиска")
            
            for url_idx, url in enumerate(urls, 1):
                logger.info(f"Обработка URL {url_idx}/{len(urls)}: {url}")
                if callback:
                    await callback(f"📥 Сканирую URL {url_idx}/{len(urls)}...")
                
                # Нормализуем базовый URL
                base_url = self.normalize_search_url(url)
                logger.info(f"Нормализованный URL: {base_url}")
                
                for page_num in range(self.config.get("pages_per_url", 5)):
                    try:
                        # Правильно формируем URL для страницы
                        if "?" in base_url:
                            page_url = f"{base_url}&page={page_num}"
                        else:
                            page_url = f"{base_url}?page={page_num}"
                        
                        logger.info(f"Загрузка страницы {page_num + 1}: {page_url}")
                        vacancies = await self.get_vacancy_ids_from_page(page_url)
                        all_vacancies.extend(vacancies)
                        logger.info(f"Найдено {len(vacancies)} вакансий на странице {page_num + 1}")
                        
                        if callback:
                            await callback(f"Найдено {len(vacancies)} вакансий на странице {page_num + 1}")
                        
                        # Если на странице нет вакансий и это не первая страница, прекращаем
                        if len(vacancies) == 0 and page_num > 0:
                            logger.info(f"Страница {page_num + 1} пуста, прекращаю обработку этого URL")
                            break
                        
                        await asyncio.sleep(1)
                    except Exception as e:
                        logger.error(f"Ошибка при обработке страницы {page_num + 1}: {e}", exc_info=True)
                        if callback:
                            await callback(f"⚠️ Ошибка на странице {page_num + 1}: {str(e)[:50]}")
                        # Продолжаем со следующей страницей
                        continue
            
            # Фильтруем уже откликнутые
            unique_vacancies = list(set(all_vacancies))
            logger.info(f"Всего найдено {len(unique_vacancies)} уникальных вакансий")
            new_vacancies = [v for v in unique_vacancies if v not in applied]
            logger.info(f"Новых вакансий для обработки: {len(new_vacancies)}")
            
            if not new_vacancies:
                return f"Найдено {len(unique_vacancies)} вакансий, все уже обработаны"
            
            if callback:
                await callback(f"✅ Найдено {len(new_vacancies)} новых вакансий для отклика")
            
            # Отправляем отклики
            success_count = 0
            error_count = 0
            test_count = 0
            already_count = 0
            
            for idx, vacancy_id in enumerate(new_vacancies, 1):
                if not self.is_running:
                    logger.info("Процесс остановлен пользователем")
                    break
                    
                if callback:
                    await callback(f"Обработка {idx}/{len(new_vacancies)}: {vacancy_id}")
                
                try:
                    result, message = await self.send_response_to_vacancy(vacancy_id)
                    logger.info(f"Вакансия {vacancy_id}: {result} - {message}")
                    
                    if result == "success":
                        success_count += 1
                    elif result == "test":
                        test_count += 1
                    elif result == "already":
                        already_count += 1
                    elif result == "limit":
                        logger.warning("Достигнут лимит откликов")
                        if callback:
                            await callback("⚠️ Достигнут лимит откликов!")
                        break
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"Ошибка при обработке вакансии {vacancy_id}: {e}")
                    error_count += 1
                
                await asyncio.sleep(self.config.get("response_delay", 3))
            
            result_msg = (
                f"✅ Обработано {len(new_vacancies)} вакансий:\n"
                f"• Успешно: {success_count}\n"
                f"• Требуют тест: {test_count}\n"
                f"• Уже откликались: {already_count}\n"
                f"• Ошибок: {error_count}"
            )
            logger.info(f"process_vacancies завершён: {result_msg}")
            return result_msg
            
        except Exception as e:
            logger.error(f"Критическая ошибка в process_vacancies: {e}", exc_info=True)
            raise
        finally:
            try:
                await self.close_browser()
            except:
                pass


# Глобальный экземпляр бота
bot_instance = HHBot()


# ========== HANDLERS ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    keyboard = [
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("🚀 Запустить отклики", callback_data="start_responses")],
        [InlineKeyboardButton("📤 Поднять резюме", callback_data="touch_resume")],
        [InlineKeyboardButton("❌ Остановить", callback_data="stop")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 Бот для автоматизации откликов на hh.ru\n\n"
        "Использует браузерную автоматизацию для реального взаимодействия с сайтом.\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    if not query:
        return
    
    logger.info(f"button_handler вызван с callback_data: {query.data}")
    
    # Обрабатываем только определённые callback
    handled_callbacks = {
        "settings", "stats", "start_responses", "touch_resume", 
        "stop", "back_to_main", "setting_params"
    }
    
    if query.data not in handled_callbacks:
        # Не обрабатываем, передаём дальше
        logger.debug(f"Callback {query.data} не обрабатывается здесь, передаю дальше")
        return
    
    await query.answer()
    
    if query.data == "settings":
        await show_settings(query)
    elif query.data == "stats":
        await show_stats(query)
    elif query.data == "start_responses":
        logger.info("Запускаю start_responses в отдельной задаче")
        # Запускаем в отдельной задаче, чтобы не блокировать обработку других запросов
        asyncio.create_task(start_responses(query))
    elif query.data == "touch_resume":
        await touch_resume_handler(query)
    elif query.data == "stop":
        await stop_handler(query)
    elif query.data == "setting_params":
        config = bot_instance.config
        keyboard = [
            [InlineKeyboardButton("◀️ Назад", callback_data="settings")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"⚙️ Параметры\n\n"
            f"Страниц на URL: {config.get('pages_per_url', 5)}\n"
            f"Задержка между откликами: {config.get('response_delay', 3)} сек\n"
            f"Интервал поднятия резюме: {config.get('resume_touch_interval_hours', 4)} часов\n\n"
            f"Для изменения параметров отредактируйте файл data/bot_config.json",
            reply_markup=reply_markup
        )
    elif query.data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("🚀 Запустить отклики", callback_data="start_responses")],
            [InlineKeyboardButton("📤 Поднять резюме", callback_data="touch_resume")],
            [InlineKeyboardButton("❌ Остановить", callback_data="stop")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🤖 Бот для автоматизации откликов на hh.ru\n\n"
            "Использует браузерную автоматизацию для реального взаимодействия с сайтом.\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )


async def show_settings(query):
    """Показать настройки"""
    config = bot_instance.config
    keyboard = [
        [InlineKeyboardButton("🔑 Токены HH", callback_data="setting_tokens")],
        [InlineKeyboardButton("📄 Resume Hash", callback_data="setting_resume")],
        [InlineKeyboardButton("✉️ Сопроводительное письмо", callback_data="setting_letter")],
        [InlineKeyboardButton("🔗 URL поиска", callback_data="setting_urls")],
        [InlineKeyboardButton("⚙️ Параметры", callback_data="setting_params")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status = "✅ Настроено" if all([
        config.get("hhtoken"),
        config.get("resume_hash")
    ]) else "❌ Не настроено"
    
    await query.edit_message_text(
        f"⚙️ Настройки\n\n"
        f"Статус: {status}\n\n"
        f"Выберите параметр для изменения:",
        reply_markup=reply_markup
    )


async def show_stats(query):
    """Показать статистику"""
    stats = bot_instance.stats
    config = bot_instance.config
    
    total = stats.get("total_responses", 0)
    tests = stats.get("total_tests", 0)
    errors = stats.get("total_errors", 0)
    
    last_touch = stats.get("last_resume_touch")
    if last_touch:
        try:
            dt = datetime.fromisoformat(last_touch)
            last_touch_str = dt.strftime("%d.%m.%Y %H:%M")
        except:
            last_touch_str = last_touch
    else:
        last_touch_str = "Никогда"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📊 Статистика\n\n"
        f"✅ Всего откликов: {total}\n"
        f"🧪 Требуют тест: {tests}\n"
        f"❌ Ошибок: {errors}\n"
        f"📤 Последнее поднятие резюме: {last_touch_str}\n\n"
        f"🔗 URL для поиска: {len(config.get('search_urls', []))}",
        reply_markup=reply_markup
    )


async def start_responses(query):
    """Запустить процесс откликов"""
    logger.info(f"start_responses вызвана, callback_data: {query.data}")
    
    # Небольшая задержка для гарантии, что ответ на callback отправлен
    await asyncio.sleep(0.1)
    
    try:
        if bot_instance.is_running:
            logger.warning("Процесс уже запущен")
            try:
                await query.answer("⚠️ Процесс уже запущен!", show_alert=True)
            except Exception as e:
                logger.error(f"Ошибка при отправке ответа: {e}")
            return
        
        config = bot_instance.config
        logger.info(f"Проверка конфигурации: hhtoken={bool(config.get('hhtoken'))}, resume_hash={bool(config.get('resume_hash'))}, urls={len(config.get('search_urls', []))}")
        
        if not config.get("hhtoken") or not config.get("resume_hash"):
            logger.warning("Не настроены токены или resume_hash")
            try:
                await query.answer("❌ Сначала настройте токены и resume_hash!", show_alert=True)
            except Exception as e:
                logger.error(f"Ошибка при отправке ответа: {e}")
            return
        
        if not config.get("search_urls"):
            logger.warning("Не настроены URL для поиска")
            try:
                await query.answer("❌ Сначала настройте URL для поиска вакансий!", show_alert=True)
            except Exception as e:
                logger.error(f"Ошибка при отправке ответа: {e}")
            return
        
        logger.info("Начинаю процесс откликов")
        try:
            await query.edit_message_text("🚀 Запускаю процесс откликов...")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            try:
                await query.message.reply_text("🚀 Запускаю процесс откликов...")
            except Exception as e2:
                logger.error(f"Ошибка при отправке нового сообщения: {e2}")
        
        async def progress_callback(message: str):
            try:
                logger.info(f"Progress: {message}")
                await query.message.reply_text(message)
            except Exception as e:
                logger.error(f"Ошибка в progress_callback: {e}")
        
        bot_instance.is_running = True
        
        try:
            logger.info("Вызываю process_vacancies")
            result = await bot_instance.process_vacancies(progress_callback)
            logger.info(f"process_vacancies завершён: {result}")
            try:
                await query.message.reply_text(f"✅ Завершено!\n\n{result}")
            except Exception as e:
                logger.error(f"Ошибка при отправке результата: {e}")
        except Exception as e:
            logger.error(f"Ошибка в process_vacancies: {e}", exc_info=True)
            error_msg = str(e)[:500]  # Ограничиваем длину сообщения
            try:
                await query.message.reply_text(f"❌ Ошибка: {error_msg}")
            except Exception as e2:
                logger.error(f"Ошибка при отправке сообщения об ошибке: {e2}")
        finally:
            bot_instance.is_running = False
            logger.info("Процесс остановлен")
        
        try:
            keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text("Выберите действие:", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Ошибка при отправке финального сообщения: {e}")
    except Exception as e:
        logger.error(f"Критическая ошибка в start_responses: {e}", exc_info=True)
        try:
            await query.answer(f"❌ Ошибка: {str(e)[:100]}", show_alert=True)
        except:
            pass


async def touch_resume_handler(query):
    """Обработать поднятие резюме"""
    config = bot_instance.config
    if not config.get("hhtoken") or not config.get("resume_hash"):
        await query.answer("❌ Сначала настройте токены и resume_hash!", show_alert=True)
        return
    
    await query.edit_message_text("📤 Поднимаю резюме...")
    
    success, message = await bot_instance.touch_resume()
    
    if success:
        await query.edit_message_text(f"✅ {message}")
    else:
        await query.edit_message_text(f"❌ {message}")
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выберите действие:", reply_markup=reply_markup)


async def stop_handler(query):
    """Остановить процесс"""
    bot_instance.is_running = False
    await query.answer("⏹ Остановлено", show_alert=True)
    await query.edit_message_text("⏹ Процесс остановлен")
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Выберите действие:", reply_markup=reply_markup)


async def handle_setting(query, context: ContextTypes.DEFAULT_TYPE):
    """Обработать выбор настройки"""
    if query.data == "setting_tokens":
        # Показываем текущее состояние токенов
        config = bot_instance.config
        current_status = []
        if config.get('hhtoken'):
            current_status.append("✅ hhtoken")
        else:
            current_status.append("❌ hhtoken")
        if config.get('hhul'):
            current_status.append("✅ hhul")
        else:
            current_status.append("❌ hhul")
        if config.get('crypted_id'):
            current_status.append("✅ crypted_id")
        else:
            current_status.append("❌ crypted_id")
        if config.get('_xsrf'):
            current_status.append("✅ xsrf")
        else:
            current_status.append("❌ xsrf")
        
        status_text = "\n".join(current_status)
        
        await query.edit_message_text(
            f"🔑 Настройка токенов HH\n\n"
            f"Текущее состояние:\n{status_text}\n\n"
            f"Отправьте токены в формате (можно все сразу или по одному):\n"
            f"hhtoken=ваш_токен\n"
            f"hhul=ваш_токен\n"
            f"crypted_id=ваш_токен\n"
            f"xsrf=ваш_токен\n\n"
            f"Или отправьте /cancel для отмены"
        )
        return SETTING_TOKEN
    elif query.data == "setting_resume":
        await query.edit_message_text(
            "📄 Настройка Resume Hash\n\n"
            "Отправьте hash вашего резюме (из URL: https://hh.ru/resume/HASH)\n\n"
            "Или отправьте /cancel для отмены"
        )
        return SETTING_RESUME
    elif query.data == "setting_letter":
        await query.edit_message_text(
            "✉️ Настройка сопроводительного письма\n\n"
            "Отправьте текст письма (можно многострочное)\n\n"
            "Или отправьте /cancel для отмены"
        )
        return SETTING_LETTER
    elif query.data == "setting_urls":
        current_urls = bot_instance.config.get('search_urls', [])
        status_text = f"Текущих URL: {len(current_urls)}\n\n" if current_urls else "URL не настроены\n\n"
        
        await query.edit_message_text(
            f"🔗 Настройка URL для поиска\n\n"
            f"{status_text}"
            f"Отправьте URL поиска вакансий:\n"
            f"• Полный URL: https://hh.ru/search/vacancy?text=Python&area=1\n"
            f"• Или поисковый запрос: Python разработчик\n"
            f"• Можно несколько URL (каждое с новой строки)\n\n"
            f"Примеры:\n"
            f"https://hh.ru/search/vacancy?text=devops&area=1\n"
            f"https://hh.ru/search/vacancy?text=backend&experience=between3And6\n\n"
            f"Или отправьте /cancel для отмены"
        )
        return SETTING_URL
    elif query.data == "setting_params":
        config = bot_instance.config
        keyboard = [
            [InlineKeyboardButton("◀️ Назад", callback_data="settings")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"⚙️ Параметры\n\n"
            f"Страниц на URL: {config.get('pages_per_url', 5)}\n"
            f"Задержка между откликами: {config.get('response_delay', 3)} сек\n"
            f"Интервал поднятия резюме: {config.get('resume_touch_interval_hours', 4)} часов\n\n"
            f"Для изменения параметров отредактируйте файл data/bot_config.json",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    elif query.data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("🚀 Запустить отклики", callback_data="start_responses")],
            [InlineKeyboardButton("📤 Поднять резюме", callback_data="touch_resume")],
            [InlineKeyboardButton("❌ Остановить", callback_data="stop")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🤖 Бот для автоматизации откликов на hh.ru\n\n"
            "Использует браузерную автоматизацию для реального взаимодействия с сайтом.\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
        return ConversationHandler.END


async def setting_token_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик установки токенов"""
    text = update.message.text
    
    try:
        logger.info(f"Получены токены: {text[:100]}...")  # Логируем первые 100 символов
        
        # Парсим токены
        tokens = {}
        lines = text.strip().split('\n')
        for line in lines:
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if key == 'hhtoken':
                    tokens['hhtoken'] = value
                elif key == 'hhul':
                    tokens['hhul'] = value
                elif key == 'crypted_id':
                    tokens['crypted_id'] = value
                elif key == 'xsrf':
                    tokens['_xsrf'] = value
        
        # Проверяем наличие всех токенов
        required_tokens = ['hhtoken', 'hhul', 'crypted_id', '_xsrf']
        missing_tokens = []
        provided_tokens = []
        
        for token_key in required_tokens:
            if token_key in tokens and tokens[token_key]:
                bot_instance.config[token_key] = tokens[token_key]
                provided_tokens.append(token_key)
            else:
                missing_tokens.append(token_key)
        
        # Сохраняем то, что есть
        bot_instance.save_config()
        
        # Формируем ответ
        if missing_tokens:
            # Показываем какие токены отсутствуют
            missing_names = {
                'hhtoken': 'hhtoken',
                'hhul': 'hhul',
                'crypted_id': 'crypted_id',
                '_xsrf': 'xsrf'
            }
            missing_list = ', '.join([missing_names.get(t, t) for t in missing_tokens])
            
            response = (
                f"⚠️ Сохранено {len(provided_tokens)} из {len(required_tokens)} токенов.\n\n"
                f"❌ Отсутствуют: {missing_list}\n\n"
                f"Отправьте недостающие токены в том же формате:\n"
                f"hhtoken=ваш_токен\n"
                f"hhul=ваш_токен\n"
                f"crypted_id=ваш_токен\n"
                f"xsrf=ваш_токен\n\n"
                f"Или отправьте /cancel для отмены"
            )
            await update.message.reply_text(response)
            return SETTING_TOKEN  # Продолжаем ожидать ввод
        else:
            await update.message.reply_text("✅ Все токены успешно сохранены!")
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Ошибка при обработке токенов: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Ошибка: {str(e)}\n\n"
            f"Попробуйте ещё раз или отправьте /cancel для отмены"
        )
        return SETTING_TOKEN


async def setting_resume_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик установки resume hash"""
    text = update.message.text.strip()
    bot_instance.config['resume_hash'] = text
    bot_instance.save_config()
    await update.message.reply_text("✅ Resume hash сохранён!")
    return ConversationHandler.END


async def setting_letter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик установки письма"""
    text = update.message.text
    bot_instance.config['letter'] = text
    bot_instance.save_config()
    await update.message.reply_text("✅ Сопроводительное письмо сохранено!")
    return ConversationHandler.END


async def setting_url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик установки URL"""
    text = update.message.text.strip()
    urls = [url.strip() for url in text.split('\n') if url.strip()]
    
    # Проверяем и нормализуем URL
    normalized_urls = []
    invalid_urls = []
    
    for url in urls:
        normalized = bot_instance.normalize_search_url(url)
        # Проверяем, что это валидный URL
        if normalized.startswith('http'):
            normalized_urls.append(normalized)
        else:
            invalid_urls.append(url)
    
    if invalid_urls:
        await update.message.reply_text(
            f"⚠️ Некоторые URL некорректны:\n" + "\n".join(invalid_urls[:5]) +
            f"\n\nИспользуйте полные URL вида:\n"
            f"https://hh.ru/search/vacancy?text=Python&area=1\n\n"
            f"Или отправьте /cancel для отмены"
        )
        return SETTING_URL
    
    bot_instance.config['search_urls'] = normalized_urls
    bot_instance.save_config()
    
    response = f"✅ Сохранено {len(normalized_urls)} URL!\n\n"
    for idx, url in enumerate(normalized_urls[:3], 1):
        # Показываем короткую версию URL
        short_url = url[:60] + "..." if len(url) > 60 else url
        response += f"{idx}. {short_url}\n"
    if len(normalized_urls) > 3:
        response += f"... и ещё {len(normalized_urls) - 3}"
    
    await update.message.reply_text(response)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text("❌ Операция отменена")
    return ConversationHandler.END


def main():
    """Главная функция запуска бота"""
    # Токен Telegram бота - нужно установить через переменную окружения или в коде
    import os
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    
    if not TELEGRAM_TOKEN:
        print("❌ Ошибка: не указан TELEGRAM_BOT_TOKEN")
        print("Установите переменную окружения: export TELEGRAM_BOT_TOKEN='ваш_токен'")
        return
    
    # Создаём приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Обработчик разговора для настроек
    async def setting_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query:
            await query.answer()
            result = await handle_setting(query, context)
            return result
        return ConversationHandler.END
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(setting_entry, pattern="^setting_")],
        states={
            SETTING_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, setting_token_handler)],
            SETTING_RESUME: [MessageHandler(filters.TEXT & ~filters.COMMAND, setting_resume_handler)],
            SETTING_LETTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, setting_letter_handler)],
            SETTING_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, setting_url_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    # Регистрируем обработчики (важен порядок!)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)  # ConversationHandler обрабатывает setting_* callback для ввода текста
    # Общий button_handler обрабатывает остальные callback (settings, stats, etc.)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    print("🤖 Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
