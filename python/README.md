# x402 Financial Data API — Python Client

Python client library for the **[x402 Financial Data API](https://github.com/nebmil569/x402-financial-data-api)**.
Pays for requests automatically using the [x402 protocol](https://x402.org) (USDC on Base network).

## Install

```bash
pip install httpx 'python-x402[evm]>=0.2.0'
```

Or from this repo:
```bash
pip install -e .
```

## Quick Start

```python
import os
from x402_financial_client import FinancialDataClient

# Your EVM wallet private key (hex format, 0x...)
# The client pays for requests automatically via x402 protocol
WALLET_PRIVATE_KEY = os.environ["WALLET_PRIVATE_KEY"]

client = FinancialDataClient(wallet_private_key=WALLET_PRIVATE_KEY)

# ── Free endpoints (no wallet needed) ──────────────────────────────────
name = client.clean_merchant("DBSS MART F&B PL")
print(name)  # {"cleaned": "DBS Mart", "original": "DBSS MART F&B PL"}

holidays = client.list_holidays(2026)
print(holidays)

# ── Paid endpoints (wallet pays via x402) ────────────────────────────────
transactions = [
    {"date": "2026-01-15", "description": "GRAB SINGAPORE", "amount": -18.50, "type": "debit"},
    {"date": "2026-01-16", "description": "SHENG SIONG HYPERMKT", "amount": -156.20, "type": "debit"},
]

summary = client.summary(transactions)
report  = client.spending_report(transactions)
insights = client.financial_insights(transactions)

# Parse a bank statement PDF
with open("bank_statement.pdf", "rb") as f:
    parsed = client.parse_pdf(f.read(), bank="dbs")

# Singapore financial tools
cpf    = client.cpf_calculator("1987-06-15", cpf_balance=45000, monthly_contribution=1500)
srs    = client.srs_calculator(annual_income=85000, age=39, citizenship="citizen")
hdb    = client.hdb_resale("Tampines", flat_type="4-room", floor_level=10)
bto    = client.bto_affordability("4-room", "Tampines", household_income=8000, cpf_balance=80000)
sgx    = client.sgx_stock("DBS")
coe    = client.coe_prices()
fire   = client.fire(current_age=39, current_savings=150000, monthly_expenses=4000, target_age=55)
```

## No API Keys

The x402 protocol handles payment **on-chain**. There's no API key — just connect your wallet and go.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `X402_API_URL` | `https://x402-financial-data-api.vercel.app` | API base URL |
| `WALLET_PRIVATE_KEY` | _(required for paid calls)_ | Wallet private key (hex) |

## Endpoints

### Free (no wallet needed)
| Endpoint | Description |
|----------|-------------|
| `GET /merchant/clean` | Clean raw transaction description → merchant name |
| `GET /merchant/batch-clean` | Batch clean up to 100 descriptions |
| `GET /holidays/singapore` | Singapore public holidays |

### Paid (wallet pays via x402)
| Endpoint | Price | Description |
|----------|-------|-------------|
| `POST /parse/{bank}` | $0.02 | Parse bank statement PDF (9 banks) |
| `POST /extract/transactions` | $0.01 | AI entity extraction + categorization |
| `POST /summary` | $0.01 | Financial summary |
| `POST /report/spending` | $0.01 | Expense report + SG benchmarks |
| `POST /report/cash-flow` | $0.01 | Cash flow analysis |
| `POST /report/subscriptions` | $0.01 | Recurring subscription detection |
| `POST /report/tax` | $0.02 | Tax report |
| `POST /invoice` | $0.02 | Generate invoice PDF |
| `POST /financial-insights` | $0.01 | AI financial insights |
| `POST /cpf/calculator` | $0.02 | CPF retirement projection |
| `POST /srs/calculator` | $0.01 | SRS tax optimization |
| `POST /hdb/resale` | $0.01 | HDB resale price estimate |
| `POST /bto/affordability` | $0.02 | BTO affordability + grants |
| `POST /property/tax` | $0.01 | IRAS property tax |
| `POST /property/absd` | $0.01 | ABSD/BSD calculator |
| `POST /sgx/stock` | $0.02 | SGX stock profile |
| `POST /sgx/portfolio` | $0.03 | Batch SGX stocks (≤20) |
| `POST /sgx/price` | $0.005 | Real-time SGX price |
| `POST /coe/prices` | $0.01 | Latest COE premiums |
| `POST /fire` | $0.01 | Singapore FIRE calculator |
| `POST /refinance` | $0.015 | Mortgage refinance analyzer |

## For AI Agents

Agents can use this client directly — no browser, no manual payment flow:

```python
# Minimal agent usage
from x402_financial_client import FinancialDataClient
client = FinancialDataClient(wallet_private_key=agent_wallet)

# Agent receives bank statement bytes from user
result = client.parse_pdf(statement_bytes, bank="ocbc")

# Agent summarizes spending
report = client.spending_report(result["transactions"])
```

All amounts in **USDC on Base network** (`eip155:8453`).
Receiving wallet: `0x50F9D979b825670A9936D992F5db8AEd9497208A`
