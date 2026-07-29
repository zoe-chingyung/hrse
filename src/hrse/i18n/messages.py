"""Bilingual (English / Traditional Chinese) message catalogue.

Design
------
* ``MessageKey`` — enum of every user-facing message.
* ``_CATALOGUE`` — ``{MessageKey: {Language: template}}``. Every key MUST have
  an entry for every ``Language`` member; a unit test enforces this.
* ``t(key, lang, **kwargs)`` — look up and ``str.format`` a template.
* ``bilingual_welcome()`` — the one message deliberately shown in BOTH
  languages at once, because it is sent before the chat has chosen one.

Pure Python — no AWS imports, fully unit-testable.
"""

from __future__ import annotations

from enum import StrEnum, auto

from hrse.models.chat_settings import Language


class MessageKey(StrEnum):
    """Every user-facing message the bot can send."""

    COMMAND_LIST = auto()
    LANGUAGE_PROMPT = auto()
    LANGUAGE_SET = auto()
    UNKNOWN_COMMAND = auto()
    SERVICE_UNAVAILABLE = auto()
    PRICES_HEADER_TODAY = auto()
    PRICES_HEADER_TOMORROW = auto()
    PRICES_TOMORROW_UNAVAILABLE = auto()
    PRICES_UNAVAILABLE = auto()
    PRICES_BEST_WINDOW = auto()
    PRICES_CHEAPEST = auto()
    PRICES_MOST_EXPENSIVE = auto()
    PRICES_AVERAGE = auto()
    HEALTH_OK = auto()
    LAUNDRY_RECORDED = auto()
    NO_EVENTS = auto()
    RECENT_EVENTS_HEADER = auto()
    WEEKLY_SUMMARY = auto()


_COMMANDS_EN = (
    "📋 <b>Commands</b>\n"
    "/prices — today's Agile electricity prices\n"
    "/prices_tomorrow — tomorrow's prices\n"
    "/laundry_done — record a laundry run\n"
    "/summary — weekly household summary\n"
    "/events — recent events\n"
    "/language — change language\n"
    "/health — service status"
)

_COMMANDS_ZH = (
    "📋 <b>指令</b>\n"
    "/prices — 今日 Agile 電價\n"
    "/prices_tomorrow — 聽日電價\n"
    "/laundry_done — 記錄一次洗衫\n"
    "/summary — 每週家居摘要\n"
    "/events — 最近事件\n"
    "/language — 更改語言\n"
    "/health — 服務狀態"
)

