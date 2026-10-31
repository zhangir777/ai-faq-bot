"""AI FAQ + lead bot. Edit knowledge.md and .env for each client.

Run: uv run python -m bot.main
"""

import asyncio
import logging
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

from bot.ai import AIError, ask, build_messages, parse_reply, providers_from_env
from bot.leads import normalize_phone, save_lead

ROOT = Path(__file__).resolve().parent.parent
CHOOSE_LANG = "Choose language / Выберите язык / Тілді таңдаңыз"
LANGS = {"en": "🇬🇧 English", "ru": "🇷🇺 Русский", "kk": "🇰🇿 Қазақша"}
TEXTS = {
    "en": {
        "greeting": "Hello! I'm the AI assistant of «Demo» beauty studio. Ask me anything about "
        "services, prices, opening hours or booking.",
        "lead_button": "📝 Leave a request",
        "ask_name": "What is your name?",
        "ask_phone": "Your phone number? Tap the button or type the number.",
        "share_phone": "📱 Share phone number",
        "done": "Thank you! A manager will contact you shortly.",
        "error": "I can't answer right now. Leave a request and a manager will reply to you.",
        "limit": "Too many messages. Try again in an hour or leave a request.",
        "no_leads": "No leads yet.",
    },
    "ru": {
        "greeting": "Здравствуйте! Я AI-помощник студии красоты «Demo». Спросите что угодно "
        "про услуги, цены, график или запись.",
        "lead_button": "📝 Оставить заявку",
        "ask_name": "Как вас зовут?",
        "ask_phone": "Ваш номер телефона? Нажмите кнопку или напишите номер.",
        "share_phone": "📱 Отправить номер",
        "done": "Спасибо! Менеджер свяжется с вами в ближайшее время.",
        "error": "Сейчас не могу ответить. Оставьте заявку, и менеджер ответит вам лично.",
        "limit": "Слишком много сообщений. Попробуйте через час или оставьте заявку.",
        "no_leads": "Заявок пока нет.",
    },
    "kk": {
        "greeting": "Сәлеметсіз бе! Мен «Demo» сұлулық студиясының AI-көмекшісімін. Қызметтер, "
        "бағалар, жұмыс уақыты немесе жазылу туралы сұраңыз.",
        "lead_button": "📝 Өтінім қалдыру",
        "ask_name": "Атыңыз кім?",
        "ask_phone": "Телефон нөміріңіз? Батырманы басыңыз немесе нөмірді жазыңыз.",
        "share_phone": "📱 Нөмірді жіберу",
        "done": "Рақмет! Менеджер жақын арада сізбен хабарласады.",
        "error": "Қазір жауап бере алмаймын. Өтінім қалдырыңыз, менеджер сізге өзі жауап береді.",
        "limit": "Хабарлама тым көп. Бір сағаттан кейін қайталаңыз немесе өтінім қалдырыңыз.",
        "no_leads": "Әзірге өтінім жоқ.",
    },
}
HISTORY_SIZE = 6  # last messages sent to the model as context
RATE_LIMIT = 30  # questions per user per hour, protects the free API quota

router = Router()
history: dict[int, deque] = defaultdict(lambda: deque(maxlen=HISTORY_SIZE))
requests_log: dict[int, deque] = defaultdict(deque)
langs: dict[int, str] = {}  # chosen language per user, in memory


class Lead(StatesGroup):
    name = State()
    phone = State()


def t(user, key: str) -> str:
    """Text in the language chosen in /start, English by default."""
    return TEXTS[langs.get(user.id, "en")][key]


def lead_kb(user):
    kb = InlineKeyboardBuilder()
    kb.button(text=t(user, "lead_button"), callback_data="lead")
    return kb.as_markup()


def lang_kb():
    kb = InlineKeyboardBuilder()
    for code, name in LANGS.items():
        kb.button(text=name, callback_data=f"lang:{code}")
    return kb.as_markup()


