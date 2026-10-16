# Initial data audit — The Money Leak

## Files and grain

| File | Rows | Columns | Expected join/use |
|---|---:|---:|---|
| customers.csv | 3,000 | 5 | `customer_id` joins transactions |
| products.csv | 250 | 5 | `product_id` joins transactions and inventory |
| transactions.csv | 18,000 | 10 | Transaction-level events |
| inventory.csv | 5,000 | 7 | Product/date stock observations |
| campaigns.csv | 1,200 | 8 | Campaign/day/channel/category metrics |

## Validation results

- No null values found in any of the five CSVs.
- No duplicate full rows found.
- No duplicate IDs found in each file's primary identifier.
- No transaction rows reference unknown customers or products.
- No inventory rows reference unknown products.
- Transactions span `2025-01-01 00:11:00` through `2025-12-31 23:53:00`.
- Inventory observations span `2025-01-01` through `2025-12-31`.
- Campaign dates span `2025-01-01` through `2025-12-31`.
- Transaction status counts: Completed 13,962; Cancelled 1,689; Returned 1,431; Pending 918.
- 76 products have `unit_cost > list_price`. This is a warning, not automatic proof of bad data, but it can generate implausible margins.
- 88 campaigns have `conversions > clicks`. Validate how conversion is defined before interpreting conversion rate.
- Inventory has 114 repeated `(product_id, date)` combinations. Snapshot selection uses the final row after sorting by date and `inventory_record_id`, but this needs a business rule before production.
- Transaction discount percentages range from 0 to 0.25; quantities are positive (1–5); transaction unit prices and product unit costs/list prices are positive.
- Inventory stock and reorder thresholds are non-negative; stockout flag values are 0 or 1.

## Metric definitions used in prototype

Main sales KPIs use `Completed` transactions only. `Returned`, `Cancelled`, and `Pending` are kept separate. Gross sales = `quantity × transaction unit_price`; discount amount = gross sales × `discount_pct`; net sales = gross sales − discount amount; estimated cost = quantity × product `unit_cost`; estimated margin = net sales − estimated cost.

Return rate = returned transactions / (completed + returned transactions). Cancellation rate = cancelled transactions / all filtered transactions. Campaign CPC = spend / clicks; cost per conversion = spend / conversions. Campaign conversion counts greater than clicks are retained but surfaced as a data-quality concern.

## Important limits

The README labels the data synthetic and educational. Costs and prices were independently generated. Currency is not specified in the source; the UI currently formats financial values as INR for presentation only. Campaigns have no transaction-level campaign ID, so campaign-attributed revenue and ROAS cannot be computed. The 2025 dataset is historical and does not support real-time claims. The demand forecast in this prototype is a transparent 28-day average baseline, not a trained machine-learning model.
