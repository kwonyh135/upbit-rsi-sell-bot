# Intrabar RSI HTML Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a readable, standalone Korean HTML version of the latest KRW-HUNT intrabar RSI timing report.

**Architecture:** Add one tracked static HTML artifact beside the Markdown report. A focused test treats the HTML as a report contract, checking the recommendation, corrected headline values, all 54 result rows, offline-only assets, and collapsible detail sections; browser QA covers visual layout.

**Tech Stack:** HTML5, embedded CSS, minimal embedded JavaScript, pytest, in-app browser.

## Global Constraints

- Output path is `docs/intrabar-rsi-comparison-latest.html`.
- Do not load remote libraries, fonts, images, or APIs.
- Preserve the exact latest values from `docs/intrabar-rsi-comparison-latest.md`.
- Do not modify live trading code, AWS configuration, runtime state, or orders.
- Body copy is Korean while technical mode identifiers remain recognizable.

---

### Task 1: Build And Verify The Standalone Report

**Files:**
- Create: `docs/intrabar-rsi-comparison-latest.html`
- Create: `tests/test_intrabar_html_report.py`

**Interfaces:**
- Consumes: the exact recommendation, coverage, matrices, cycle diagnostics, event differences, and limitations in `docs/intrabar-rsi-comparison-latest.md`.
- Produces: one offline HTML document that can be opened directly in a browser.

- [ ] **Step 1: Write the failing report-contract test**

```python
from pathlib import Path


REPORT = Path("docs/intrabar-rsi-comparison-latest.html")


def test_intrabar_html_report_contains_correct_summary_and_all_runs():
    html = REPORT.read_text(encoding="utf-8")
    assert '<html lang="ko">' in html
    assert "30초 유지" in html
    assert "25.68%" in html
    assert "5.64%" in html
    assert html.count('class="run-row') == 54
    assert html.count("<details") >= 3


def test_intrabar_html_report_is_standalone_and_discloses_risk():
    html = REPORT.read_text(encoding="utf-8")
    assert "https://" not in html
    assert "http://" not in html
    assert "과거 결과는 미래 수익을 보장하지 않습니다" in html
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_intrabar_html_report.py -q`

Expected: FAIL because `docs/intrabar-rsi-comparison-latest.html` does not exist.

- [ ] **Step 3: Create the standalone HTML**

Create semantic sections with these stable hooks:

```html
<html lang="ko">
  <section id="recommendation">...</section>
  <section id="holdout-comparison">...</section>
  <section id="interpretation">...</section>
  <details id="full-period">...</details>
  <details id="training">...</details>
  <details id="holdout">...</details>
  <section id="diagnostics">...</section>
  <section id="limitations">...</section>
</html>
```

The three summary mode cards use completed `3.45% / 18.05% / -11.71%`, immediate `12.64% / 20.22% / -7.53%`, and hold-30-second `25.68% / 18.21% / 5.64%` for holdout return, MDD, and 0.30% stress return. Copy all 18 rows from each Markdown matrix into its corresponding detail table and mark every body row with `class="run-row"`. Embed responsive styling, print styling, accessible labels, and a small button that expands or collapses all details.

- [ ] **Step 4: Run focused and full automated verification**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_intrabar_html_report.py -q`

Expected: `2 passed`.

Run: `./.venv/Scripts/python.exe -m pytest -q`

Expected: all project tests pass.

- [ ] **Step 5: Perform browser QA**

Open the absolute local HTML path in the in-app browser. Verify the recommendation and three summary cards are visible, toggle the detail controls, inspect the 54-row content, then resize to a narrow viewport and confirm cards stack and tables scroll horizontally without page clipping.

- [ ] **Step 6: Commit the artifact and test**

```bash
git add docs/intrabar-rsi-comparison-latest.html tests/test_intrabar_html_report.py
git commit -m "docs: add readable intrabar RSI HTML report"
```
