# Spendr

A Flask dashboard that turns a household transactions CSV into eight spending charts.

## Charts

| Chart | What it shows |
|---|---|
| Monthly spending trends | total expenses per month (line) |
| Category breakdown | total expenses per category (bar) |
| Payment modes | total amount per payment mode, across all transaction types (bar) |
| Spending heatmap | expenses by year × month |
| Category-wise spending | each category's share of expenses (pie) |
| Yearly spending | total expenses per year |
| Quarterly spending | total expenses per quarter |
| Category over time | monthly expenses per category (stacked area) |

Click a chart to enlarge it.

## Run

Requires Python 3.10+.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
.venv/bin/python app.py                            # Windows: .venv\Scripts\python app.py
```

Then open http://127.0.0.1:5000.

## Data

`Daily Household Transactions.csv` holds 2,461 transactions in INR from January 2015 to September 2018. Columns:

| Column | Example |
|---|---|
| Date | `20/09/2018 12:04:08` or `19/09/2018` (day first, time optional) |
| Mode | `Cash`, `Saving Bank account 1` |
| Category, Subcategory | `Food`, `snacks` |
| Note | free text |
| Amount | `60` |
| Income/Expense | `Expense`, `Income`, `Transfer-Out` |
| Currency | `INR` |

To use your own data, replace the CSV with one that has the same columns.

## Project structure

```
app.py                  load the CSV, draw the charts, serve the page
templates/index.html    dashboard page
requirements.txt
Daily Household Transactions.csv
static/                 generated chart images (created at runtime, not committed)
```

## Notes

- The charts are redrawn on every page load, so the first load takes a few seconds.
- Most charts count only `Expense` rows. The payment-mode chart sums every row, including income and transfers.
- Charts are written to `static/` as shared files, so two people loading the page at the same moment can overwrite each other's images. That's fine for local use but not for multi-user hosting.
