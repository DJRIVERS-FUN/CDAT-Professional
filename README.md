# CDAT Professional

CDAT Professional is a desktop research platform developed in the Rivers Lab to support transparent, reproducible and AI-enhanced computational discourse analysis.

## Current milestone: v0.1-dev

The first milestone provides:

- a native PySide6 desktop application;
- SQLite-backed project management;
- new, open and delete project workflows;
- recent-project navigation;
- structured project folders for documents, exports, figures and logs.

Corpus discovery, screening, annotation, validation, statistical analysis and publication export will be added in later milestones.

## macOS installation

```bash
git clone https://github.com/DJRIVERS-FUN/CDAT-Professional.git
cd CDAT-Professional
git checkout develop
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 app.py
```

Alternatively, after the first installation, run:

```bash
./run_cdat.command
```

If macOS blocks the launcher, right-click it and select **Open**, or run:

```bash
chmod +x run_cdat.command
xattr -d com.apple.quarantine run_cdat.command
./run_cdat.command
```

## Data storage

The application registry is stored locally at:

```text
~/.cdat_professional/cdat.db
```

Research data remain inside the project folder chosen by the researcher. Deleting a project record does not delete the project folder or research files.
