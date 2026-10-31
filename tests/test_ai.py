import pytest
from aiohttp import ClientSession, web

from bot.ai import AIError, Provider, ask, build_messages, parse_reply, providers_from_env


def test_parse_reply_strips_tag_and_think():
    assert parse_reply("<think>hmm</think>Маникюр 7 000 ₸. [LEAD]") == ("Маникюр 7 000 ₸.", True)
    assert parse_reply("Мы работаем 10–21.") == ("Мы работаем 10–21.", False)


def test_build_messages_puts_knowledge_in_system_and_question_last():
    history = [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}]
    msgs = build_messages("Стрижка 4 000", history, "q2")
    assert msgs[0]["role"] == "system" and "Стрижка 4 000" in msgs[0]["content"]
    assert msgs[1:3] == history
    assert msgs[-1] == {"role": "user", "content": "q2"}


def test_providers_from_env(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert providers_from_env() == []
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    assert [p.name for p in providers_from_env()] == ["groq", "groq-fallback", "gemini"]


@pytest.fixture
async def fake_api():
    """Local server: /fail returns 429 (rate limit), /ok returns an answer."""

    async def fail(request):
        return web.Response(status=429, text="rate limit")

    async def ok(request):
        body = await request.json()
        assert request.headers["Authorization"] == "Bearer k"
        return web.json_response(
            {"choices": [{"message": {"content": f"hi from {body['model']}"}}]}
        )

    app = web.Application()
    app.router.add_post("/fail", fail)
    app.router.add_post("/ok", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    await runner.cleanup()


async def test_ask_falls_back_to_next_provider(fake_api):
    providers = [
        Provider("a", f"{fake_api}/fail", "k", "m1"),
        Provider("b", f"{fake_api}/ok", "k", "m2"),
    ]
    async with ClientSession() as session:
        assert await ask(session, providers, [{"role": "user", "content": "q"}]) == "hi from m2"


async def test_ask_raises_when_all_fail(fake_api):
    async with ClientSession() as session:
        with pytest.raises(AIError):
            await ask(session, [Provider("a", f"{fake_api}/fail", "k", "m")], [])
