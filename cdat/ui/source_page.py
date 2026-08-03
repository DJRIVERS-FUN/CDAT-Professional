from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cdat.project_manager import Project
from cdat.source_manager import SourceManager, SourceRecord, VALID_SOURCE_TYPES


class PasteUrlsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Paste article URLs")
        self.resize(680, 480)
        layout = QVBoxLayout(self)

        instruction = QLabel("Paste one individual article, thread, transcript or guidance URL per line.")
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        meta = QHBoxLayout()
        self.source_type = QComboBox()
        self.source_type.addItems(sorted(VALID_SOURCE_TYPES))
        self.source_type.setCurrentText("Media")
        meta.addWidget(QLabel("Source type"))
        meta.addWidget(self.source_type)
        meta.addStretch()
        layout.addLayout(meta)

        self.urls = QTextEdit()
        self.urls.setPlaceholderText("https://example.org/article-one\nhttps://example.org/article-two")
        layout.addWidget(self.urls, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Add URLs")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[list[str], str]:
        urls = [line.strip() for line in self.urls.toPlainText().splitlines() if line.strip()]
        return urls, self.source_type.currentText()


class SourcePage(QWidget):
    back_requested = Signal()

    def __init__(self, manager: SourceManager):
        super().__init__()
        self.manager = manager
        self.project: Project | None = None
        self._records: dict[int, SourceRecord] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        top = QHBoxLayout()
        back = QPushButton("← Project")
        back.setObjectName("secondaryButton")
        back.clicked.connect(self.back_requested.emit)
        self.heading = QLabel("Sources and Screening")
        self.heading.setObjectName("pageTitle")
        top.addWidget(back)
        top.addWidget(self.heading)
        top.addStretch()
        layout.addLayout(top)

        self.summary = QLabel("No project selected")
        self.summary.setObjectName("bodyText")
        layout.addWidget(self.summary)

        controls = QHBoxLayout()
        paste = QPushButton("Paste URLs")
        paste.clicked.connect(self.paste_urls)
        import_button = QPushButton("Import CSV")
        import_button.clicked.connect(self.import_csv)
        export_button = QPushButton("Export Manifest")
        export_button.setObjectName("secondaryButton")
        export_button.clicked.connect(self.export_manifest)
        controls.addWidget(paste)
        controls.addWidget(import_button)
        controls.addWidget(export_button)
        controls.addStretch()

        controls.addWidget(QLabel("Show"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Pending", "Include", "Exclude"])
        self.filter_combo.currentTextChanged.connect(self.refresh)
        controls.addWidget(self.filter_combo)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Decision", "Source Type", "Source Name", "Date", "URL", "Notes", "ID"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.setColumnHidden(6, True)
        layout.addWidget(self.table, 1)

        screening = QHBoxLayout()
        include = QPushButton("Include Selected")
        include.clicked.connect(lambda: self.set_decision("Include"))
        exclude = QPushButton("Exclude Selected")
        exclude.setObjectName("secondaryButton")
        exclude.clicked.connect(lambda: self.set_decision("Exclude"))
        pending = QPushButton("Return to Pending")
        pending.setObjectName("secondaryButton")
        pending.clicked.connect(lambda: self.set_decision("Pending"))
        delete = QPushButton("Delete Selected")
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self.delete_selected)
        screening.addWidget(include)
        screening.addWidget(exclude)
        screening.addWidget(pending)
        screening.addStretch()
        screening.addWidget(delete)
        layout.addLayout(screening)

    def load_project(self, project: Project) -> None:
        self.project = project
        self.heading.setText(f"Sources and Screening — {project.title}")
        self.refresh()

    def refresh(self) -> None:
        if not self.project:
            return
        selected_filter = self.filter_combo.currentText()
        decision = None if selected_filter == "All" else selected_filter
        records = self.manager.list_sources(self.project.id, decision)
        self._records = {record.id: record for record in records}
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [
                record.screening_decision,
                record.source_type,
                record.source_name,
                record.publication_date,
                record.url,
                record.notes,
                str(record.id),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 4:
                    item.setToolTip(value)
                self.table.setItem(row, column, item)
        counts = self.manager.counts(self.project.id)
        self.summary.setText(
            f"Total: {counts['Total']}   ·   Pending: {counts['Pending']}   ·   "
            f"Included: {counts['Include']}   ·   Excluded: {counts['Exclude']}"
        )

    def selected_ids(self) -> list[int]:
        ids: list[int] = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 6)
            if item:
                ids.append(int(item.text()))
        return ids

    def paste_urls(self) -> None:
        if not self.project:
            return
        dialog = PasteUrlsDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        urls, source_type = dialog.values()
        if not urls:
            return
        added, skipped = self.manager.add_urls(self.project.id, urls, source_type)
        self.refresh()
        QMessageBox.information(
            self,
            "URLs added",
            f"Added {added} new URLs. Skipped {skipped} invalid URLs. Duplicates were ignored.",
        )

    def import_csv(self) -> None:
        if not self.project:
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Import URL manifest", "", "CSV files (*.csv)")
        if not filename:
            return
        try:
            added, skipped = self.manager.import_csv(self.project.id, Path(filename))
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self.refresh()
        QMessageBox.information(self, "Import complete", f"Added {added} new URLs; skipped {skipped} invalid rows.")

    def export_manifest(self) -> None:
        if not self.project:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export source manifest",
            str(Path(self.project.project_path) / "source_manifest.csv"),
            "CSV files (*.csv)",
        )
        if not filename:
            return
        self.manager.export_manifest(self.project.id, Path(filename))
        QMessageBox.information(self, "Export complete", f"Manifest saved to:\n{filename}")

    def set_decision(self, decision: str) -> None:
        ids = self.selected_ids()
        if not ids:
            QMessageBox.information(self, "Select sources", "Select one or more source rows first.")
            return
        reason = ""
        if decision == "Exclude":
            dialog = QDialog(self)
            dialog.setWindowTitle("Exclusion reason")
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel("Record a brief reason for excluding the selected sources:"))
            reason_edit = QLineEdit()
            reason_edit.setPlaceholderText("e.g., duplicate, irrelevant, outside date range")
            layout.addWidget(reason_edit)
            buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.Accepted:
                return
            reason = reason_edit.text().strip()
        self.manager.set_decision(ids, decision, reason)
        self.refresh()

    def delete_selected(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        answer = QMessageBox.question(
            self,
            "Delete sources",
            f"Permanently delete {len(ids)} selected source record(s)?",
        )
        if answer == QMessageBox.Yes:
            self.manager.delete_sources(ids)
            self.refresh()
