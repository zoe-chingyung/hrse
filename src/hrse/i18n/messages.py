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
    SETUP_INVALID_ANSWER = auto()
    PROFILE_HEADER = auto()
    PROFILE_TASK_BLOCK = auto()
    PROFILE_NONE = auto()
    RESET_DONE = auto()
    TASKS_LIST = auto()
    PRICE_BAR_CHART_TITLE = auto()
    PRICE_BAR_CHART_TITLE_TOMORROW = auto()
    PRICE_BAR_CHART_FOOTER = auto()
    PRICE_BAR_CHART_AVOID_HEADER = auto()
    START_INVITE_REQUIRED = auto()
    START_ALREADY_REGISTERED = auto()
    SETUP_Q_POSTCODE = auto()
    SETUP_REGION_CONFIRMED = auto()
    SETUP_REGION_LOOKUP_FAILED = auto()
    # Sprint C — button-driven onboarding
    SETUP_Q_TASK_SELECT = auto()
    SETUP_TASKS_NONE_SELECTED = auto()
    SETUP_TASKS_LOCKED = auto()
    SETUP_Q_TARGET_RUNS = auto()
    SETUP_Q_DURATION = auto()
    SETUP_Q_BUDGET = auto()
    SETUP_Q_EARLIEST = auto()
    SETUP_Q_LATEST = auto()
    SETUP_Q_OUTDOOR_DRYING = auto()
    SETUP_Q_MIN_UV = auto()
    SETUP_Q_MAX_RAIN = auto()
    SETUP_Q_TIMEZONE = auto()
    SETUP_Q_EV_DURATION = auto()
    SETUP_TYPE_YOUR_ANSWER = auto()
    SETUP_OPTION_CONFIRMED = auto()
    SETUP_USE_BUTTONS_HINT = auto()
    SETUP_COMPLETE_SUMMARY = auto()


