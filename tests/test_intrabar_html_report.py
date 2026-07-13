from pathlib import Path
from html.parser import HTMLParser


REPORT = Path("docs/intrabar-rsi-comparison-latest.html")
MARKDOWN_REPORT = Path("docs/intrabar-rsi-comparison-latest.md")


class RunRowParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "tr" and "run-row" in attributes.get("class", "").split():
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def normalized_run_rows(rows):
    return [[cell.replace(",", "").replace(" KRW", "") for cell in row] for row in rows]


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
    assert "@media (max-width: 820px)" in html
    assert 'id="toggle-details"' in html


def test_intrabar_html_tables_match_all_markdown_run_rows():
    mode_names = {
        "completed": "완성봉",
        "immediate": "즉시",
        "hold_30s": "30초 유지",
    }
    protection_names = {"protected": "적용", "unprotected": "미적용"}
    markdown_rows = []
    for line in MARKDOWN_REPORT.read_text(encoding="utf-8").splitlines():
        if not line.startswith(("| protected |", "| unprotected |")):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        cells[0] = protection_names[cells[0]]
        cells[1] = mode_names[cells[1]]
        markdown_rows.append(cells)

    parser = RunRowParser()
    parser.feed(REPORT.read_text(encoding="utf-8"))

    assert len(markdown_rows) == 54
    assert normalized_run_rows(parser.rows) == normalized_run_rows(markdown_rows)
