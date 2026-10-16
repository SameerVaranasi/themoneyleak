from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
app = FastAPI(title="The Money Leak Analytics API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def load_data():
    customers = pd.read_csv(DATA / "customers.csv", parse_dates=["signup_date"])
    products = pd.read_csv(DATA / "products.csv")
    transactions = pd.read_csv(DATA / "transactions.csv", parse_dates=["timestamp"])
    inventory = pd.read_csv(DATA / "inventory.csv", parse_dates=["date"])
    campaigns = pd.read_csv(DATA / "campaigns.csv", parse_dates=["date"])
    tx = transactions.merge(products, on="product_id", how="left", validate="many_to_one").merge(customers, on="customer_id", how="left", validate="many_to_one")
    tx["gross_sales"] = tx["quantity"] * tx["unit_price"]
    tx["discount_amount"] = tx["gross_sales"] * tx["discount_pct"]
    tx["net_sales"] = tx["gross_sales"] - tx["discount_amount"]
    tx["estimated_cost"] = tx["quantity"] * tx["unit_cost"]
    tx["estimated_margin"] = tx["net_sales"] - tx["estimated_cost"]
    tx["margin_pct"] = np.where(tx["net_sales"] != 0, tx["estimated_margin"] / tx["net_sales"] * 100, np.nan)
    return customers, products, transactions, inventory, campaigns, tx


def records(df):
    return df.replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict(orient="records")


def money(v):
    return round(float(v), 2) if pd.notna(v) and np.isfinite(v) else 0.0

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "The Money Leak Analytics API"}

@app.get("/api/metadata")
def metadata():
    customers, products, transactions, inventory, campaigns, tx = load_data()
    return {"row_counts": {"customers": len(customers), "products": len(products), "transactions": len(transactions), "inventory": len(inventory), "campaigns": len(campaigns)}, "date_range": {"transactions_start": str(transactions.timestamp.min()), "transactions_end": str(transactions.timestamp.max()), "inventory_start": str(inventory.date.min().date()), "inventory_end": str(inventory.date.max().date()), "campaigns_start": str(campaigns.date.min().date()), "campaigns_end": str(campaigns.date.max().date())}, "statuses": transactions.status.value_counts().to_dict()}

@app.get("/api/quality")
def quality():
    customers, products, transactions, inventory, campaigns, tx = load_data()
    return {"checks": [
        {"check": "Missing values", "count": int(sum(df.isna().sum().sum() for df in [customers, products, transactions, inventory, campaigns])), "severity": "info", "detail": "Across the five source CSVs."},
        {"check": "Duplicate transaction IDs", "count": int(transactions.transaction_id.duplicated().sum()), "severity": "high", "detail": "Transaction identifiers should be unique."},
        {"check": "Products with unit cost above list price", "count": int((products.unit_cost > products.list_price).sum()), "severity": "medium", "detail": "May be legitimate or synthetic-data inconsistency; investigate before interpreting margins."},
        {"check": "Campaign conversions greater than clicks", "count": int((campaigns.conversions > campaigns.clicks).sum()), "severity": "medium", "detail": "Conversion definition or generated values may be inconsistent."},
        {"check": "Repeated product/date inventory observations", "count": int(inventory.duplicated(["product_id", "date"]).sum()), "severity": "medium", "detail": "Use the latest observation per product for a current-stock snapshot; investigate ties before time-series use."},
        {"check": "Transactions with missing customer reference", "count": int((~transactions.customer_id.isin(customers.customer_id)).sum()), "severity": "high", "detail": "Foreign-key integrity check."},
        {"check": "Transactions with missing product reference", "count": int((~transactions.product_id.isin(products.product_id)).sum()), "severity": "high", "detail": "Foreign-key integrity check."},
        {"check": "Inventory records with missing product reference", "count": int((~inventory.product_id.isin(products.product_id)).sum()), "severity": "high", "detail": "Foreign-key integrity check."},
    ]}

