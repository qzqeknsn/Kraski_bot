"""
Telegram AI-бот для компании "Центр Красок #1"
Использует Groq API (бесплатный, быстрый).

Установка:
    pip install python-telegram-bot groq

Запуск:
    python3 bot.py
"""

import logging
import os
from collections import defaultdict
from typing import Optional
from pathlib import Path

# ─── Загрузка bot.env ────────────────────────────────────────────────────────
def load_env(filepath="bot.env"):
    env_path = Path(filepath)
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

load_env("bot.env")

from groq import Groq
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from company_knowledge import COMPANY_KNOWLEDGE

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY",   "YOUR_GROQ_API_KEY")

MAX_HISTORY_MESSAGES = 10
MAX_USER_MESSAGE_LEN = 1000

# ─── Системный промпт ────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""Ты — консультант интернет-магазина "Центр Красок #1" (centr-krasok.kz) в Казахстане.

Твоя задача — помогать клиентам, отвечая на вопросы о компании, товарах, услугах и условиях работы.

## База знаний о компании:
{COMPANY_KNOWLEDGE}

## Правила:
1. Отвечай ТОЛЬКО на основе базы знаний о компании.
2. Если информации нет — честно скажи и предложи позвонить: +7 778 061-50-00 или написать: info@centr-krasok.kz.
3. Никогда не выдумывай цены, адреса, телефоны или характеристики товаров.
4. Пиши на языке вопроса (русский, казахский или английский).
5. Если вопрос не о компании — мягко верни разговор к теме магазина.
6. По ценам и конкретным товарам отправляй на centr-krasok.kz/catalog/.

## Стиль и оформление (строго обязательно):
- Пиши как живой грамотный человек — естественно, тепло, без канцелярщины
- БЕЗ эмодзи и стикеров — совсем
- Используй Telegram Markdown:
  * *жирный* для заголовков секций и ключевых слов
  * Абзацы разделяй пустой строкой
  * Списки через дефис: - пункт
- Структура: вступительный абзац → основное → следующий шаг
- В конце всегда предлагай следующий шаг (позвонить, написать, зайти на сайт)
"""

groq_client = Groq(api_key=GROQ_API_KEY)
conversation_history: dict[int, list[dict]] = defaultdict(list)


# ─── AI-логика ───────────────────────────────────────────────────────────────

def get_ai_response(chat_id: int, user_message: str) -> str:
    history = conversation_history[chat_id]
    history.append({"role": "user", "content": user_message})
    trimmed = history[-MAX_HISTORY_MESSAGES:]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + trimmed

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=1024,
            temperature=0.3,
        )
        assistant_message = response.choices[0].message.content
        history.append({"role": "assistant", "content": assistant_message})

        if len(history) > MAX_HISTORY_MESSAGES * 2:
            conversation_history[chat_id] = history[-MAX_HISTORY_MESSAGES:]

        return assistant_message

    except Exception as e:
        logger.error(f"Ошибка Groq API: {e}")
        if history:
            history.pop()
        return (
            "Временные технические неполадки. Попробуйте через минуту "
            "или свяжитесь с нами напрямую:\n\n"
            "+7 778 061-50-00\n"
            "info@centr-krasok.kz"
        )


def is_message_safe(text: str) -> tuple[bool, Optional[str]]:
    if len(text) > MAX_USER_MESSAGE_LEN:
        return False, f"Сообщение слишком длинное (максимум {MAX_USER_MESSAGE_LEN} символов)."
    injection_keywords = [
        "ignore previous instructions", "ignore all instructions",
        "забудь все инструкции", "игнорируй системный промпт",
        "system prompt", "ты теперь", "притворись что ты",
        "roleplay as", "act as", "jailbreak", " DAN ",
    ]
    for keyword in injection_keywords:
        if keyword.lower() in text.lower():
            return False, "Некорректный запрос."
    return True, None


# ─── Обработчики ─────────────────────────────────────────────────────────────

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Сбрасываем историю — бот не пишет первым, ждёт вопроса пользователя
    conversation_history[update.effective_chat.id] = []


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "*Как пользоваться ботом*\n\n"
        "Просто напишите вопрос о магазине Центр Красок #1 — я отвечу на основе актуальной информации о компании.\n\n"
        "*Примеры вопросов:*\n\n"
        "- Чем занимается компания?\n"
        "- Какие краски вы продаёте?\n"
        "- Где находится офис в Алматы?\n"
        "- Какие бренды есть в ассортименте?\n"
        "- Как оформить доставку?\n"
        "- Есть ли условия для дизайнеров?\n\n"
        "*Команды:*\n\n"
        "- /start — начать заново\n"
        "- /reset — очистить историю диалога\n"
        "- /help — эта справка\n\n"
        "По срочным вопросам звоните: +7 778 061-50-00\n"
        "Сайт: centr-krasok.kz"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conversation_history[update.effective_chat.id] = []
    await update.message.reply_text("История диалога очищена. Можете начать новый разговор.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    user_text = update.message.text.strip()

    logger.info(f"Сообщение от {user.full_name} (id={user.id}): {user_text[:80]}")

    is_safe, reason = is_message_safe(user_text)
    if not is_safe:
        await update.message.reply_text(
            f"{reason}\n\nПожалуйста, задайте вопрос о магазине Центр Красок #1."
        )
        return

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    response_text = get_ai_response(chat_id, user_text)
    await update.message.reply_text(response_text, parse_mode="Markdown")


# ─── Запуск ──────────────────────────────────────────────────────────────────

def main() -> None:
    if TELEGRAM_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        raise ValueError("Укажите TELEGRAM_TOKEN в файле bot.env")
    if GROQ_API_KEY == "YOUR_GROQ_API_KEY":
        raise ValueError("Укажите GROQ_API_KEY в файле bot.env")

    logger.info("🚀 Запуск бота Центр Красок #1 (Groq)...")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("help",  handle_help))
    app.add_handler(CommandHandler("reset", handle_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("✅ Бот запущен. Ожидание сообщений...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()