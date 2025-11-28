"""
AI-генератор идей для digital-продуктов
Telegram Bot с интеграцией Cerebras LLM
"""

import os
import logging
import asyncio
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum
import re

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, 
    CallbackQuery,
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.enums import ParseMode
from cerebras.cloud.sdk import Cerebras

# ============== КОНФИГУРАЦИЯ ==============

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY")
CEREBRAS_MODEL = "gpt-oss-120b"  # Или другая доступная модель

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============== СИСТЕМНЫЙ ПРОМПТ ==============

SYSTEM_PROMPT = """Ты — профессиональный продукт-менеджер и генератор идей цифровых продуктов.
Твоя задача: по данным пользователя (ниша, бюджет, рынок/география) формировать структурированный отчёт.

Всегда возвращай результат строго по структуре:

1. **📊 Краткий анализ ниши** — 2–3 предложения о текущем состоянии рынка и трендах.

2. **💡 Идеи приложений** — для каждой идеи:
   • Название
   • Краткое описание ценности (1-2 предложения)
   • Целевая аудитория

3. **🔧 Основные фичи** — для каждой идеи минимум 5-6 конкретных фич.

4. **⏱ Сроки разработки**:
   • MVP: X-Y месяцев
   • Полная версия: X-Y месяцев

5. **💰 Оценка стоимости** (учитывая указанный бюджет):
   • MVP: $X,XXX - $XX,XXX
   • Полная версия: $XX,XXX - $XXX,XXX
   
6. **📈 План монетизации** — минимум 3 конкретных варианта с примерами цен.

7. **⚠️ Риски и рекомендации** — 3-4 пункта.

Требования к стилю:
- Конкретика, никаких общих фраз типа "зависит от многих факторов"
- Реалистичные оценки на основе рыночных данных
- Пиши на русском языке
- Используй эмодзи для структурирования
- Адаптируй сложность под указанный бюджет
- Если бюджет маленький — предлагай более простые решения
- Если бюджет большой — предлагай более амбициозные идеи
- ВАЖНО: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать таблицы (ASCII tables). Telegram их не поддерживает.
- Вместо таблиц используй маркированные списки или блоки с заголовками.
- Если нужно сравнить данные, делай это через список:
  • Параметр 1: Значение
  • Параметр 2: Значение"""

# ============== ДАННЫЕ И КОНСТАНТЫ ==============

NICHES = [
    ("🏥 Здоровье и фитнес", "health_fitness"),
    ("📚 Образование", "education"),
    ("🛒 E-commerce", "ecommerce"),
    ("💼 B2B / SaaS", "b2b_saas"),
    ("🎮 Игры и развлечения", "games"),
    ("🍕 Еда и доставка", "food"),
    ("🏠 Недвижимость", "realestate"),
    ("💰 Финтех", "fintech"),
    ("✈️ Путешествия", "travel"),
    ("✍️ Ввести свою нишу", "custom"),
]

BUDGETS = [
    ("💵 $1,000 - $5,000 (микро)", "micro"),
    ("💵 $5,000 - $15,000 (малый)", "small"),
    ("💰 $15,000 - $50,000 (средний)", "medium"),
    ("💰 $50,000 - $150,000 (большой)", "large"),
    ("🏦 $150,000+ (enterprise)", "enterprise"),
]

MARKETS = [
    ("🇷🇺 Россия / СНГ", "russia_cis"),
    ("🇺🇸 США / Канада", "usa_canada"),
    ("🇪🇺 Европа", "europe"),
    ("🌏 Азия", "asia"),
    ("🌍 Глобальный", "global"),
    ("✍️ Указать свой", "custom"),
]