_CATALOGUE: dict[MessageKey, dict[Language, str]] = {
    MessageKey.COMMAND_LIST: {
        Language.EN: _COMMANDS_EN,
        Language.ZH: _COMMANDS_ZH,
    },
    MessageKey.LANGUAGE_PROMPT: {
        # Shown before a language is chosen, so both variants are identical
        # and bilingual by design.
        Language.EN: "🌐 Please choose your language / 請選擇語言:",
        Language.ZH: "🌐 Please choose your language / 請選擇語言:",
    },
    MessageKey.LANGUAGE_SET: {
        Language.EN: "✅ Language set to <b>English</b>.\n\n" + _COMMANDS_EN,
        Language.ZH: "✅ 語言已設定為<b>中文</b>。\n\n" + _COMMANDS_ZH,
    },
    MessageKey.UNKNOWN_COMMAND: {
        Language.EN: "🤖 Unknown command.\n\n" + _COMMANDS_EN,
        Language.ZH: "🤖 唔識呢個指令。\n\n" + _COMMANDS_ZH,
    },
    MessageKey.SERVICE_UNAVAILABLE: {
        Language.EN: "⚠️ Service unavailable.",
        Language.ZH: "⚠️ 服務暫時唔可用。",
    },
    MessageKey.PRICES_HEADER_TODAY: {
        Language.EN: "⚡ <b>Agile prices — today ({date})</b>",
        Language.ZH: "⚡ <b>Agile 電價 — 今日({date})</b>",
    },
    MessageKey.PRICES_HEADER_TOMORROW: {
        Language.EN: "⚡ <b>Agile prices — tomorrow ({date})</b>",
        Language.ZH: "⚡ <b>Agile 電價 — 聽日({date})</b>",
    },
    MessageKey.PRICES_TOMORROW_UNAVAILABLE: {
        Language.EN: (
            "⏳ Tomorrow's Agile prices aren't published yet.\n"
            "They usually appear around 16:00 UK time — try again later."
        ),
        Language.ZH: "⏳ 聽日嘅 Agile 電價未出。\n通常英國時間下晝四點左右公佈,遲啲再試。",
    },
    MessageKey.PRICES_UNAVAILABLE: {
        Language.EN: "⚠️ No price data available right now. Try again later.",
        Language.ZH: "⚠️ 而家攞唔到電價數據,遲啲再試。",
    },
    MessageKey.PRICES_BEST_WINDOW: {
        Language.EN: "🎯 Best {hours}h window: <b>{window}</b> (avg <b>{price}p</b>/kWh)",
        Language.ZH: "🎯 最抵 {hours} 小時窗口:<b>{window}</b>(平均 <b>{price}p</b>/kWh)",
    },
    MessageKey.PRICES_CHEAPEST: {
        Language.EN: "▼ Cheapest: <b>{price}p</b> @ {window}",
        Language.ZH: "▼ 最平:<b>{price}p</b> @ {window}",
    },
    MessageKey.PRICES_MOST_EXPENSIVE: {
        Language.EN: "▲ Most expensive: <b>{price}p</b> @ {window}",
        Language.ZH: "▲ 最貴:<b>{price}p</b> @ {window}",
    },
    MessageKey.PRICES_AVERAGE: {
        Language.EN: "Ø Average: <b>{price}p</b>/kWh",
        Language.ZH: "Ø 平均:<b>{price}p</b>/kWh",
    },
    MessageKey.HEALTH_OK: {
        Language.EN: "✅ <b>HRSE is healthy</b>\nVersion: <code>{version}</code>",
        Language.ZH: "✅ <b>HRSE 運作正常</b>\n版本:<code>{version}</code>",
    },
    MessageKey.LAUNDRY_RECORDED: {
        Language.EN: "🧺 Laundry recorded.\nThis week: <b>{count}</b> completed.",
        Language.ZH: "🧺 已記錄一次洗衫。\n今個星期:完成咗 <b>{count}</b> 次。",
    },
    MessageKey.NO_EVENTS: {
        Language.EN: "📋 No events recorded yet.",
        Language.ZH: "📋 仲未有任何記錄。",
    },
    MessageKey.RECENT_EVENTS_HEADER: {
        Language.EN: "📋 <b>Recent Events</b>",
        Language.ZH: "📋 <b>最近事件</b>",
    },
    MessageKey.WEEKLY_SUMMARY: {
        Language.EN: (
            "🏠 <b>Household Summary</b>\n"
            "Laundry: <b>{laundry_count}</b> completed\n"
            "Last Laundry: {last_laundry}\n"
            "Events This Week: <b>{total_events}</b>"
        ),
        Language.ZH: (
            "🏠 <b>家居摘要</b>\n"
            "洗衫:完成咗 <b>{laundry_count}</b> 次\n"
            "上次洗衫:{last_laundry}\n"
            "今週事件:<b>{total_events}</b>"
        ),
    },
}


def t(key: MessageKey, lang: Language, **kwargs: object) -> str:
    """Return the template for ``key`` in ``lang``, formatted with ``kwargs``.

    Args:
        key:    The message to look up.
        lang:   Target language.
        kwargs: ``str.format`` substitutions expected by the template.

    Returns:
        The formatted message string.
    """
    return _CATALOGUE[key][lang].format(**kwargs)


def bilingual_welcome() -> str:
    """Return the group/chat onboarding welcome message in both languages.

    Sent when the bot joins a chat (or on /start), before a language has
    been chosen — hence deliberately bilingual.
    """
    return (
        "👋 <b>Hello! I'm HRSE</b> — your household scheduling assistant.\n"
        "I watch Octopus Agile electricity prices and the weather, and tell "
        "this chat the best time to run household tasks like laundry.\n"
        "\n"
        "👋 <b>你好!我係 HRSE</b> — 屋企資源調度助手。\n"
        "我會留意 Octopus Agile 電價同天氣,話俾大家知幾時做家務(例如洗衫)最抵。\n"
        "\n"
        + _COMMANDS_EN
        + "\n\n"
        + _COMMANDS_ZH
        + "\n\n"
        + t(MessageKey.LANGUAGE_PROMPT, Language.EN)
    )
