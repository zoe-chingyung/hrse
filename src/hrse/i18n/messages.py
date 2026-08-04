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
    SETUP_Q_LAUNDRY_TARGET = auto()
    SETUP_Q_EARLIEST_START = auto()
    SETUP_Q_LATEST_FINISH = auto()
    SETUP_Q_OUTDOOR_DRYING = auto()
    SETUP_Q_TIMEZONE = auto()
    SETUP_Q_WASH_BUDGET = auto()
    SETUP_INVALID_ANSWER = auto()
    SETUP_DONE = auto()
    PROFILE_HEADER = auto()
    PROFILE_NONE = auto()
    RESET_DONE = auto()
    TASKS_LIST = auto()
    TASK_USAGE_ADD = auto()
    TASK_USAGE_REMOVE = auto()
    TASK_UNKNOWN = auto()
    TASK_ALREADY_ENABLED = auto()
    TASK_ADDED = auto()
    TASK_NOT_ENABLED = auto()
    TASK_REMOVED = auto()
    PRICE_BAR_CHART_TITLE = auto()
    PRICE_BAR_CHART_FOOTER = auto()


_COMMANDS_EN = (
    "📋 <b>Commands</b>\n"
    "/prices — today's Agile electricity prices\n"
    "/prices_tomorrow — tomorrow's prices\n"
    "/laundry_done — record a laundry run\n"
    "/summary — weekly household summary\n"
    "/events — recent events\n"
    "/setup — configure your laundry preferences\n"
    "/profile — show your current settings\n"
    "/reset — clear your settings (use global defaults)\n"
    "/tasks — list your active tasks\n"
    "/add_task — enable a task (laundry, dishwasher, ev)\n"
    "/remove_task — disable a task\n"
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
    "/setup — 設定你嘅洗衫偏好\n"
    "/profile — 查看你而家嘅設定\n"
    "/reset — 清除你嘅設定(用返預設值)\n"
    "/tasks — 查看你已啟用嘅任務\n"
    "/add_task — 啟用任務(laundry、dishwasher、ev)\n"
    "/remove_task — 停用任務\n"
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
    MessageKey.SETUP_Q_LAUNDRY_TARGET: {
        Language.EN: (
            "🛠 <b>Setup ({step}/{total})</b>\n"
            "How many laundry runs per week do you want? (e.g. <code>2</code>)"
        ),
        Language.ZH: (
            "🛠 <b>設定 ({step}/{total})</b>\n" "你想每星期洗幾多次衫?(例如 <code>2</code>)"
        ),
    },
    MessageKey.SETUP_Q_EARLIEST_START: {
        Language.EN: (
            "🛠 <b>Setup ({step}/{total})</b>\n"
            "Earliest time a run can start? 24h <code>HH:MM</code> (e.g. <code>08:00</code>)"
        ),
        Language.ZH: (
            "🛠 <b>設定 ({step}/{total})</b>\n"
            "最早幾點可以開始洗?24小時制 <code>HH:MM</code>(例如 <code>08:00</code>)"
        ),
    },
    MessageKey.SETUP_Q_LATEST_FINISH: {
        Language.EN: (
            "🛠 <b>Setup ({step}/{total})</b>\n"
            "Latest time a run must finish by? 24h <code>HH:MM</code> (e.g. <code>22:00</code>)"
        ),
        Language.ZH: (
            "🛠 <b>設定 ({step}/{total})</b>\n"
            "最遲幾點要洗完?24小時制 <code>HH:MM</code>(例如 <code>22:00</code>)"
        ),
    },
    MessageKey.SETUP_Q_OUTDOOR_DRYING: {
        Language.EN: (
            "🛠 <b>Setup ({step}/{total})</b>\n"
            "Do you dry laundry outdoors? Reply <code>yes</code> or <code>no</code>"
        ),
        Language.ZH: (
            "🛠 <b>設定 ({step}/{total})</b>\n"
            "你係咪喺室外晾衫?回覆 <code>yes</code> 或 <code>no</code>"
        ),
    },
    MessageKey.SETUP_Q_TIMEZONE: {
        Language.EN: (
            "🛠 <b>Setup ({step}/{total})</b>\n"
            "Your IANA timezone? (e.g. <code>Europe/London</code>)"
        ),
        Language.ZH: (
            "🛠 <b>設定 ({step}/{total})</b>\n" "你嘅 IANA 時區?(例如 <code>Europe/London</code>)"
        ),
    },
    MessageKey.SETUP_Q_WASH_BUDGET: {
        Language.EN: (
            "🛠 <b>Setup ({step}/{total})</b>\n"
            "Max budget per wash, in pence? (e.g. <code>40</code>)"
        ),
        Language.ZH: (
            "🛠 <b>設定 ({step}/{total})</b>\n" "每次洗衫嘅預算上限,幾多便士?(例如 <code>40</code>)"
        ),
    },
    MessageKey.SETUP_INVALID_ANSWER: {
        Language.EN: "⚠️ Didn't understand that — please try again.",
        Language.ZH: "⚠️ 唔明你個答案,請再試一次。",
    },
    MessageKey.SETUP_DONE: {
        Language.EN: "✅ <b>Setup complete!</b> Run /profile to see your settings.",
        Language.ZH: "✅ <b>設定完成!</b>用 /profile 睇返你嘅設定。",
    },
    MessageKey.PROFILE_HEADER: {
        Language.EN: (
            "⚙️ <b>Your Settings</b>\n"
            "Laundry target: <b>{target}</b>/week\n"
            "Window: {earliest}–{latest}\n"
            "Budget: <b>{budget}p</b>/wash\n"
            "Outdoor drying: {outdoor}\n"
            "Timezone: {timezone}\n\n"
            "Use /reset to clear these and use global defaults."
        ),
        Language.ZH: (
            "⚙️ <b>你嘅設定</b>\n"
            "洗衫目標:每星期 <b>{target}</b> 次\n"
            "時段:{earliest}–{latest}\n"
            "預算:每次 <b>{budget}p</b>\n"
            "室外晾衫:{outdoor}\n"
            "時區:{timezone}\n\n"
            "用 /reset 清除呢啲設定,改用全域預設值。"
        ),
    },
    MessageKey.PROFILE_NONE: {
        Language.EN: "⚙️ No personal settings yet — using global defaults.\nRun /setup to configure.",
        Language.ZH: "⚙️ 未有個人設定,而家用緊全域預設值。\n用 /setup 開始設定。",
    },
    MessageKey.RESET_DONE: {
        Language.EN: "🔄 Your settings have been cleared. Using global defaults now.",
        Language.ZH: "🔄 你嘅設定已經清除,而家用緊全域預設值。",
    },
    MessageKey.TASKS_LIST: {
        Language.EN: "📋 <b>Your Active Tasks</b>\n{tasks}",
        Language.ZH: "📋 <b>你已啟用嘅任務</b>\n{tasks}",
    },
    MessageKey.TASK_USAGE_ADD: {
        Language.EN: "Usage: <code>/add_task laundry|dishwasher|ev</code>",
        Language.ZH: "用法:<code>/add_task laundry|dishwasher|ev</code>",
    },
    MessageKey.TASK_USAGE_REMOVE: {
        Language.EN: "Usage: <code>/remove_task laundry|dishwasher|ev</code>",
        Language.ZH: "用法:<code>/remove_task laundry|dishwasher|ev</code>",
    },
    MessageKey.TASK_UNKNOWN: {
        Language.EN: "⚠️ Unknown task <code>{task}</code>. Valid: {valid}",
        Language.ZH: "⚠️ 未知任務 <code>{task}</code>。可用:{valid}",
    },
    MessageKey.TASK_ALREADY_ENABLED: {
        Language.EN: "{task} is already enabled.",
        Language.ZH: "{task} 已經啟用咗。",
    },
    MessageKey.TASK_ADDED: {
        Language.EN: "✅ {task} enabled.",
        Language.ZH: "✅ {task} 已啟用。",
    },
    MessageKey.TASK_NOT_ENABLED: {
        Language.EN: "{task} isn't enabled.",
        Language.ZH: "{task} 未啟用。",
    },
    MessageKey.TASK_REMOVED: {
        Language.EN: "❌ {task} disabled.",
        Language.ZH: "❌ {task} 已停用。",
    },
    MessageKey.PRICE_BAR_CHART_TITLE: {
        Language.EN: "⚡ Today's prices",
        Language.ZH: "⚡ 今日電價走勢",
    },
    MessageKey.PRICE_BAR_CHART_FOOTER: {
        Language.EN: "✅ Best wash time: from {time}",
        Language.ZH: "✅ 最抵洗衫時間:由 {time} 開始",
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
