"""
history.py — persistent opportunity age tracking and watchlist.

Stores first-seen timestamps and watched keys in ~/.arb_tool/.
All I/O is fire-and-forget; exceptions are silently swallowed so the
main UI never crashes due to disk issues.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("arb_tool.history")

DATA_DIR = Path.home() / ".arb_tool"
_HISTORY_FILE  = DATA_DIR / "history.json"
_WATCHLIST_FILE = DATA_DIR / "watchlist.json"

# Hard limit on history entries to prevent unbounded file growth
_MAX_HISTORY = 3_000


class OppHistory:
    """Persist first-seen timestamps and watchlist entries across sessions."""

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._history:   dict[str, str] = {}  # key → ISO first-seen timestamp
        self._watchlist: set[str]       = set()
        self._load()

    # ── Private I/O ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if _HISTORY_FILE.exists():
                self._history = json.loads(_HISTORY_FILE.read_text())
        except Exception as exc:
            log.warning("Could not load history: %s", exc)
            self._history = {}

        try:
            if _WATCHLIST_FILE.exists():
                self._watchlist = set(json.loads(_WATCHLIST_FILE.read_text()))
        except Exception as exc:
            log.warning("Could not load watchlist: %s", exc)
            self._watchlist = set()

    def _save_history(self) -> None:
        try:
            if len(self._history) > _MAX_HISTORY:
                items = sorted(self._history.items(), key=lambda x: x[1])
                self._history = dict(items[-_MAX_HISTORY:])
            _HISTORY_FILE.write_text(json.dumps(self._history, indent=None))
        except Exception as exc:
            log.debug("Could not save history: %s", exc)

    def _save_watchlist(self) -> None:
        try:
            _WATCHLIST_FILE.write_text(json.dumps(sorted(self._watchlist)))
        except Exception as exc:
            log.debug("Could not save watchlist: %s", exc)

    # ── History API ───────────────────────────────────────────────────────────

    def record(self, key: str) -> bool:
        """Mark key as first-seen now. Returns True if it was genuinely new."""
        if key not in self._history:
            self._history[key] = datetime.now().isoformat()
            self._save_history()
            return True
        return False

    def first_seen(self, key: str) -> Optional[datetime]:
        raw = self._history.get(key)
        if raw:
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                pass
        return None

    def age_str(self, key: str) -> str:
        """Return compact human-readable age: 'new', '5m', '3h', '2d'. Empty if unknown."""
        ts = self.first_seen(key)
        if ts is None:
            return ""
        secs = (datetime.now() - ts).total_seconds()
        if secs < 90:
            return "new"
        if secs < 3_600:
            return f"{int(secs / 60)}m"
        if secs < 86_400:
            return f"{int(secs / 3_600)}h"
        return f"{int(secs / 86_400)}d"

    def prune_stale(self, active_keys: set[str], keep_days: int = 7) -> int:
        """Remove history entries older than keep_days that are no longer active.
        Returns number of pruned entries.
        """
        cutoff = (datetime.now()).timestamp() - keep_days * 86_400
        to_remove = [
            k for k, ts in self._history.items()
            if k not in active_keys
            and datetime.fromisoformat(ts).timestamp() < cutoff
        ]
        for k in to_remove:
            del self._history[k]
        if to_remove:
            self._save_history()
        return len(to_remove)

    # ── Watchlist API ─────────────────────────────────────────────────────────

    def is_watched(self, key: str) -> bool:
        return key in self._watchlist

    def toggle_watch(self, key: str) -> bool:
        """Toggle watch state. Returns True if the key is now watched."""
        if key in self._watchlist:
            self._watchlist.discard(key)
        else:
            self._watchlist.add(key)
        self._save_watchlist()
        return key in self._watchlist

    @property
    def watched_count(self) -> int:
        return len(self._watchlist)