@app.get("/api/overview")
def overview(region: Optional[str] = None, channel: Optional[str] = None, category: Optional[str] = None):
    customers, products, transactions, inventory, campaigns, tx = load_data()
    if region and region != "All": tx = tx[tx.region == region]
    if channel and channel != "All": tx = tx[tx.channel == channel]
    if category and category != "All": tx = tx[tx.category == category]
    completed = tx[tx.status == "Completed"]
    returned = tx[tx.status == "Returned"]
    cancelled = tx[tx.status == "Cancelled"]
    gross = completed.gross_sales.sum(); discount = completed.discount_amount.sum(); net = completed.net_sales.sum(); cost = completed.estimated_cost.sum(); margin = completed.estimated_margin.sum()
    monthly = completed.assign(month=completed.timestamp.dt.to_period("M").astype(str)).groupby("month", as_index=False).agg(net_sales=("net_sales", "sum"), estimated_margin=("estimated_margin", "sum"))
    category_sales = completed.groupby("category", as_index=False).agg(net_sales=("net_sales", "sum"), estimated_margin=("estimated_margin", "sum")).sort_values("net_sales", ascending=False)
    channel_sales = completed.groupby("channel", as_index=False).agg(net_sales=("net_sales", "sum"), estimated_margin=("estimated_margin", "sum"))
    return {"kpis": {"gross_sales": money(gross), "discounts": money(discount), "net_sales": money(net), "estimated_cost": money(cost), "estimated_margin": money(margin), "margin_pct": money(margin/net*100 if net else 0), "completed_transactions": int(len(completed)), "return_rate": money(len(returned)/max(len(completed)+len(returned), 1)*100), "cancellation_rate": money(len(cancelled)/max(len(tx), 1)*100)}, "monthly_sales": records(monthly), "category_sales": records(category_sales), "channel_sales": records(channel_sales), "filters": {"regions": sorted(tx.region.dropna().unique().tolist()), "channels": sorted(transactions.channel.dropna().unique().tolist()), "categories": sorted(products.category.dropna().unique().tolist())}}

@app.get("/api/leakage")
def leakage(limit: int = 15):
    _, products, _, _, _, tx = load_data()
    completed = tx[tx.status == "Completed"]
    by_product = completed.groupby(["product_id", "category"], as_index=False).agg(units=("quantity", "sum"), net_sales=("net_sales", "sum"), estimated_cost=("estimated_cost", "sum"), estimated_margin=("estimated_margin", "sum"), transactions=("transaction_id", "count"))
    by_product["margin_pct"] = np.where(by_product.net_sales != 0, by_product.estimated_margin/by_product.net_sales*100, np.nan)
    by_product = by_product.sort_values("estimated_margin")
    by_category = completed.groupby("category", as_index=False).agg(net_sales=("net_sales", "sum"), estimated_margin=("estimated_margin", "sum"), estimated_cost=("estimated_cost", "sum"))
    by_region = completed.groupby("region", as_index=False).agg(net_sales=("net_sales", "sum"), estimated_margin=("estimated_margin", "sum"))
    by_channel = completed.groupby("channel", as_index=False).agg(net_sales=("net_sales", "sum"), estimated_margin=("estimated_margin", "sum"))
    return {"lowest_margin_products": records(by_product.head(limit)), "highest_margin_products": records(by_product.tail(limit).sort_values("estimated_margin", ascending=False)), "by_category": records(by_category.sort_values("estimated_margin")), "by_region": records(by_region.sort_values("estimated_margin")), "by_channel": records(by_channel.sort_values("estimated_margin"))}

@app.get("/api/returns")
def returns(limit: int = 15):
    _, _, _, _, _, tx = load_data()
    eligible = tx[tx.status.isin(["Completed", "Returned"])]
    grouped = eligible.groupby(["product_id", "category", "region", "channel"], as_index=False).agg(eligible_orders=("transaction_id", "count"), returned_orders=("status", lambda s: int((s == "Returned").sum())), eligible_net_sales=("net_sales", "sum"), returned_sales=("net_sales", lambda s: float(s[eligible.loc[s.index, "status"] == "Returned"].sum())))
    grouped["return_rate_pct"] = np.where(grouped.eligible_orders > 0, grouped.returned_orders/grouped.eligible_orders*100, 0)
    discount = eligible.assign(discount_band=pd.cut(eligible.discount_pct, [-0.001, 0, .1, .2, .251], labels=["0%", ">0–10%", ">10–20%", ">20–25%"], include_lowest=True)).groupby("discount_band", observed=False).agg(orders=("transaction_id", "count"), return_rate_pct=("status", lambda s: (s == "Returned").mean()*100)).reset_index()
    cat = eligible.groupby("category", as_index=False).agg(orders=("transaction_id", "count"), returned_orders=("status", lambda s: int((s == "Returned").sum())), returned_sales=("net_sales", lambda s: float(s[eligible.loc[s.index, "status"] == "Returned"].sum())))
    cat["return_rate_pct"] = cat.returned_orders/cat.orders*100
    return {"risk_ranking": records(grouped.sort_values(["return_rate_pct", "returned_sales"], ascending=False).head(limit)), "by_category": records(cat.sort_values("returned_sales", ascending=False)), "by_discount": records(discount)}

