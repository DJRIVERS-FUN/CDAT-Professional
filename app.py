#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from cdat.database import Database
from cdat.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("CDAT Professional")
    app.setOrganizationName("Rivers Lab")

    data_dir = Path.home() / ".cdat_professional"
    data_dir.mkdir(parents=True, exist_ok=True)
    database = Database(data_dir / "cdat.db")
    database.initialize()

    window = MainWindow(database)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
