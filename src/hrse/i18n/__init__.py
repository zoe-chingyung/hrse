"""Internationalisation (i18n) for user-facing bot messages.

Pure Python — no AWS imports. See ``hrse.i18n.messages``.
"""

from hrse.i18n.messages import (
    MessageKey,
    bilingual_already_registered,
    bilingual_invite_required,
    bilingual_welcome,
    t,
)

__all__ = [
    "MessageKey",
    "bilingual_already_registered",
    "bilingual_invite_required",
    "bilingual_welcome",
    "t",
]
