# AI FAQ bot for Telegram

[![CI](https://github.com/zhangir777/ai-faq-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/zhangir777/ai-faq-bot/actions/workflows/ci.yml)

**Hire me:** [Upwork](https://www.upwork.com/freelancers/~012c68804f9b4d4550) · [Fiverr](https://www.fiverr.com/akhmetov_zhangi) · [Telegram @ZhangirAkhmetov](https://t.me/ZhangirAkhmetov)

**Live demo:** [@zhangir_ai_faq_bot](https://t.me/zhangir_ai_faq_bot) (runs when my demo server is on)

A Telegram bot that answers customer questions 24/7 using your company's FAQ, then collects
leads (name + phone) into Excel and sends them to managers.

- Answers **only from your knowledge base** (`knowledge.md`): no made-up prices or services.
  If the answer isn't there, it says so and offers to leave a request.
- **English, Russian and Kazakh**: the customer picks a language in /start, and the AI replies
  in the language of the question.
- Lead capture: name → phone (button or typed, normalized to `+7…`) → saved to `data/leads.xlsx`
  with the customer's questions, and sent to managers in Telegram. Managers get the file with `/leads`.
- Runs on **free LLM APIs**: Groq (main model + fallback model), optional Google Gemini as a backup.
  If one provider is down or hits its limit, the next one answers.
- Per-user limit (30 questions/hour) to protect the free quota; short chat memory for follow-up questions.

| Answers from the FAQ | Lead capture |
|---|---|
| ![AI answers in English](docs/screenshots/1_answers_en.png) | ![Lead capture in English](docs/screenshots/2_lead_en.png) |

## Set up for a new client (10 minutes)
1. Replace `knowledge.md` with the client's info: services, prices, address, hours, payment, rules.
   Plain text or Markdown, no special format.
2. Change the greeting and button texts (EN/RU/KZ) in `TEXTS` in `bot/main.py`.
3. Copy `.env.example` to `.env` and fill in `BOT_TOKEN`, `ADMIN_IDS`, `GROQ_API_KEY`.

## Run
```bash
uv sync
uv run python -m bot.main
```
or with Docker:
```bash
docker compose up -d --build
```

## Tests
```bash
uv run pytest -q
```
Offline tests (no Telegram, no LLM): answer → lead → Excel → manager notification through the real
dispatcher with a fake Telegram API, provider fallback against a local fake API, rate limit, `/leads`.

## Stack
Python 3.12, aiogram 3, aiohttp, openpyxl, Groq / Gemini (OpenAI-compatible API).

## License
MIT

## На русском

AI-бот для Telegram, который 24/7 отвечает клиентам на вопросы по базе знаний компании и собирает заявки.

- Отвечает только по фактам из `knowledge.md` (услуги, цены, адрес, график, оплата). Если ответа нет, честно говорит об этом и предлагает оставить заявку.
- Русский, казахский, английский: клиент выбирает язык в /start, AI отвечает на языке вопроса.
- Заявка: имя → телефон → строка в Excel (`data/leads.xlsx`) с вопросами клиента + уведомление менеджеру в Telegram. Команда `/leads` присылает файл.
- Работает на бесплатных API (Groq, запасной Gemini), есть лимит сообщений на пользователя.

| Ответы (RU / KZ) | Заявка |
|---|---|
| ![Ответы на русском и казахском](docs/screenshots/3_answers_ru_kk.png) | ![Заявка на русском](docs/screenshots/4_lead_ru.png) |

Под ваш бизнес: нужны услуги с ценами, адрес, график и ответы на частые вопросы. Демо в этом репозитории: вымышленная студия красоты «Demo» в Алматы.