@app.get("/api/inventory")
def inventory_risk(limit: int = 30):
    _, products, transactions, inventory, _, tx = load_data()
    latest = inventory.sort_values(["date", "inventory_record_id"]).groupby("product_id", as_index=False).tail(1)
    latest = latest.merge(products, on="product_id", how="left")
    completed = tx[tx.status == "Completed"]
    sales = completed.groupby("product_id", as_index=False).agg(units_sold=("quantity", "sum"), last_sale=("timestamp", "max"))
    daily = completed.groupby("product_id").apply(lambda x: x.groupby(x.timestamp.dt.date).quantity.sum().mean(), include_groups=False).rename("avg_units_per_active_day").reset_index()
    latest = latest.merge(sales, on="product_id", how="left").merge(daily, on="product_id", how="left")
    latest[["units_sold", "avg_units_per_active_day"]] = latest[["units_sold", "avg_units_per_active_day"]].fillna(0)
    latest["days_of_cover_est"] = np.where(latest.avg_units_per_active_day > 0, latest.stock_on_hand/latest.avg_units_per_active_day, np.nan)
    latest["risk_score"] = (latest.stock_on_hand <= latest.reorder_threshold).astype(int)*50 + (latest.stockout_flag.astype(int)*30) + (latest.supplier_delay_days >= latest.supplier_lead_days).astype(int)*20
    latest["recommendation"] = np.select([latest.stock_on_hand <= latest.reorder_threshold, latest.stockout_flag == 1, latest.avg_units_per_active_day == 0], ["Replenish review: at/below reorder threshold", "Investigate stockout flag", "Review demand before replenishing"], default="Monitor stock")
    ranked = latest.sort_values(["risk_score", "supplier_delay_days"], ascending=False)
    return {"latest_snapshot_date": str(latest.date.max().date()), "at_or_below_reorder": int((latest.stock_on_hand <= latest.reorder_threshold).sum()), "stockout_flags_latest": int((latest.stockout_flag == 1).sum()), "products_without_observed_completed_sales": int((latest.avg_units_per_active_day == 0).sum()), "risk_ranking": records(ranked.head(limit)[["product_id", "category", "stock_on_hand", "reorder_threshold", "stockout_flag", "supplier_delay_days", "supplier_lead_days", "units_sold", "avg_units_per_active_day", "days_of_cover_est", "risk_score", "recommendation"]]), "latest_stock": records(latest[["product_id", "category", "date", "stock_on_hand", "reorder_threshold", "stockout_flag"]].sort_values("stock_on_hand"))}

@app.get("/api/campaigns")
def campaign_efficiency(limit: int = 20):
    _, _, _, _, campaigns, _ = load_data()
    c = campaigns.copy()
    c["cpc"] = np.where(c.clicks > 0, c.spend/c.clicks, np.nan)
    c["cost_per_conversion"] = np.where(c.conversions > 0, c.spend/c.conversions, np.nan)
    c["ctr_pct"] = np.where(c.impressions > 0, c.clicks/c.impressions*100, np.nan)
    c["conversion_rate_pct"] = np.where(c.clicks > 0, c.conversions/c.clicks*100, np.nan)
    by_channel = c.groupby("channel", as_index=False).agg(spend=("spend", "sum"), clicks=("clicks", "sum"), conversions=("conversions", "sum"), impressions=("impressions", "sum"))
    by_channel["cpc"] = by_channel.spend/by_channel.clicks.replace(0, np.nan)
    by_channel["cost_per_conversion"] = by_channel.spend/by_channel.conversions.replace(0, np.nan)
    by_channel["ctr_pct"] = by_channel.clicks/by_channel.impressions.replace(0, np.nan)*100
    by_channel["conversion_rate_pct"] = by_channel.conversions/by_channel.clicks.replace(0, np.nan)*100
    by_category = c.groupby("category", as_index=False).agg(spend=("spend", "sum"), clicks=("clicks", "sum"), conversions=("conversions", "sum"))
    by_category["cpc"] = by_category.spend/by_category.clicks.replace(0, np.nan)
    by_category["cost_per_conversion"] = by_category.spend/by_category.conversions.replace(0, np.nan)
    return {"summary": {"spend": money(c.spend.sum()), "clicks": int(c.clicks.sum()), "conversions": int(c.conversions.sum()), "cpc": money(c.spend.sum()/c.clicks.sum()), "cost_per_conversion": money(c.spend.sum()/c.conversions.sum()), "conversions_gt_clicks": int((c.conversions > c.clicks).sum())}, "campaigns": records(c.sort_values("cost_per_conversion", ascending=False).head(limit)), "by_channel": records(by_channel), "by_category": records(by_category)}

