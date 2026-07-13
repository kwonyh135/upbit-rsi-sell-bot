# Intrabar RSI HTML Report Design

## Purpose

Create a readable, standalone HTML companion for the existing KRW-HUNT intrabar RSI Markdown report. The HTML must preserve the tested numbers and recommendation while making the decision, risks, and detailed run matrix easier to scan.

## Source And Output

- Source of truth: `docs/intrabar-rsi-comparison-latest.md` and the matching generated JSON result.
- Output: `docs/intrabar-rsi-comparison-latest.html`.
- The output is a single offline file with embedded CSS and JavaScript. It must not load remote libraries, fonts, images, or APIs.
- This work does not change live trading code, AWS configuration, runtime state, or orders.

## Information Architecture

1. A title and data-coverage strip identify the market, period, observation count, and split date.
2. A recommendation hero states that `hold_30s` won and explains the holdout and slippage criteria in Korean.
3. Summary cards compare holdout return, MDD, completed cycles, and 0.30% stress return for completed, immediate, and hold-30-second modes.
4. Lightweight CSS bar charts visualize holdout return, MDD, and stress return without external chart libraries.
5. A short interpretation section explains why hold-30-second won, what false signals mean, and why the result is not a profit guarantee.
6. Full-period, training, and holdout matrices remain available in collapsed detail sections. Duplicate protected and unprotected rows remain visible because they are part of the original 54-run evidence.
7. Cycle concentration, event timing differences, methodology, and limitations appear below the main comparison.

## Visual Design

- Use a calm dark navy and warm off-white palette with green for positive values, red for losses, and amber for cautions.
- Use responsive cards and horizontally scrollable tables so the report works on desktop and narrow windows.
- Emphasize `hold_30s` consistently with a winner badge and accent border.
- Keep all body copy in Korean while preserving technical mode identifiers and exact numeric values.
- Respect `prefers-reduced-motion`; no decorative animation is required.

## Data Integrity

- Exact table values are copied from the latest generated Markdown report.
- The headline uses the corrected holdout results: completed `3.45%`, immediate `12.64%`, hold-30-second `25.68%`.
- The 0.30% stress results are completed `-11.71%`, immediate `-7.53%`, hold-30-second `5.64%`.
- The recommendation must remain `hold_30s` and the report must disclose that historical results do not guarantee future performance.

## Validation

- Confirm the HTML contains all three 18-run matrices and the expected recommendation and headline values.
- Open the local HTML in the in-app browser and inspect the rendered text, layout, table overflow, and detail controls.
- Check desktop and narrow viewport screenshots for clipping or unreadable content.
- Run the existing Python test suite to confirm no project behavior changed.
