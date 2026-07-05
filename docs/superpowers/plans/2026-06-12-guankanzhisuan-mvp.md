# 管勘智算 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web app that fills blank unit prices in a standard Excel file from the local two-dimensional knowledge database and exports a filled Excel plus a Word report.

**Architecture:** FastAPI owns file upload, matching, Excel writing, report generation, and downloadable artifacts. React/Vite owns a compact desktop-style upload and result dashboard. The matching path is deterministic: normalize `要素1` through `要素5` plus `单位`, match against the local Excel knowledge base, and only use LLMs later for explanation/report polishing.

**Tech Stack:** Python, FastAPI, openpyxl, python-docx, pytest, React, TypeScript, Vite, lucide-react.

---

### Task 1: Project Context

**Files:**
- Create: `README.md`
- Create: `AGENTS.md`
- Create: `CHANGELOG.md`

- [x] **Step 1: Document the project purpose**

Record the project name, data files, target workflow, architecture decision, and validation method.

- [x] **Step 2: Document project-specific operating rules**

Keep raw Excel files unchanged, write generated artifacts under runtime output folders, and validate with the 100-row answer workbook.

### Task 2: Backend Matching Core

**Files:**
- Create: `backend/app/normalization.py`
- Create: `backend/app/knowledge_base.py`
- Create: `backend/app/fill_engine.py`
- Create: `backend/tests/test_matching.py`

- [x] **Step 1: Write failing tests**

Test full-row exact matching, full-width/half-width punctuation normalization, and end-to-end comparison against the provided answer workbook.

- [x] **Step 2: Implement normalization**

Normalize whitespace, Chinese parentheses, empty values, scale prefixes, and common punctuation differences.

- [x] **Step 3: Implement knowledge index and fill engine**

Load B-G as key fields and H as price. Fill rows whose price cell is blank or contains `空单价`.

### Task 3: API And Report Generation

**Files:**
- Create: `backend/app/report.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_api.py`
- Create: `backend/requirements.txt`

- [x] **Step 1: Write API/report tests**

Verify `/api/health` responds and report generation creates a readable `.docx` with summary information.

- [x] **Step 2: Implement FastAPI routes**

Expose `/api/health`, `/api/process`, and `/api/download/{job_id}/{kind}`.

- [x] **Step 3: Implement report writer**

Generate a Word report with input summary, match summary, and review rows.

### Task 4: Frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/styles.css`

- [x] **Step 1: Create upload workflow**

Build a desktop utility interface with file picker, process button, progress/error state, and download links.

- [x] **Step 2: Add result summary**

Display total rows, filled rows, exact matches, review count, and generated filenames.

### Task 5: Verification

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [x] **Step 1: Run backend tests**

Run `python -m pytest backend/tests -v`.

- [x] **Step 2: Run frontend build**

Run `npm install` and `npm run build` inside `frontend`.

- [x] **Step 3: Run sample validation**

Run the fill engine against the provided input workbook and compare generated prices to the answer workbook.