@app.get("/api/customers")
def customer_analysis(limit: int = 20):
    _, _, _, _, _, tx = load_data()
    completed = tx[tx.status == "Completed"].copy()
    customer = completed.groupby(["customer_id", "region", "customer_segment"], as_index=False).agg(net_sales=("net_sales", "sum"), estimated_margin=("estimated_margin", "sum"), orders=("transaction_id", "nunique"), units=("quantity", "sum"))
    customer["aov"] = customer.net_sales/customer.orders.replace(0, np.nan)
    segment = customer.groupby("customer_segment", as_index=False).agg(customers=("customer_id", "nunique"), net_sales=("net_sales", "sum"), estimated_margin=("estimated_margin", "sum"), orders=("orders", "sum"))
    segment["aov"] = segment.net_sales/segment.orders.replace(0, np.nan)
    region = customer.groupby("region", as_index=False).agg(customers=("customer_id", "nunique"), net_sales=("net_sales", "sum"), estimated_margin=("estimated_margin", "sum"), orders=("orders", "sum"))
    region["aov"] = region.net_sales/region.orders.replace(0, np.nan)
    return {"segments": records(segment.sort_values("net_sales", ascending=False)), "regions": records(region.sort_values("net_sales", ascending=False)), "top_customers": records(customer.sort_values("net_sales", ascending=False).head(limit)), "low_margin_high_sales_segments": records(segment.sort_values("estimated_margin").head(5))}

@app.get("/api/anomalies")
def anomalies():
    _, products, transactions, inventory, campaigns, tx = load_data()
    completed = tx[tx.status == "Completed"]
    product_margin = completed.groupby(["product_id", "category"], as_index=False).agg(net_sales=("net_sales", "sum"), estimated_margin=("estimated_margin", "sum"))
    product_margin["margin_pct"] = np.where(product_margin.net_sales != 0, product_margin.estimated_margin/product_margin.net_sales*100, np.nan)
    margin_mean = product_margin.margin_pct.mean(); margin_std = product_margin.margin_pct.std(ddof=0)
    unusual_margin = product_margin[(product_margin.margin_pct < margin_mean - 2*margin_std) | (product_margin.margin_pct > margin_mean + 2*margin_std)].copy()
    unusual_margin["alert"] = "Product margin outside 2 standard deviations of product-level distribution"
    disc = completed.groupby(["product_id", "category"], as_index=False).agg(avg_discount_pct=("discount_pct", "mean"), orders=("transaction_id", "count"))
    cutoff = disc.avg_discount_pct.quantile(.95)
    high_discount = disc[disc.avg_discount_pct >= cutoff].copy(); high_discount["alert"] = "Average discount in top 5% of products"
    c = campaigns.copy(); c["cpc"] = c.spend/c.clicks.replace(0, np.nan)
    c["cost_per_conversion"] = c.spend/c.conversions.replace(0, np.nan)
    cpc_cutoff = c.cpc.quantile(.95)
    expensive = c[c.cpc >= cpc_cutoff].copy(); expensive["alert"] = "Campaign CPC in top 5%"
    return {"unusual_margins": records(unusual_margin.sort_values("margin_pct")), "high_discount_products": records(high_discount.sort_values("avg_discount_pct", ascending=False)), "expensive_campaigns": records(expensive.sort_values("cpc", ascending=False)), "thresholds": {"product_margin_mean_pct": money(margin_mean), "product_margin_std_pct": money(margin_std), "high_discount_p95": money(cutoff*100), "campaign_cpc_p95": money(cpc_cutoff)}}

