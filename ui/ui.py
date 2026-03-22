from __future__ import annotations

try:
    from .app import CMD_UI
except ImportError:
    from ui.app import CMD_UI


if __name__ == "__main__":
    CMD_UI().run()
