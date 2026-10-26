"""Тексти інтерфейсу бота трьома мовами. Відповіді AI модель пише сама мовою клієнта."""
from __future__ import annotations

TEXTS = {
    "uk": {
        "start": "Вітаю, <b>{name}</b>! 👋\n\nЯ AI-консультант магазину <b>{shop}</b>. Запитуйте про товари, "
                 "доставку, оплату, гарантію чи повернення — відповім за кілька секунд.\n\n"
                 "Якщо знадобиться жива людина, натисніть «👤 Менеджер».",
        "btn_manager": "👤 Менеджер",
        "btn_help": "ℹ️ Що ти вмієш?",
        "help": "Я відповідаю на питання про магазин <b>{shop}</b>:\n"
                "• товари та їх характеристики\n• доставка й оплата\n• гарантія та повернення\n"
                "• графік роботи й контакти\n\nПишіть звичайними словами, будь-якою мовою 🙂\n"
                "/reset — почати розмову спочатку",
        "no_answer": "Хм, на це питання в мене немає точної відповіді 🤔\nМожу покликати менеджера — він допоможе.",
        "btn_call": "👤 Покликати менеджера",
        "error": "Вибачте, сталася технічна помилка 😔 Спробуйте ще раз за хвилину або покличте менеджера.",
        "handoff_ok": "Передаю вашу розмову менеджеру 👤\nВін відповість тут, у цьому чаті. Зазвичай це займає кілька хвилин.",
        "handoff_already": "Менеджер уже в розмові, просто пишіть сюди 🙂",
        "handoff_off": "Зараз менеджери недоступні 😔 Спробуйте пізніше або поставте питання мені.",
        "back_to_ai": "Розмову з менеджером завершено ✅\nЯкщо будуть питання — я знову на зв'язку 🤖",
        "reset": "Історію розмови очищено. Чим можу допомогти?",
        "manager_label": "👤 Менеджер",
    },
    "ru": {
        "start": "Здравствуйте, <b>{name}</b>! 👋\n\nЯ AI-консультант магазина <b>{shop}</b>. Спрашивайте о товарах, "
                 "доставке, оплате, гарантии или возврате — отвечу за пару секунд.\n\n"
                 "Если понадобится живой человек, нажмите «👤 Менеджер».",
        "btn_manager": "👤 Менеджер",
        "btn_help": "ℹ️ Что ты умеешь?",
        "help": "Я отвечаю на вопросы о магазине <b>{shop}</b>:\n"
                "• товары и характеристики\n• доставка и оплата\n• гарантия и возврат\n"
                "• график работы и контакты\n\nПишите обычными словами на любом языке 🙂\n"
                "/reset — начать разговор заново",
        "no_answer": "Хм, на этот вопрос у меня нет точного ответа 🤔\nМогу позвать менеджера — он поможет.",
        "btn_call": "👤 Позвать менеджера",
        "error": "Извините, произошла техническая ошибка 😔 Попробуйте через минуту или позовите менеджера.",
        "handoff_ok": "Передаю разговор менеджеру 👤\nОн ответит здесь, в этом чате. Обычно это занимает несколько минут.",
        "handoff_already": "Менеджер уже в разговоре, просто пишите сюда 🙂",
        "handoff_off": "Сейчас менеджеры недоступны 😔 Попробуйте позже или задайте вопрос мне.",
        "back_to_ai": "Разговор с менеджером завершён ✅\nЕсли будут вопросы — я снова на связи 🤖",
        "reset": "История разговора очищена. Чем могу помочь?",
        "manager_label": "👤 Менеджер",
    },
    "en": {
        "start": "Hi, <b>{name}</b>! 👋\n\nI'm the AI assistant of <b>{shop}</b>. Ask me about products, "
                 "delivery, payment, warranty or returns — I'll answer in seconds.\n\n"
                 "If you need a real person, tap «👤 Manager».",
        "btn_manager": "👤 Manager",
        "btn_help": "ℹ️ What can you do?",
        "help": "I answer questions about <b>{shop}</b>:\n"
                "• products and specs\n• delivery and payment\n• warranty and returns\n"
                "• opening hours and contacts\n\nJust write in plain words, any language 🙂\n"
                "/reset — start over",
        "no_answer": "Hmm, I don't have an exact answer to that 🤔\nI can call a manager to help you.",
        "btn_call": "👤 Call a manager",
        "error": "Sorry, a technical error occurred 😔 Please try again in a minute or call a manager.",
        "handoff_ok": "Passing your chat to a manager 👤\nThey'll reply right here. It usually takes a few minutes.",
        "handoff_already": "A manager is already in the chat, just write here 🙂",
        "handoff_off": "Managers are not available right now 😔 Please try later or ask me.",
        "back_to_ai": "The chat with the manager is closed ✅\nIf you have more questions, I'm here 🤖",
        "reset": "Chat history cleared. How can I help?",
        "manager_label": "👤 Manager",
    },
}

MANAGER_BUTTONS = {v["btn_manager"] for v in TEXTS.values()}
HELP_BUTTONS = {v["btn_help"] for v in TEXTS.values()}


def lang_of(code: str | None) -> str:
    code = (code or "").lower()
    if code.startswith("uk"):
        return "uk"
    if code.startswith(("ru", "be", "kk")):
        return "ru"
    if code.startswith("en"):
        return "en"
    return "uk"


def t(lang: str | None, key: str, **kw) -> str:
    return TEXTS.get(lang or "uk", TEXTS["uk"])[key].format(**kw)
