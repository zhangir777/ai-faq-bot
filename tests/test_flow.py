"""Question -> AI answer -> lead flow through the real dispatcher with a fake Telegram API."""

import itertools
from datetime import datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendDocument, SendMessage
from aiogram.types import CallbackQuery, Chat, Contact, Message, Update
from aiogram.types import User as TgUser
from openpyxl import load_workbook

import bot.main as main
from bot.ai import AIError

ids = itertools.count(1)
USER = TgUser(id=10, is_bot=False, first_name="Test", username="client")
CHAT = Chat(id=10, type="private")
ADMIN = 99


class FakeSession(BaseSession):
    """Records every API call and returns a plausible result."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if method.__returning__ is bool:
            return True
        return Message(message_id=next(ids), date=datetime.now(), chat=CHAT, text="ok")

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    async def close(self):
        pass


def msg(text=None, contact=None, user=USER):
    return Update(
        update_id=next(ids),
        message=Message(
            message_id=next(ids), date=datetime.now(), chat=CHAT, from_user=user,
            text=text, contact=contact,
        ),
    )  # fmt: skip


def cb(data):
    m = Message(message_id=next(ids), date=datetime.now(), chat=CHAT, text="x")
    return Update(
        update_id=next(ids),
        callback_query=CallbackQuery(
            id=str(next(ids)), from_user=USER, chat_instance="1", message=m, data=data
        ),
    )


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(main.router, "_parent_router", None)  # router is a module singleton
    main.history.clear()
    main.requests_log.clear()
    main.langs.clear()
    session = FakeSession()
    bot = Bot("42:TEST", session=session)
    dp = Dispatcher()
    dp.include_router(main.router)
    leads = tmp_path / "leads.xlsx"
    kwargs = dict(session=None, providers=[], knowledge="kb", admin_ids=[ADMIN], leads_path=leads)

    async def feed(update):
        session.calls.clear()
        await dp.feed_update(bot, update, **kwargs)
        return [c for c in session.calls if isinstance(c, SendMessage | SendDocument)]

    return feed, leads, monkeypatch


async def test_question_then_lead_saved_and_admin_notified(env):
    feed, leads, monkeypatch = env

    async def fake_ask(session, providers, messages):
        assert messages[-1]["content"] == "Хочу на маникюр завтра"
        return "Маникюр стоит 7 000 ₸. Оставьте заявку. [LEAD]"

    monkeypatch.setattr(main, "ask", fake_ask)
    sent = await feed(msg("Хочу на маникюр завтра"))
    assert sent[0].text == "Маникюр стоит 7 000 ₸. Оставьте заявку."
    assert sent[0].reply_markup.inline_keyboard[0][0].callback_data == "lead"

    sent = await feed(cb("lead"))
    assert sent[0].text == main.TEXTS["en"]["ask_name"]
    await feed(msg("Айгуль"))
    sent = await feed(msg("12345"))  # bad phone -> asked again
    assert sent[0].text == main.TEXTS["en"]["ask_phone"]
    contact = Contact(phone_number="77771234567", first_name="A", user_id=USER.id)  # no "+"
    sent = await feed(msg(contact=contact))

    admin = [m for m in sent if m.chat_id == ADMIN][0]
    assert "+77771234567" in admin.text and "маникюр" in admin.text
    assert sent[-1].text == main.TEXTS["en"]["done"]
    row = list(load_workbook(leads).active.values)[1]
    assert row[1:4] == ("Айгуль", "+77771234567", "Хочу на маникюр завтра")


async def test_answer_without_lead_tag_has_no_button(env):
    feed, _, monkeypatch = env

    async def fake_ask(*args):
        return "Мы работаем 10:00–21:00."

    monkeypatch.setattr(main, "ask", fake_ask)
    sent = await feed(msg("График?"))
    assert sent[0].reply_markup is None


async def test_ai_error_offers_lead(env):
    feed, _, monkeypatch = env

    async def broken(*args):
        raise AIError("down")

    monkeypatch.setattr(main, "ask", broken)
    sent = await feed(msg("?"))
    assert sent[0].text == main.TEXTS["en"]["error"]


async def test_rate_limit(env):
    feed, _, monkeypatch = env
    monkeypatch.setattr(main, "RATE_LIMIT", 2)

    async def fake_ask(*args):
        return "ok"

    monkeypatch.setattr(main, "ask", fake_ask)
    await feed(msg("1"))
    await feed(msg("2"))
    sent = await feed(msg("3"))
    assert sent[0].text == main.TEXTS["en"]["limit"]


async def test_leads_command_only_for_admin(env):
    feed, leads, _ = env
    assert await feed(msg("/leads")) == []
    admin = TgUser(id=ADMIN, is_bot=False, first_name="Admin")
    sent = await feed(msg("/leads", user=admin))
    assert sent[0].text == main.TEXTS["en"]["no_leads"]


async def test_start_asks_language_then_greets_in_it(env):
    feed, _, _ = env
    sent = await feed(msg("/start"))
    langs = [b.callback_data for b in sent[0].reply_markup.inline_keyboard[0]]
    assert langs == ["lang:en", "lang:ru", "lang:kk"]
    sent = await feed(cb("lang:kk"))
    assert sent[0].text == main.TEXTS["kk"]["greeting"]
    assert sent[0].reply_markup.inline_keyboard[0][0].text == main.TEXTS["kk"]["lead_button"]


async def test_foreign_phone_and_start_hides_phone_keyboard(env):
    feed, leads, _ = env
    await feed(cb("lead"))
    await feed(msg("John"))
    sent = await feed(msg("/start"))  # left the lead form -> contact keyboard removed
    assert type(sent[0].reply_markup).__name__ == "ReplyKeyboardRemove"

    await feed(cb("lead"))
    await feed(msg("John"))
    sent = await feed(msg("+1 (415) 555-0100"))
    assert sent[-1].text == main.TEXTS["en"]["done"]
    assert list(load_workbook(leads).active.values)[1][2] == "+14155550100"