# Примеры идей для демонстрации
EXAMPLE_IDEAS = """
🎯 **Пример генерации: Ниша "Фитнес", бюджет $15-50K, рынок Россия**

---

📊 **Краткий анализ ниши**
Рынок фитнес-приложений в России растёт на 15-20% ежегодно. Основные тренды: персонализация тренировок через AI, интеграция с носимыми устройствами, геймификация. Высокая конкуренция, но есть ниши для локальных решений.

---

💡 **Идея #1: FitBuddy — AI-тренер с голосовым сопровождением**

Мобильное приложение с AI-тренером, который ведёт тренировку голосом, анализирует технику через камеру и адаптирует программу под прогресс пользователя.

🔧 **Фичи:**
• Голосовой AI-тренер на русском языке
• Анализ техники упражнений через камеру
• Адаптивные программы тренировок
• Интеграция с Apple Health / Google Fit
• Социальные челленджи с друзьями
• Трекер питания с распознаванием фото еды

⏱ **Сроки:** MVP 3-4 мес, полная версия 7-9 мес
💰 **Стоимость:** MVP $25,000-35,000, полная $60,000-90,000

📈 **Монетизация:**
• Подписка Premium: 299-499 ₽/мес
• Персональные программы: 1,500-3,000 ₽
• B2B для фитнес-клубов: от 15,000 ₽/мес

---

_Это сокращённый пример. Полный отчёт содержит 3-5 идей с детальной проработкой._
"""

# ============== FSM СОСТОЯНИЯ ==============

class IdeaGeneration(StatesGroup):
    """Состояния для генерации идей"""
    waiting_niche = State()
    waiting_custom_niche = State()
    waiting_budget = State()
    waiting_market = State()
    waiting_custom_market = State()
    confirming = State()
    generating = State()

class Settings(StatesGroup):
    """Состояния настроек"""
    main = State()
    ideas_count = State()
    report_format = State()

# ============== ХРАНЕНИЕ ДАННЫХ СЕССИИ ==============

@dataclass
class UserSession:
    """Данные сессии пользователя"""
    niche: Optional[str] = None
    niche_display: Optional[str] = None
    budget: Optional[str] = None
    budget_display: Optional[str] = None
    market: Optional[str] = None
    market_display: Optional[str] = None
    ideas_count: int = 4
    report_format: str = "detailed"  # detailed / short

