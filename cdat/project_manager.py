from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cdat.database import Database


@dataclass(slots=True)
class Project:
    id: int
    title: str
    research_question: str
    principal_investigator: str
    institution: str
    language: str
    start_date: str
    end_date: str
    project_path: str


class ProjectManager:
    def __init__(self, database: Database):
        self.database = database

    def list_projects(self) -> list[Project]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, title, research_question, principal_investigator, institution, "
                "language, start_date, end_date, project_path "
                "FROM projects ORDER BY last_opened_at DESC, updated_at DESC"
            ).fetchall()
        return [Project(**dict(row)) for row in rows]

    def create_project(
        self,
        *,
        title: str,
        research_question: str,
        principal_investigator: str,
        institution: str,
        language: str,
        start_date: str,
        end_date: str,
        project_path: str,
    ) -> Project:
        path = Path(project_path).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        for folder in ("documents", "exports", "figures", "logs"):
            (path / folder).mkdir(exist_ok=True)

        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO projects (
                    title, research_question, principal_investigator, institution,
                    language, start_date, end_date, project_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title.strip(), research_question.strip(), principal_investigator.strip(),
                    institution.strip(), language.strip() or "English", start_date.strip(),
                    end_date.strip(), str(path),
                ),
            )
            project_id = int(cursor.lastrowid)

        return Project(
            id=project_id,
            title=title.strip(),
            research_question=research_question.strip(),
            principal_investigator=principal_investigator.strip(),
            institution=institution.strip(),
            language=language.strip() or "English",
            start_date=start_date.strip(),
            end_date=end_date.strip(),
            project_path=str(path),
        )

    def delete_project(self, project_id: int) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
