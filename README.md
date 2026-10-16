# The Money Leak — Business Dashboard + Risk Monitor

A local-first analytics prototype using React, Tailwind CSS, Recharts, FastAPI and pandas. It includes the five synthetic source CSVs provided for the project.

## Dataset findings

- customers: 3,000 rows; products: 250; transactions: 18,000; inventory: 5,000; campaigns: 1,200.
- Source files have no missing values or duplicate rows/IDs in the initial audit.
- All transaction customer/product IDs and inventory product IDs map to source tables.
- Transactions, inventory and campaigns cover Jan–Dec 2025.
- 76 products have unit_cost > list_price; investigate before interpreting margins.
- 88 campaign rows have conversions > clicks; CPC/cost-per-conversion can be calculated, but conversion-rate interpretation needs caution.
- Inventory contains repeated product/date pairs; the prototype selects the last record after sorting by date and inventory_record_id for the snapshot. Resolve tied observations for production use.
- Campaign data does not have transaction-level campaign IDs, so do not infer attributable revenue or ROAS.
- This is synthetic educational data, not real company data.

## Run locally

### 1. Backend

Open a terminal in `backend`:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: http://127.0.0.1:8000/docs
Health check: http://127.0.0.1:8000/api/health

### 2. Frontend

Open a second terminal in `frontend`:

```bash
npm install
npm run dev
```

Open http://localhost:5173.

## Included dashboard features

Business dashboard: overview KPIs, monthly sales/margin trend, category performance, product margin ranking, return risk, inventory risk, campaign efficiency, customer/region comparisons, quality checks and campaign anomaly table.

Risk monitor: 7/14/30/60/90-day baseline demand estimates, recent-vs-prior sales trend, inventory risk scoring, estimated days of cover, reorder point estimate, suggested quantity and explanation text.

## Important methodology notes

- Revenue and margin KPIs use `Completed` transactions only. Returned, cancelled and pending transactions are excluded from the main sales KPIs.
- Gross sales = quantity × transaction unit price; discount amount = gross sales × discount_pct; net sales = gross sales − discount amount; estimated cost = quantity × product unit_cost; estimated margin = net sales − estimated cost.
- Return rate is returned transactions divided by completed + returned transactions. Cancellation rate is cancelled transactions divided by all filtered transactions.
- The demand estimate is a transparent baseline: completed units in the latest 28-day window divided by 28; scaled to the selected forecast horizon. It is not a trained ML model and is not backtested yet.
- Inventory observations are synthetic and may not represent current stock in real life. Review suggested quantities manually.
- Currency is displayed as INR as a UI convention; confirm the intended currency before interpreting financial values.

## Next development steps

1. Add automated tests for every metric and API endpoint.
2. Resolve duplicate product/date inventory observations and decide which observation is authoritative.
3. Add chronological forecast backtesting and compare a naive baseline with moving average/seasonal models.
4. Add export to CSV and drill-down filters to each feature.
5. Add PostgreSQL only when the CSV-based prototype and data definitions are stable.