@app.get("/api/risk-monitor")
def risk_monitor(horizon_days: int = 30, limit: int = 30):
    _, products, transactions, inventory, _, tx = load_data()
    completed = tx[tx.status == "Completed"].copy()
    end = completed.timestamp.max().normalize()
    recent_start = end - pd.Timedelta(days=27)
    previous_start = end - pd.Timedelta(days=55)
    recent = completed[completed.timestamp >= recent_start].groupby("product_id").quantity.sum()
    previous = completed[(completed.timestamp >= previous_start) & (completed.timestamp < recent_start)].groupby("product_id").quantity.sum()
    latest = inventory.sort_values(["date", "inventory_record_id"]).groupby("product_id", as_index=False).tail(1).merge(products, on="product_id", how="left")
    latest["recent_28d_units"] = latest.product_id.map(recent).fillna(0)
    latest["previous_28d_units"] = latest.product_id.map(previous).fillna(0)
    latest["daily_demand_est"] = latest.recent_28d_units / 28
    # Simple transparent baseline: recent 28-day average scaled to requested horizon.
    latest["forecast_units"] = np.ceil(latest.daily_demand_est * horizon_days).astype(int)
    latest["demand_change_pct"] = np.where(latest.previous_28d_units > 0, (latest.recent_28d_units-latest.previous_28d_units)/latest.previous_28d_units*100, np.where(latest.recent_28d_units > 0, 100, 0))
    latest["days_of_cover"] = np.where(latest.daily_demand_est > 0, latest.stock_on_hand/latest.daily_demand_est, np.nan)
    latest["reorder_point_est"] = np.ceil(latest.daily_demand_est * latest.supplier_lead_days + np.sqrt(np.maximum(latest.recent_28d_units, 1))*0.5).astype(int)
    latest["suggested_order_qty"] = np.maximum(0, latest.forecast_units + latest.reorder_point_est - latest.stock_on_hand).astype(int)
    latest["risk_score"] = 0
    latest.loc[latest.stock_on_hand <= latest.reorder_threshold, "risk_score"] += 35
    latest.loc[latest.stock_on_hand < latest.reorder_point_est, "risk_score"] += 25
    latest.loc[latest.supplier_delay_days >= latest.supplier_lead_days, "risk_score"] += 15
    latest.loc[latest.demand_change_pct >= 25, "risk_score"] += 15
    latest.loc[latest.stockout_flag == 1, "risk_score"] += 10
    latest["risk_level"] = np.select([latest.risk_score >= 60, latest.risk_score >= 30], ["High", "Medium"], default="Low")
    latest["recommendation"] = np.select([latest.daily_demand_est == 0, latest.stock_on_hand <= latest.reorder_threshold, latest.stock_on_hand < latest.reorder_point_est, latest.demand_change_pct <= -25], ["Validate demand; avoid automatic replenishment", "Prioritize replenishment review", "Plan replenishment using lead time", "Review for slow-mover or markdown decision"], default="Monitor; no immediate action indicated")
    latest["reason"] = latest.apply(lambda r: f"Recent 28-day units: {int(r.recent_28d_units)}; stock: {int(r.stock_on_hand)}; reorder threshold: {int(r.reorder_threshold)}; supplier lead: {int(r.supplier_lead_days)} days; demand change: {round(float(r.demand_change_pct),1)}% vs prior 28 days.", axis=1)
    ranked = latest.sort_values(["risk_score", "suggested_order_qty"], ascending=False)
    return {"data_through": str(end.date()), "horizon_days": horizon_days, "method": "Transparent baseline: recent 28-day completed unit sales scaled to horizon. Not a trained ML model; one year of synthetic history and stockout-censored demand limit reliability.", "summary": {"high_risk_products": int((latest.risk_level == "High").sum()), "medium_risk_products": int((latest.risk_level == "Medium").sum()), "products_with_forecast_demand": int((latest.forecast_units > 0).sum()), "products_at_or_below_reorder": int((latest.stock_on_hand <= latest.reorder_threshold).sum())}, "products": records(ranked.head(limit)[["product_id", "category", "stock_on_hand", "reorder_threshold", "supplier_lead_days", "supplier_delay_days", "recent_28d_units", "previous_28d_units", "demand_change_pct", "forecast_units", "days_of_cover", "reorder_point_est", "suggested_order_qty", "risk_score", "risk_level", "recommendation", "reason"]])}