def allowed(user_id: int, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    log = requests_log[user_id]
    while log and now - log[0] > 3600:
        log.popleft()
    if len(log) >= RATE_LIMIT:
        return False
    log.append(now)
    return True


def last_questions(user_id: int) -> str:
    return " | ".join(m["content"] for m in history[user_id] if m["role"] == "user")[-1000:]


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    history.pop(message.from_user.id, None)
    await message.answer(CHOOSE_LANG, reply_markup=lang_kb())


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(call: CallbackQuery):
    lang = call.data.split(":", 1)[1]
    if lang in TEXTS:
        langs[call.from_user.id] = lang
    await call.message.answer(t(call.from_user, "greeting"), reply_markup=lead_kb(call.from_user))
    await call.answer()


@router.message(Command("leads"))
async def send_leads(message: Message, admin_ids: list[int], leads_path: Path):
    if message.from_user.id not in admin_ids:
        return
    if not leads_path.exists():
        return await message.answer(t(message.from_user, "no_leads"))
    await message.answer_document(FSInputFile(leads_path))


@router.message(Command("lead"))
async def lead_command(message: Message, state: FSMContext):
    await state.set_state(Lead.name)
    await message.answer(t(message.from_user, "ask_name"))


@router.callback_query(F.data == "lead")
async def lead_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(Lead.name)
    await call.message.answer(t(call.from_user, "ask_name"))
    await call.answer()


@router.message(Lead.name, F.text)
async def lead_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text[:100])
    await state.set_state(Lead.phone)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(message.from_user, "share_phone"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(t(message.from_user, "ask_phone"), reply_markup=kb)


@router.message(Lead.phone)
async def lead_phone(
    message: Message, state: FSMContext, bot: Bot, admin_ids: list[int], leads_path: Path
):
    raw = message.contact.phone_number if message.contact else (message.text or "")
    phone = normalize_phone(raw)
    if not phone:
        return await message.answer(t(message.from_user, "ask_phone"))
    data = await state.get_data()
    await state.clear()
    user = message.from_user
    question = last_questions(user.id) or "-"
    save_lead(leads_path, data["name"], phone, question, user.username or "", user.id)
    text = (
        f"📝 New lead\nName: {data['name']}\nPhone: {phone}\n"
        f"Question: {question}\nTelegram: @{user.username or '-'} (id {user.id})"
    )
    for admin_id in admin_ids:
        await bot.send_message(admin_id, text, parse_mode=None)
    await message.answer(t(message.from_user, "done"), reply_markup=ReplyKeyboardRemove())


@router.message(F.text)
async def question(
    message: Message,
    bot: Bot,
    session: aiohttp.ClientSession,
    providers: list,
    knowledge: str,
):
    user_id = message.from_user.id
    if not allowed(user_id):
        return await message.answer(
            t(message.from_user, "limit"), reply_markup=lead_kb(message.from_user)
        )
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    text = message.text[:1000]
    try:
        raw = await ask(session, providers, build_messages(knowledge, list(history[user_id]), text))
    except AIError:
        return await message.answer(
            t(message.from_user, "error"), reply_markup=lead_kb(message.from_user)
        )
    answer, wants_lead = parse_reply(raw)
    history[user_id].extend(
        [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
    )
    await message.answer(
        answer, parse_mode=None, reply_markup=lead_kb(message.from_user) if wants_lead else None
    )


def admin_ids_from_env() -> list[int]:
    return [int(x) for x in re.findall(r"\d+", os.getenv("ADMIN_IDS", ""))]


async def main() -> None:
    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO)
    providers = providers_from_env()
    if not providers:
        raise SystemExit("Set GROQ_API_KEY or GEMINI_API_KEY in .env")
    knowledge = (ROOT / os.getenv("KNOWLEDGE_FILE", "knowledge.md")).read_text(encoding="utf-8")
    bot = Bot(os.environ["BOT_TOKEN"])
    dp = Dispatcher()
    dp.include_router(router)
    async with aiohttp.ClientSession() as session:
        await dp.start_polling(
            bot,
            session=session,
            providers=providers,
            knowledge=knowledge,
            admin_ids=admin_ids_from_env(),
            leads_path=ROOT / os.getenv("LEADS_FILE", "data/leads.xlsx"),
        )


if __name__ == "__main__":
    asyncio.run(main())
