"""EventStore Protocol — the only storage contract the application depends on.

Any class that implements ``append_event`` and ``list_events`` with the
correct signatures satisfies this Protocol, without inheritance.
This makes it trivial to substitute a different backend (local
file, in-memory stub) by passing a different object at construction time.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hrse.models.events import Event  # noqa: TCH001 — used in Protocol method signatures at runtime


@runtime_checkable
class EventStore(Protocol):
    """Structural contract for an append-only event store."""

    def append_event(self, event: Event) -> None:
        """Persist a new event.

        Args:
            event: The event to store.
        """
        ...

    def list_events(self) -> list[Event]:
        """Return all stored events, oldest first.

        Returns:
            A list of ``Event`` objects in insertion order.
            Returns an empty list when the store is empty.
        """
        ...