_COMMANDS_EN = (
    "📋 <b>Commands</b>\n"
    "/prices — today's Agile electricity prices\n"
    "/prices_tomorrow — tomorrow's prices\n"
    "/laundry_done — record a laundry run\n"
    "/summary — weekly household summary\n"
    "/events — recent events\n"
    "/profile — show your current settings\n"
    "/tasks — list your active tasks\n"
    "/reset — clear your settings and redo setup\n"
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
    "/profile — 查看你而家嘅設定\n"
    "/tasks — 查看你已啟用嘅任務\n"
    "/reset — 清除你嘅設定並重新設定\n"
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
    MessageKey.SETUP_INVALID_ANSWER: {
        Language.EN: "⚠️ Didn't understand that — please try again.",
        Language.ZH: "⚠️ 唔明你個答案,請再試一次。",
    },
    MessageKey.PROFILE_HEADER: {
        Language.EN: "⚙️ <b>Your Settings</b>{blocks}\n\nUse /reset to clear everything and start over.",
        Language.ZH: "⚙️ <b>你嘅設定</b>{blocks}\n\n用 /reset 清除晒重新開始。",
    },
    MessageKey.PROFILE_TASK_BLOCK: {
        Language.EN: (
            "\n\n<b>{task}</b>\n"
            "Target: {target}/week\n"
            "Duration: {duration}\n"
            "Window: {earliest}–{latest}\n"
            "Budget: {budget}p\n"
            "Weather-aware: {weather}"
        ),
        Language.ZH: (
            "\n\n<b>{task}</b>\n"
            "目標:每星期 {target} 次\n"
            "時長:{duration}\n"
            "時段:{earliest}–{latest}\n"
            "預算:{budget}p\n"
            "睇天氣:{weather}"
        ),
    },
    MessageKey.PROFILE_NONE: {
        Language.EN: "⚙️ No tasks configured yet. Run /reset to start setup.",
        Language.ZH: "⚙️ 未有任何已設定嘅任務。用 /reset 開始設定。",
    },
    MessageKey.RESET_DONE: {
        Language.EN: "🔄 Your settings have been cleared. Let's set up again.",
        Language.ZH: "🔄 你嘅設定已經清除,我哋再設定一次。",
    },
    MessageKey.TASKS_LIST: {
        Language.EN: "📋 <b>Your Active Tasks</b>\n{tasks}",
        Language.ZH: "📋 <b>你已啟用嘅任務</b>\n{tasks}",
    },
    MessageKey.PRICE_BAR_CHART_TITLE: {
        Language.EN: "⚡ Today's prices",
        Language.ZH: "⚡ 今日電價走勢",
    },
    MessageKey.PRICE_BAR_CHART_TITLE_TOMORROW: {
        Language.EN: "⚡ Tomorrow's prices",
        Language.ZH: "⚡ 聽日電價走勢",
    },
    MessageKey.PRICE_BAR_CHART_FOOTER: {
        Language.EN: "✅ Best wash time: from {time}",
        Language.ZH: "✅ 最抵洗衫時間:由 {time} 開始",
    },
    MessageKey.PRICE_BAR_CHART_AVOID_HEADER: {
        Language.EN: "⚠️ Avoid heavy use (priciest slots):",
        Language.ZH: "⚠️ 避免大量用電(最貴時段):",
    },
    MessageKey.START_INVITE_REQUIRED: {
        Language.EN: (
            "🔒 This bot is invite-only.\n"
            "Ask the owner for your invite code, then run <code>/start &lt;code&gt;</code>."
        ),
        Language.ZH: "🔒 呢個機械人淨係限邀請登記。\n請問管理員攞邀請碼,然後執行 <code>/start &lt;code&gt;</code>。",
    },
    MessageKey.START_ALREADY_REGISTERED: {
        Language.EN: "✅ You're already set up. Use /reset if you want to start over.",
        Language.ZH: "✅ 你已經設定咗。想重新開始就用 /reset。",
    },
    MessageKey.SETUP_Q_POSTCODE: {
        Language.EN: (
            "🛠 <b>Setup</b>\n"
            "What's your postcode? I'll use it to find your electricity "
            "pricing region (e.g. <code>SW1A 1AA</code>)."
        ),
        Language.ZH: (
            "🛠 <b>設定</b>\n" "你嘅郵政編號係?我會用嚟搵你嘅電價地區(例如 <code>SW1A 1AA</code>)。"
        ),
    },
    MessageKey.SETUP_REGION_CONFIRMED: {
        Language.EN: "📍 Region set to <b>{region}</b>.",
        Language.ZH: "📍 地區已設定為 <b>{region}</b>。",
    },
    MessageKey.SETUP_REGION_LOOKUP_FAILED: {
        Language.EN: (
            "⚠️ Couldn't find that postcode. Pick your region below, or "
            "try entering the postcode again."
        ),
        Language.ZH: "⚠️ 搵唔到呢個郵政編號。喺下面揀返你嘅地區,或者再輸入一次郵政編號。",
    },
    MessageKey.SETUP_Q_TASK_SELECT: {
        Language.EN: (
            "🛠 <b>Setup</b>\n"
            "Which tasks do you want recommendations for? Tap to select, then Done."
        ),
        Language.ZH: "🛠 <b>設定</b>\n你想要邊啲任務嘅建議?揀完撳「完成」。",
    },
    MessageKey.SETUP_TASKS_NONE_SELECTED: {
        Language.EN: "⚠️ Pick at least one task before continuing.",
        Language.ZH: "⚠️ 揀最少一個任務先可以繼續。",
    },
    MessageKey.SETUP_TASKS_LOCKED: {
        Language.EN: "✅ Tasks selected: {tasks}",
        Language.ZH: "✅ 已揀任務:{tasks}",
    },
    MessageKey.SETUP_Q_TARGET_RUNS: {
        Language.EN: "🛠 <b>{task} setup ({step}/{total})</b>\nHow many times per week?",
        Language.ZH: "🛠 <b>{task} 設定 ({step}/{total})</b>\n每星期想要幾多次?",
    },
    MessageKey.SETUP_Q_DURATION: {
        Language.EN: (
            "🛠 <b>{task} setup ({step}/{total})</b>\n"
            "How long does one run take? (Other: type a number of 30-min "
            "slots, e.g. <code>4</code> = 2h)"
        ),
        Language.ZH: (
            "🛠 <b>{task} 設定 ({step}/{total})</b>\n"
            "一次要用幾耐?(其他:輸入 30 分鐘為單位嘅格數,例如 <code>4</code> = 2 小時)"
        ),
    },
    MessageKey.SETUP_Q_BUDGET: {
        Language.EN: "🛠 <b>{task} setup ({step}/{total})</b>\nMax budget per run, in pence?",
        Language.ZH: "🛠 <b>{task} 設定 ({step}/{total})</b>\n每次嘅預算上限,幾多便士?",
    },
    MessageKey.SETUP_Q_EARLIEST: {
        Language.EN: "🛠 <b>{task} setup ({step}/{total})</b>\nEarliest time a run can start?",
        Language.ZH: "🛠 <b>{task} 設定 ({step}/{total})</b>\n最早幾點可以開始?",
    },
    MessageKey.SETUP_Q_LATEST: {
        Language.EN: "🛠 <b>{task} setup ({step}/{total})</b>\nLatest time a run must finish by?",
        Language.ZH: "🛠 <b>{task} 設定 ({step}/{total})</b>\n最遲幾點要完成?",
    },
    MessageKey.SETUP_Q_OUTDOOR_DRYING: {
        Language.EN: "🛠 <b>{task} setup ({step}/{total})</b>\nDo you dry laundry outdoors?",
        Language.ZH: "🛠 <b>{task} 設定 ({step}/{total})</b>\n你係咪喺室外晾衫?",
    },
    MessageKey.SETUP_Q_MIN_UV: {
        Language.EN: (
            "🛠 <b>{task} setup ({step}/{total})</b>\n"
            "Minimum UV index to recommend a run? (only above this)"
        ),
        Language.ZH: "🛠 <b>{task} 設定 ({step}/{total})</b>\nUV 指數要高過幾多先建議?",
    },
    MessageKey.SETUP_Q_MAX_RAIN: {
        Language.EN: "🛠 <b>{task} setup ({step}/{total})</b>\nMax acceptable rain probability?",
        Language.ZH: "🛠 <b>{task} 設定 ({step}/{total})</b>\n最高可以接受幾多% 落雨機率?",
    },
    MessageKey.SETUP_Q_TIMEZONE: {
        Language.EN: "🛠 <b>{task} setup ({step}/{total})</b>\nYour IANA timezone?",
        Language.ZH: "🛠 <b>{task} 設定 ({step}/{total})</b>\n你嘅 IANA 時區?",
    },
    MessageKey.SETUP_Q_EV_DURATION: {
        Language.EN: (
            "🛠 <b>{task} setup</b>\n"
            "How long do you want to charge for? I'll find the cheapest "
            "contiguous window of that length."
        ),
        Language.ZH: "🛠 <b>{task} 設定</b>\n想充幾耐?我會搵嗰段長度入面最平嘅連續時段。",
    },
    MessageKey.SETUP_TYPE_YOUR_ANSWER: {
        Language.EN: "✏️ Type your answer below:",
        Language.ZH: "✏️ 喺下面打你嘅答案:",
    },
    MessageKey.SETUP_OPTION_CONFIRMED: {
        Language.EN: "✅ {label}",
        Language.ZH: "✅ {label}",
    },
    MessageKey.SETUP_USE_BUTTONS_HINT: {
        Language.EN: "🔘 Please use the buttons above to continue setup.",
        Language.ZH: "🔘 請用返上面嘅按鈕繼續設定。",
    },
    MessageKey.SETUP_COMPLETE_SUMMARY: {
        Language.EN: (
            "✅ <b>Setup complete!</b>\n"
            "Your tasks: {tasks}\n\n"
            "📅 You'll get a plan around 16:45 UTC each day, and a reminder "
            "around 08:00 UTC. Run /profile to review, /reset to start over."
        ),
        Language.ZH: (
            "✅ <b>設定完成!</b>\n"
            "你嘅任務:{tasks}\n\n"
            "📅 每日大約 UTC 16:45 會收到計劃,UTC 08:00 會有提示。"
            "用 /profile 睇返設定,/reset 可以重新開始。"
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


def bilingual_invite_required() -> str:
    """Return the invite-only rejection message in both languages.

    Sent when /start is run with a missing or incorrect invite code, before
    any language has been chosen for the chat — hence bilingual.
    """
    return (
        t(MessageKey.START_INVITE_REQUIRED, Language.EN)
        + "\n\n"
        + t(MessageKey.START_INVITE_REQUIRED, Language.ZH)
    )


def bilingual_already_registered() -> str:
    """Return the already-registered notice in both languages.

    Sent when /start is re-run by a chat that has already completed
    onboarding, so its saved profile isn't silently wiped.
    """
    return (
        t(MessageKey.START_ALREADY_REGISTERED, Language.EN)
        + "\n\n"
        + t(MessageKey.START_ALREADY_REGISTERED, Language.ZH)
    )
