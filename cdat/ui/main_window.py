from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cdat.database import Database
from cdat.project_manager import Project, ProjectManager
from cdat.source_manager import SourceManager
from cdat.ui.source_page import SourcePage


class MainWindow(QMainWindow):
    def __init__(self, database: Database):
        super().__init__()
        self.manager = ProjectManager(database)
        self.source_manager = SourceManager(database)
        self.current_project: Project | None = None
        self.setWindowTitle("CDAT Professional")
        self.resize(1240, 800)
        self.setMinimumSize(1000, 680)
        self._build_menu()
        self._build_ui()
        self._apply_style()
        self.refresh_projects()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("New Project", self.show_new_project)
        file_menu.addAction("Open Selected Project", self.open_selected_project)
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close)

        project_menu = self.menuBar().addMenu("Project")
        project_menu.addAction("Sources and Screening", self.show_sources)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("About CDAT Professional", self.show_about)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("Computational Discourse Analysis Toolkit")
        title.setObjectName("appTitle")
        subtitle = QLabel("Transparent, reproducible and AI-enhanced discourse research")
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 10, 0)
        section = QLabel("Recent Projects")
        section.setObjectName("sectionTitle")
        left_layout.addWidget(section)
        self.project_list = QListWidget()
        self.project_list.itemDoubleClicked.connect(lambda _: self.open_selected_project())
        left_layout.addWidget(self.project_list, 1)

        button_row = QHBoxLayout()
        new_button = QPushButton("New Project")
        new_button.clicked.connect(self.show_new_project)
        open_button = QPushButton("Open")
        open_button.clicked.connect(self.open_selected_project)
        delete_button = QPushButton("Delete")
        delete_button.setObjectName("secondaryButton")
        delete_button.clicked.connect(self.delete_selected_project)
        button_row.addWidget(new_button)
        button_row.addWidget(open_button)
        button_row.addWidget(delete_button)
        left_layout.addLayout(button_row)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._welcome_page())
        self.pages.addWidget(self._new_project_page())
        self.pages.addWidget(self._project_page())
        self.source_page = SourcePage(self.source_manager)
        self.source_page.back_requested.connect(self.show_current_project)
        self.pages.addWidget(self.source_page)

        splitter.addWidget(left)
        splitter.addWidget(self.pages)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        self.setCentralWidget(root)
        status = QStatusBar()
        status.showMessage("Ready")
        self.setStatusBar(status)

    def _welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        heading = QLabel("Welcome to CDAT Professional")
        heading.setObjectName("pageTitle")
        body = QLabel(
            "Create a new research project or open an existing project to begin building, "
            "screening, annotating and analysing a discourse corpus."
        )
        body.setWordWrap(True)
        body.setObjectName("bodyText")
        create = QPushButton("Create New Project")
        create.clicked.connect(self.show_new_project)
        create.setMaximumWidth(220)
        layout.addWidget(heading)
        layout.addWidget(body)
        layout.addSpacing(12)
        layout.addWidget(create)
        layout.addStretch()
        return page

    def _new_project_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 20)
        heading = QLabel("New Project")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(12)
        self.title_edit = QLineEdit()
        self.question_edit = QTextEdit()
        self.question_edit.setMaximumHeight(90)
        self.pi_edit = QLineEdit("Damian Rivers")
        self.institution_edit = QLineEdit("Future University Hakodate")
        self.language_edit = QLineEdit("English")
        self.start_edit = QLineEdit("2018-01-01")
        self.end_edit = QLineEdit("2026-12-31")
        self.path_edit = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.choose_project_path)
        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(browse)

        form.addRow("Project title", self.title_edit)
        form.addRow("Research question", self.question_edit)
        form.addRow("Principal investigator", self.pi_edit)
        form.addRow("Institution", self.institution_edit)
        form.addRow("Language", self.language_edit)
        form.addRow("Start date", self.start_edit)
        form.addRow("End date", self.end_edit)
        form.addRow("Project folder", path_row)
        layout.addLayout(form)

        actions = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        create = QPushButton("Create Project")
        create.clicked.connect(self.create_project)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(create)
        layout.addLayout(actions)
        layout.addStretch()
        return page

    def _project_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        self.project_title = QLabel("Project")
        self.project_title.setObjectName("pageTitle")
        self.project_summary = QLabel()
        self.project_summary.setWordWrap(True)
        self.project_summary.setObjectName("bodyText")
        layout.addWidget(self.project_title)
        layout.addWidget(self.project_summary)
        layout.addSpacing(18)

        source_panel = QWidget()
        source_panel.setObjectName("card")
        source_layout = QVBoxLayout(source_panel)
        source_heading = QLabel("1. Sources and Screening")
        source_heading.setObjectName("sectionTitle")
        source_description = QLabel(
            "Add article URLs, import flexible CSV manifests, screen candidate documents, "
            "record inclusion decisions and export a reproducible source manifest."
        )
        source_description.setWordWrap(True)
        source_description.setObjectName("bodyText")
        source_button = QPushButton("Open Sources and Screening")
        source_button.setMaximumWidth(250)
        source_button.clicked.connect(self.show_sources)
        source_layout.addWidget(source_heading)
        source_layout.addWidget(source_description)
        source_layout.addWidget(source_button)
        layout.addWidget(source_panel)

        placeholder = QLabel(
            "Corpus collection, annotation, validation, statistical analysis and publication export "
            "will be added in subsequent milestones."
        )
        placeholder.setWordWrap(True)
        placeholder.setObjectName("panel")
        layout.addWidget(placeholder)
        layout.addStretch()
        return page

    def refresh_projects(self) -> None:
        self.project_list.clear()
        for project in self.manager.list_projects():
            item = QListWidgetItem(project.title)
            item.setData(Qt.UserRole, project)
            item.setToolTip(project.project_path)
            self.project_list.addItem(item)

    def show_new_project(self) -> None:
        self.pages.setCurrentIndex(1)
        self.title_edit.setFocus()

    def choose_project_path(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose project folder")
        if path:
            self.path_edit.setText(path)

    def create_project(self) -> None:
        title = self.title_edit.text().strip()
        path = self.path_edit.text().strip()
        if not title or not path:
            QMessageBox.warning(self, "Missing information", "Project title and folder are required.")
            return
        try:
            project = self.manager.create_project(
                title=title,
                research_question=self.question_edit.toPlainText(),
                principal_investigator=self.pi_edit.text(),
                institution=self.institution_edit.text(),
                language=self.language_edit.text(),
                start_date=self.start_edit.text(),
                end_date=self.end_edit.text(),
                project_path=path,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Project creation failed", str(exc))
            return
        self.refresh_projects()
        self.open_project(project)
        self.statusBar().showMessage(f"Created project: {project.title}", 5000)

    def selected_project(self) -> Project | None:
        item = self.project_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def open_selected_project(self) -> None:
        project = self.selected_project()
        if not project:
            QMessageBox.information(self, "Select a project", "Choose a project from the list first.")
            return
        self.open_project(project)

    def open_project(self, project: Project) -> None:
        self.current_project = project
        self.project_title.setText(project.title)
        question = project.research_question or "No research question recorded."
        self.project_summary.setText(
            f"{question}\n\nPrincipal investigator: {project.principal_investigator or 'Not specified'}\n"
            f"Institution: {project.institution or 'Not specified'}\n"
            f"Study period: {project.start_date or '—'} to {project.end_date or '—'}\n"
            f"Project folder: {project.project_path}"
        )
        self.pages.setCurrentIndex(2)
        self.statusBar().showMessage(f"Opened project: {project.title}", 5000)

    def show_current_project(self) -> None:
        if self.current_project:
            self.pages.setCurrentIndex(2)
        else:
            self.pages.setCurrentIndex(0)

    def show_sources(self) -> None:
        if not self.current_project:
            QMessageBox.information(self, "Open a project", "Open or create a project first.")
            return
        self.source_page.load_project(self.current_project)
        self.pages.setCurrentIndex(3)
        self.statusBar().showMessage("Sources and screening", 3000)

    def delete_selected_project(self) -> None:
        project = self.selected_project()
        if not project:
            return
        answer = QMessageBox.question(
            self,
            "Delete project record",
            f"Delete the CDAT record for '{project.title}'?\n\nThe project folder and research files will not be deleted.",
        )
        if answer == QMessageBox.Yes:
            self.manager.delete_project(project.id)
            self.current_project = None
            self.refresh_projects()
            self.pages.setCurrentIndex(0)
            self.statusBar().showMessage("Project record deleted", 5000)

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About CDAT Professional",
            "CDAT Professional v0.2-dev\n\nDeveloped in the Rivers Lab to support transparent, "
            "reproducible and AI-enhanced computational discourse research.",
        )

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f6f7f9; color: #1f2933; font-size: 14px; }
            QLabel#appTitle { font-size: 27px; font-weight: 700; }
            QLabel#subtitle { color: #667085; font-size: 14px; }
            QLabel#sectionTitle, QLabel#pageTitle { font-size: 19px; font-weight: 650; }
            QLabel#bodyText { color: #475467; }
            QLabel#panel, QWidget#card { background: white; border: 1px solid #d8dde5; border-radius: 8px; padding: 18px; }
            QListWidget, QLineEdit, QTextEdit, QTableWidget, QComboBox {
                background: white; border: 1px solid #cfd6df; border-radius: 6px; padding: 7px;
            }
            QListWidget::item { padding: 10px; }
            QListWidget::item:selected, QTableWidget::item:selected { background: #dbeafe; color: #1e3a5f; }
            QPushButton { background: #2457a6; color: white; border: 0; border-radius: 6px; padding: 9px 15px; font-weight: 600; }
            QPushButton:hover { background: #1d4b90; }
            QPushButton#secondaryButton { background: #e8ebf0; color: #344054; }
            QPushButton#secondaryButton:hover { background: #dce1e8; }
            QPushButton#dangerButton { background: #b42318; color: white; }
            QPushButton#dangerButton:hover { background: #912018; }
            QHeaderView::section { background: #eef1f5; padding: 7px; border: 0; border-bottom: 1px solid #cfd6df; font-weight: 600; }
            QStatusBar { background: white; border-top: 1px solid #d8dde5; }
            """
        )