# ============== КЛАВИАТУРЫ ==============

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню"""
    buttons = [
        [InlineKeyboardButton(text="🎯 Сгенерировать идеи", callback_data="generate")],
        [InlineKeyboardButton(text="🧩 Примеры идей", callback_data="examples")],
        [InlineKeyboardButton(text="🛠 Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_niche_keyboard() -> InlineKeyboardMarkup:
    """Выбор ниши"""
    buttons = []
    for i in range(0, len(NICHES), 2):
        row = [InlineKeyboardButton(text=NICHES[i][0], callback_data=f"niche_{NICHES[i][1]}")]
        if i + 1 < len(NICHES):
            row.append(InlineKeyboardButton(text=NICHES[i+1][0], callback_data=f"niche_{NICHES[i+1][1]}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_budget_keyboard() -> InlineKeyboardMarkup:
    """Выбор бюджета"""
    buttons = [[InlineKeyboardButton(text=b[0], callback_data=f"budget_{b[1]}")] for b in BUDGETS]
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_niche"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_market_keyboard() -> InlineKeyboardMarkup:
    """Выбор рынка"""
    buttons = []
    for i in range(0, len(MARKETS), 2):
        row = [InlineKeyboardButton(text=MARKETS[i][0], callback_data=f"market_{MARKETS[i][1]}")]
        if i + 1 < len(MARKETS):
            row.append(InlineKeyboardButton(text=MARKETS[i+1][0], callback_data=f"market_{MARKETS[i+1][1]}"))
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_budget"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirm_keyboard() -> InlineKeyboardMarkup:
    """Подтверждение генерации"""
    buttons = [
        [InlineKeyboardButton(text="✅ Сгенерировать", callback_data="confirm_generate")],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_market"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_after_generation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после генерации"""
    buttons = [
        [InlineKeyboardButton(text="🔄 Сгенерировать ещё", callback_data="regenerate")],
        [InlineKeyboardButton(text="🎯 Новый запрос", callback_data="generate")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_settings_keyboard(session: UserSession) -> InlineKeyboardMarkup:
    """Меню настроек"""
    format_text = "📝 Подробный" if session.report_format == "detailed" else "📋 Краткий"
    buttons = [
        [InlineKeyboardButton(
            text=f"🔢 Количество идей: {session.ideas_count}", 
            callback_data="settings_ideas_count"
        )],
        [InlineKeyboardButton(
            text=f"📄 Формат отчёта: {format_text}", 
            callback_data="settings_format"
        )],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_ideas_count_keyboard() -> InlineKeyboardMarkup:
    """Выбор количества идей"""
    buttons = [
        [
            InlineKeyboardButton(text="3", callback_data="count_3"),
            InlineKeyboardButton(text="4", callback_data="count_4"),
            InlineKeyboardButton(text="5", callback_data="count_5"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_format_keyboard() -> InlineKeyboardMarkup:
    """Выбор формата отчёта"""
    buttons = [
        [InlineKeyboardButton(text="📝 Подробный", callback_data="format_detailed")],
        [InlineKeyboardButton(text="📋 Краткий", callback_data="format_short")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отмены для текстового ввода"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

# ============== CEREBRAS LLM ==============

class LLMClient:
    """Клиент для работы с Cerebras LLM"""
    
    def __init__(self):
        self.client = Cerebras(api_key=CEREBRAS_API_KEY)
    
    async def generate_ideas(self, session: UserSession) -> str:
        """Генерация идей на основе данных сессии"""
        
        format_instruction = ""
        if session.report_format == "short":
            format_instruction = "\n\nВАЖНО: Сделай отчёт более кратким — по 2-3 фичи на идею, без подробных описаний рисков."
        
        user_prompt = f"""Сгенерируй {session.ideas_count} идей digital-продуктов/приложений.

Входные данные:
- Ниша: {session.niche_display}
- Бюджет: {session.budget_display}
- Целевой рынок: {session.market_display}
{format_instruction}

Дай конкретные, реалистичные идеи с учётом указанного бюджета и рынка."""

        try:
            # Запускаем синхронный вызов в executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    model=CEREBRAS_MODEL,
                    max_tokens=4000,
                    temperature=0.7,
                )
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return f"❌ Произошла ошибка при генерации: {str(e)}\n\nПопробуйте ещё раз или обратитесь к разработчику."


# ============== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==============

def process_ai_response(text: str) -> str:
    """
    Обрабатывает ответ от AI для форматирования в Telegram (HTML).
    """
    if not text:
        return ""
        
    # Удаляем HTML-теги, которые могут вызывать проблемы (оставляем только поддерживаемые)
    text = re.sub(r'<(?!/?(?:b|strong|i|em|u|s|a|code|pre)[^>]*>)(?:.|\n)*?>', '', text)
    
    # Обработка спойлеров
    text = re.sub(r'\|\|(.*?)\|\|', r'<span class="tg-spoiler">\1</span>', text)
    
    # Форматирование чисел (10000 -> 10 000)
    def format_numbers(match):
        return '{:,}'.format(int(match.group(0))).replace(',', ' ')
    
    text = re.sub(r'\b\d{4,}\b', format_numbers, text)

    # Удаление табличной разметки (если LLM всё же решит её использовать)
    # Превращаем строки таблицы | Cell | Cell | в строки с разделителями
    text = re.sub(r'\|\s*', '', text) # Удаляем вертикальные черты
    text = re.sub(r'[-]{3,}', '', text) # Удаляем горизонтальные разделители таблиц
    
    # Стандартные преобразования Markdown в HTML
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)  # Bold
    text = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', text)    # Italic
    text = re.sub(r'__([^_]+)__', r'<u>\1</u>', text)    # Underline
    text = re.sub(r'~~([^~]+)~~', r'<s>\1</s>', text)    # Strikethrough
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text) # Inline code
    text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL) # Code blocks
    
    # Ссылки [text](url) -> <a href="url">text</a>
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
    
    # Списки
    text = re.sub(r'(?m)^\s*-\s', '• ', text)
    
    # Заголовки ### -> <b>
    text = re.sub(r'(?m)^###\s*(.*?)$', r'<b>\1</b>', text)
    text = re.sub(r'(?m)^##\s*(.*?)$', r'<b>\1</b>', text)
    
    return text.strip()

def split_long_message(text: str, max_length: int = 4000) -> list[str]:
    """
    Умное разбиение длинного сообщения на части
    """
    if len(text) <= max_length:
        return [text]
        
    parts = []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    current_part = ""
    
    for sentence in sentences:
        if len(current_part) + len(sentence) <= max_length:
            current_part += sentence + " "
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = sentence + " "
    
    if current_part:
        parts.append(current_part.strip())
    
    # Если какое-то предложение оказалось длиннее max_length, разделим его жестко
    final_parts = []
    for part in parts:
        if len(part) > max_length:
            # Разбиваем по словам
            words = part.split()
            current_subpart = ""
            for word in words:
                if len(current_subpart) + len(word) + 1 <= max_length:
                    current_subpart += word + " "
                else:
                    final_parts.append(current_subpart.strip())
                    current_subpart = word + " "
            if current_subpart:
                final_parts.append(current_subpart.strip())
        else:
            final_parts.append(part)
            
    return final_parts

# ============== ИНИЦИАЛИЗАЦИЯ ==============

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

llm_client = LLMClient()

# Хранение сессий пользователей (в памяти)
user_sessions: dict[int, UserSession] = {}

def get_session(user_id: int) -> UserSession:
    """Получить или создать сессию пользователя"""
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession()
    return user_sessions[user_id]

# ============== ОБРАБОТЧИКИ ==============

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Команда /start"""
    await state.clear()
    
    welcome_text = """👋 **Привет! Я AI-генератор идей для digital-продуктов.**

Я помогу тебе:
• Найти перспективную идею для приложения
• Определить ключевые фичи
• Оценить сроки и стоимость разработки
• Продумать монетизацию

Просто укажи нишу, бюджет и целевой рынок — и получи детальный отчёт с 3-5 идеями!

👇 Выбери действие:"""
    
    await message.answer(
        welcome_text, 
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help"""
    help_text = """📖 **Как пользоваться ботом:**

1️⃣ Нажми "🎯 Сгенерировать идеи"
2️⃣ Выбери или введи нишу
3️⃣ Укажи бюджет на разработку
4️⃣ Выбери целевой рынок
5️⃣ Подтверди и получи отчёт!

**Команды:**
/start — Главное меню
/help — Эта справка
/generate — Быстрый старт генерации

**Настройки:**
• Количество идей: 3-5
• Формат: подробный или краткий

Если есть вопросы — пиши разработчику!"""
    
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

@router.message(Command("generate"))
async def cmd_generate(message: Message, state: FSMContext):
    """Быстрый старт генерации"""
    await state.set_state(IdeaGeneration.waiting_niche)
    
    await message.answer(
        "🎯 **Шаг 1/3: Выбери нишу**\n\nВыбери из списка или введи свою:",
        reply_markup=get_niche_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

# ============== CALLBACK HANDLERS ==============

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await callback.message.edit_text(
        "🏠 **Главное меню**\n\nВыбери действие:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "generate")
async def cb_generate(callback: CallbackQuery, state: FSMContext):
    """Начало генерации"""
    await state.set_state(IdeaGeneration.waiting_niche)
    
    await callback.message.edit_text(
        "🎯 **Шаг 1/3: Выбери нишу**\n\nВыбери из списка или введи свою:",
        reply_markup=get_niche_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "examples")
async def cb_examples(callback: CallbackQuery):
    """Показать примеры"""
    await callback.message.edit_text(
        EXAMPLE_IDEAS,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Сгенерировать свои идеи", callback_data="generate")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")],
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "about")
async def cb_about(callback: CallbackQuery):
    """О боте"""
    about_text = """ℹ️ **AI-генератор идей для digital-продуктов**

🤖 Использует передовые языковые модели для генерации реалистичных идей приложений.

**Возможности:**
• Генерация 3-5 идей под вашу нишу
• Оценка сроков и стоимости
• План монетизации
• Анализ рисков

**Технологии:**
• Cerebras LLM
• Python + aiogram

**Разработчик:** @your_username

Версия: 1.0.0"""
    
    await callback.message.edit_text(
        about_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")],
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery, state: FSMContext):
    """Настройки"""
    session = get_session(callback.from_user.id)
    
    await callback.message.edit_text(
        "🛠 **Настройки**\n\nВыбери параметр для изменения:",
        reply_markup=get_settings_keyboard(session),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "settings_ideas_count")
async def cb_settings_ideas_count(callback: CallbackQuery):
    """Настройка количества идей"""
    await callback.message.edit_text(
        "🔢 **Количество идей**\n\nВыбери, сколько идей генерировать:",
        reply_markup=get_ideas_count_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("count_"))
async def cb_count_select(callback: CallbackQuery):
    """Выбор количества идей"""
    count = int(callback.data.split("_")[1])
    session = get_session(callback.from_user.id)
    session.ideas_count = count
    
    await callback.answer(f"✅ Установлено: {count} идей")
    await callback.message.edit_text(
        "🛠 **Настройки**\n\nВыбери параметр для изменения:",
        reply_markup=get_settings_keyboard(session),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "settings_format")
async def cb_settings_format(callback: CallbackQuery):
    """Настройка формата"""
    await callback.message.edit_text(
        "📄 **Формат отчёта**\n\nВыбери предпочтительный формат:",
        reply_markup=get_format_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data.startswith("format_"))
async def cb_format_select(callback: CallbackQuery):
    """Выбор формата"""
    format_type = callback.data.split("_")[1]
    session = get_session(callback.from_user.id)
    session.report_format = format_type
    
    format_name = "Подробный" if format_type == "detailed" else "Краткий"
    await callback.answer(f"✅ Установлено: {format_name}")
    await callback.message.edit_text(
        "🛠 **Настройки**\n\nВыбери параметр для изменения:",
        reply_markup=get_settings_keyboard(session),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Отменено.\n\n🏠 **Главное меню**\n\nВыбери действие:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

# ============== NICHE SELECTION ==============

@router.callback_query(F.data.startswith("niche_"), StateFilter(IdeaGeneration.waiting_niche))
async def cb_niche_select(callback: CallbackQuery, state: FSMContext):
    """Выбор ниши"""
    niche_code = callback.data.replace("niche_", "")
    session = get_session(callback.from_user.id)
    
    if niche_code == "custom":
        await state.set_state(IdeaGeneration.waiting_custom_niche)
        await callback.message.edit_text(
            "✍️ **Введи свою нишу:**\n\nОпиши нишу или сферу бизнеса для генерации идей.",
            reply_markup=get_cancel_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Найти отображаемое название
    niche_display = next((n[0] for n in NICHES if n[1] == niche_code), niche_code)
    session.niche = niche_code
    session.niche_display = niche_display
    
    await state.set_state(IdeaGeneration.waiting_budget)
    await callback.message.edit_text(
        f"✅ Ниша: {niche_display}\n\n💰 **Шаг 2/3: Выбери бюджет на разработку:**",
        reply_markup=get_budget_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(StateFilter(IdeaGeneration.waiting_custom_niche))
async def msg_custom_niche(message: Message, state: FSMContext):
    """Ввод своей ниши"""
    session = get_session(message.from_user.id)
    session.niche = "custom"
    session.niche_display = message.text.strip()
    
    await state.set_state(IdeaGeneration.waiting_budget)
    await message.answer(
        f"✅ Ниша: {session.niche_display}\n\n💰 **Шаг 2/3: Выбери бюджет на разработку:**",
        reply_markup=get_budget_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

# ============== BUDGET SELECTION ==============

@router.callback_query(F.data.startswith("budget_"), StateFilter(IdeaGeneration.waiting_budget))
async def cb_budget_select(callback: CallbackQuery, state: FSMContext):
    """Выбор бюджета"""
    budget_code = callback.data.replace("budget_", "")
    session = get_session(callback.from_user.id)
    
    budget_display = next((b[0] for b in BUDGETS if b[1] == budget_code), budget_code)
    session.budget = budget_code
    session.budget_display = budget_display
    
    await state.set_state(IdeaGeneration.waiting_market)
    await callback.message.edit_text(
        f"✅ Ниша: {session.niche_display}\n"
        f"✅ Бюджет: {budget_display}\n\n"
        f"🌍 **Шаг 3/3: Выбери целевой рынок:**",
        reply_markup=get_market_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "back_to_niche", StateFilter(IdeaGeneration.waiting_budget))
async def cb_back_to_niche(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору ниши"""
    await state.set_state(IdeaGeneration.waiting_niche)
    await callback.message.edit_text(
        "🎯 **Шаг 1/3: Выбери нишу**\n\nВыбери из списка или введи свою:",
        reply_markup=get_niche_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

# ============== MARKET SELECTION ==============

@router.callback_query(F.data.startswith("market_"), StateFilter(IdeaGeneration.waiting_market))
async def cb_market_select(callback: CallbackQuery, state: FSMContext):
    """Выбор рынка"""
    market_code = callback.data.replace("market_", "")
    session = get_session(callback.from_user.id)
    
    if market_code == "custom":
        await state.set_state(IdeaGeneration.waiting_custom_market)
        await callback.message.edit_text(
            "✍️ **Введи целевой рынок:**\n\nУкажи страну, регион или характеристику аудитории.",
            reply_markup=get_cancel_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    market_display = next((m[0] for m in MARKETS if m[1] == market_code), market_code)
    session.market = market_code
    session.market_display = market_display
    
    await state.set_state(IdeaGeneration.confirming)
    await show_confirmation(callback.message, session)

@router.message(StateFilter(IdeaGeneration.waiting_custom_market))
async def msg_custom_market(message: Message, state: FSMContext):
    """Ввод своего рынка"""
    session = get_session(message.from_user.id)
    session.market = "custom"
    session.market_display = message.text.strip()
    
    await state.set_state(IdeaGeneration.confirming)
    await show_confirmation(message, session, edit=False)

@router.callback_query(F.data == "back_to_budget", StateFilter(IdeaGeneration.waiting_market))
async def cb_back_to_budget(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору бюджета"""
    session = get_session(callback.from_user.id)
    await state.set_state(IdeaGeneration.waiting_budget)
    await callback.message.edit_text(
        f"✅ Ниша: {session.niche_display}\n\n💰 **Шаг 2/3: Выбери бюджет на разработку:**",
        reply_markup=get_budget_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

# ============== CONFIRMATION & GENERATION ==============

async def show_confirmation(message: Message, session: UserSession, edit: bool = True):
    """Показать подтверждение"""
    confirm_text = f"""📋 **Проверь данные:**

🎯 **Ниша:** {session.niche_display}
💰 **Бюджет:** {session.budget_display}
🌍 **Рынок:** {session.market_display}
🔢 **Количество идей:** {session.ideas_count}

Всё верно? Нажми "Сгенерировать" для получения отчёта."""
    
    if edit:
        await message.edit_text(
            confirm_text,
            reply_markup=get_confirm_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.answer(
            confirm_text,
            reply_markup=get_confirm_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )

@router.callback_query(F.data == "back_to_market", StateFilter(IdeaGeneration.confirming))
async def cb_back_to_market(callback: CallbackQuery, state: FSMContext):
    """Назад к выбору рынка"""
    session = get_session(callback.from_user.id)
    await state.set_state(IdeaGeneration.waiting_market)
    await callback.message.edit_text(
        f"✅ Ниша: {session.niche_display}\n"
        f"✅ Бюджет: {session.budget_display}\n\n"
        f"🌍 **Шаг 3/3: Выбери целевой рынок:**",
        reply_markup=get_market_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.callback_query(F.data == "confirm_generate", StateFilter(IdeaGeneration.confirming))
async def cb_confirm_generate(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и запуск генерации"""
    session = get_session(callback.from_user.id)
    
    await state.set_state(IdeaGeneration.generating)
    await callback.message.edit_text(
        "⏳ **Генерирую идеи...**\n\n"
        "Это может занять 30-60 секунд. AI анализирует нишу, рынок и формирует персонализированные рекомендации.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Генерация
    result = await llm_client.generate_ideas(session)
    
    # Отправляем результат (может быть длинным)
    await state.clear()
    
    # Обработка и отправка результата
    processed_result = process_ai_response(result)
    parts = split_long_message(processed_result)
    
    for i, part in enumerate(parts):
        if i == len(parts) - 1:
            await callback.message.answer(
                part,
                reply_markup=get_after_generation_keyboard(),
                parse_mode=ParseMode.HTML
            )
        else:
            await callback.message.answer(part, parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "regenerate")
async def cb_regenerate(callback: CallbackQuery, state: FSMContext):
    """Повторная генерация с теми же параметрами"""
    session = get_session(callback.from_user.id)
    
    if not session.niche or not session.budget or not session.market:
        await callback.answer("❌ Сначала введите параметры", show_alert=True)
        return
    
    await state.set_state(IdeaGeneration.generating)
    await callback.message.edit_text(
        "⏳ **Генерирую новые идеи...**\n\n"
        "Использую те же параметры, но AI сгенерирует другие варианты.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    result = await llm_client.generate_ideas(session)
    await state.clear()
    
    processed_result = process_ai_response(result)
    parts = split_long_message(processed_result)
    
    for i, part in enumerate(parts):
        if i == len(parts) - 1:
            await callback.message.answer(
                part,
                reply_markup=get_after_generation_keyboard(),
                parse_mode=ParseMode.HTML
            )
        else:
            await callback.message.answer(part, parse_mode=ParseMode.HTML)

# ============== FALLBACK HANDLERS ==============

@router.message(StateFilter(IdeaGeneration.waiting_niche))
async def msg_fallback_niche(message: Message):
    """Fallback для выбора ниши"""
    await message.answer(
        "⚠️ Пожалуйста, выбери нишу из списка или нажми «Ввести свою нишу».",
        reply_markup=get_niche_keyboard()
    )

@router.message(StateFilter(IdeaGeneration.waiting_budget))
async def msg_fallback_budget(message: Message):
    """Fallback для выбора бюджета"""
    await message.answer(
        "⚠️ Пожалуйста, выбери бюджет из предложенных вариантов.",
        reply_markup=get_budget_keyboard()
    )

@router.message(StateFilter(IdeaGeneration.waiting_market))
async def msg_fallback_market(message: Message):
    """Fallback для выбора рынка"""
    await message.answer(
        "⚠️ Пожалуйста, выбери рынок из списка или нажми «Указать свой».",
        reply_markup=get_market_keyboard()
    )

@router.message()
async def msg_fallback_general(message: Message, state: FSMContext):
    """Общий fallback"""
    current_state = await state.get_state()
    
    if current_state is None:
        await message.answer(
            "👋 Используй меню для навигации!\n\n"
            "Нажми /start чтобы открыть главное меню.",
            reply_markup=get_main_menu_keyboard()
        )

# ============== MAIN ==============

async def main():
    """Запуск бота"""
    logger.info("Starting bot...")
    
    # Проверка конфигурации
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не установлен!")
    if not CEREBRAS_API_KEY:
        raise ValueError("CEREBRAS_API_KEY не установлен!")
    
    # Запуск
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
