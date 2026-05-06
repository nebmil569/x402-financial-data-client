#!/usr/bin/env python3
"""
x402 Financial Data API — Python Client
========================================
Python client for the x402 Financial Data API.
Pays for requests using the x402 protocol (USDC on Base network).

Supports:
- Bank statement PDF parsing (9 Singapore banks)
- AI-powered transaction extraction & categorization
- Financial reports (spending, cash flow, subscriptions, tax)
- Singapore-specific tools (CPF, HDB, BTO, COE, SGX stocks, property tax, ABSD...)
- Free merchant name cleaning

Install:
    pip install httpx python-x402
    # or
    pip install -e .

Usage:
    from x402_financial_client import FinancialDataClient

    client = FinancialDataClient(
        wallet_private_key=os.environ["WALLET_PRIVATE_KEY"]
    )

    # Parse a bank statement PDF
    with open("bank_statement.pdf", "rb") as f:
        result = client.parse_pdf(f.read(), bank="dbs")

    # Get spending report
    report = client.spending_report(transactions)

    # Free merchant cleaning
    cleaned = client.clean_merchant("DBSS MART F&B PL")

For agents / automated use: set WALLET_PRIVATE_KEY in environment.
No API keys needed — payments are on-chain via x402.
"""

import os
import json
import base64
from typing import Optional
from pathlib import Path

try:
    from x402.client import Client as X402Client
    from x402.schemas.payments import PaymentPayload
    HAS_X402 = True
except ImportError:
    HAS_X402 = False

import httpx


BASE_URL = os.getenv("X402_API_URL", "https://x402-financial-data-api.vercel.app")
NETWORK = "eip155:8453"
USDC_ASSET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
RECEIVING_WALLET = "0x50F9D979b825670A9936D992F5db8AEd9497208A"


class FinancialDataClient:
    """
    Python client for the x402 Financial Data API.

    Usage:
        client = FinancialDataClient(wallet_private_key="0x...")

        # Free endpoint (no payment)
        name = client.clean_merchant("GRAB* RIDE 09 APR")

        # Paid endpoint (auto Pays via x402)
        result = client.parse_pdf(pdf_bytes, bank="dbs")
    """

    def __init__(
        self,
        wallet_private_key: Optional[str] = None,
        base_url: str = BASE_URL,
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        if wallet_private_key:
            if not HAS_X402:
                raise ImportError(
                    "x402 package not installed. Run: pip install 'python-x402[evm]>=0.2.0'"
                )
            self.x402 = X402Client(
                private_key=wallet_private_key,
                network=NETWORK,
                asset=USDC_ASSET,
            )
        else:
            self.x402 = None

        self._client = httpx.Client(timeout=timeout)

    # ── Free Endpoints ─────────────────────────────────────────────────────────

    def clean_merchant(self, description: str) -> dict:
        """
        FREE — Clean a raw bank transaction description to a merchant name.
        No x402 payment required.

        Args:
            description: Raw transaction description, e.g. "GRAB* RIDE 09 APR"

        Returns:
            {"cleaned": "Grab", "original": "GRAB* RIDE 09 APR"}
        """
        resp = self._client.get(
            f"{self.base_url}/merchant/clean",
            params={"description": description},
        )
        resp.raise_for_status()
        return resp.json()

    def batch_clean_merchants(self, descriptions: list[str]) -> dict:
        """
        FREE for ≤20 items — Clean up to 100 raw transaction descriptions.
        No x402 payment for ≤20 items.

        Args:
            descriptions: List of raw transaction descriptions

        Returns:
            {"cleaned": [{"original": "...", "cleaned": "..."}, ...]}
        """
        resp = self._client.get(
            f"{self.base_url}/merchant/batch-clean",
            params={"descriptions": descriptions},
        )
        resp.raise_for_status()
        return resp.json()

    def list_holidays(self, year: int = 2026) -> dict:
        """FREE — Singapore public holidays for a given year."""
        resp = self._client.get(f"{self.base_url}/holidays/singapore", params={"year": year})
        resp.raise_for_status()
        return resp.json()

    # ── Paid Endpoints: Bank Parsing ───────────────────────────────────────────

    def parse_pdf(self, pdf_bytes: bytes, bank: str) -> dict:
        """
        Parse a bank statement PDF. Supports 9 Singapore banks.
        Banks: dbs, posb, ocbc, uob, citi, maybank, standchart, trust, boc

        Args:
            pdf_bytes: Raw PDF file bytes
            bank: Bank code (lowercase)

        Returns:
            Structured JSON with accounts, transactions, balances
        """
        files = {"file": ("statement.pdf", pdf_bytes, "application/pdf")}
        data = {"bank": bank}
        return self._post_multipart("/parse/" + bank, files, data)

    # ── Paid Endpoints: AI Analysis ─────────────────────────────────────────────

    def extract_transactions(self, transactions: list[dict]) -> dict:
        """
        AI-powered entity extraction + categorization from bank transactions.
        Takes raw transactions, returns merchant names, categories, flags.

        Args:
            transactions: List of {"date": "YYYY-MM-DD", "description": "...", "amount": 0.00, "type": "debit/credit"}

        Returns:
            {"categorized": [...], "summary": {...}}
        """
        return self._post_json("/extract/transactions", {"transactions": transactions})

    def summary(self, transactions: list[dict]) -> dict:
        """Financial summary from transactions."""
        return self._post_json("/summary", {"transactions": transactions})

    def spending_report(self, transactions: list[dict]) -> dict:
        """Detailed expense report with benchmarks vs Singapore household averages."""
        return self._post_json("/report/spending", {"transactions": transactions})

    def cash_flow_report(self, transactions: list[dict]) -> dict:
        """Cash flow analysis."""
        return self._post_json("/report/cash-flow", {"transactions": transactions})

    def subscriptions_report(self, transactions: list[dict]) -> dict:
        """Detect recurring subscriptions."""
        return self._post_json("/report/subscriptions", {"transactions": transactions})

    def tax_report(self, transactions: list[dict]) -> dict:
        """Tax report from transactions."""
        return self._post_json("/report/tax", {"transactions": transactions})

    def invoice(self, transactions: list[dict], issue_date: str = None) -> dict:
        """Generate invoice PDF from transactions."""
        payload = {"transactions": transactions}
        if issue_date:
            payload["issue_date"] = issue_date
        return self._post_json("/invoice", payload)

    def financial_insights(self, transactions: list[dict]) -> dict:
        """AI-powered financial insights."""
        return self._post_json("/financial-insights", {"transactions": transactions})

    # ── Paid Endpoints: Singapore Financial Tools ─────────────────────────────

    def cpf_calculator(
        self,
        birth_date: str,
        cpf_balance: float,
        monthly_contribution: float = 0,
        current_age: int = None,
    ) -> dict:
        """
        CPF projection at retirement.
        Args:
            birth_date: "YYYY-MM-DD"
            cpf_balance: Current CPF OA + SA balance (SGD)
            monthly_contribution: Optional monthly contribution
            current_age: Optional current age
        """
        payload = {
            "birth_date": birth_date,
            "cpf_balance": cpf_balance,
        }
        if monthly_contribution:
            payload["monthly_contribution"] = monthly_contribution
        if current_age:
            payload["current_age"] = current_age
        return self._post_json("/cpf/calculator", payload)

    def srs_calculator(
        self,
        annual_income: float,
        age: int,
        citizenship: str = "citizen",
        srs_balance: float = 0,
    ) -> dict:
        """
        SRS (Supplementary Retirement Scheme) tax optimization.
        Args:
            annual_income: Gross annual income (SGD)
            age: Current age
            citizenship: "citizen", "pr", or "foreign"
            srs_balance: Current SRS balance
        """
        return self._post_json("/srs/calculator", {
            "annual_income": annual_inour,
            "age": age,
            "citizenship": citizenship,
            "srs_balance": srs_balance,
        })

    def hdb_resale(
        self,
        town: str,
        flat_type: str,
        floor_level: int = 5,
        lease_start: str = None,
        storey: str = "mid",
    ) -> dict:
        """
        HDB resale price estimate.
        Args:
            town: HDB town name (e.g. "Tampines", "Jurong West")
            flat_type: "1-room", "2-room", "3-room", "4-room", "5-room", "executive"
            floor_level: Floor number
            lease_start: "YYYY-MM-DD" (optional, defaults to earliest)
            storey: "low", "mid", "high"
        """
        payload = {
            "town": town,
            "flat_type": flat_type,
            "floor_level": floor_level,
            "storey": storey,
        }
        if lease_start:
            payload["lease_start"] = lease_start
        return self._post_json("/hdb/resale", payload)

    def bto_affordability(
        self,
        flat_type: str,
        estate: str,
        household_income: float,
        cpf_balance: float,
    ) -> dict:
        """
        BTO affordability calculator.
        Args:
            flat_type: "2-room", "3-room", "4-room", "5-room"
            estate: Estate name (e.g. "Bukit Merah", "Tampines")
            household_income: Gross monthly household income
            cpf_balance: Combined CPF OA balance
        """
        return self._post_json("/bto/affordability", {
            "flat_type": flat_type,
            "estate": estate,
            "household_income": household_income,
            "cpf_balance": cpf_balance,
        })

    def property_tax(self, annual_value: float, owner_type: str = "citizen") -> dict:
        """
        IRAS progressive property tax calculator.
        Args:
            annual_value: Annual value of property (SGD)
            owner_type: "citizen", "pr", " foreigner"
        """
        return self._post_json("/property/tax", {
            "annual_value": annual_value,
            "owner_type": owner_type,
        })

    def absd_calculator(
        self,
        purchase_price: float,
        residential_status: str = "citizen",
        current_properties_value: float = 0,
    ) -> dict:
        """
        ABSD (Additional Buyer's Stamp Duty) calculator.
        Args:
            purchase_price: Property purchase price (SGD)
            residential_status: "citizen", "pr", "foreigner"
            current_properties_value: Current market value of all owned properties
        """
        return self._post_json("/property/absd", {
            "purchase_price": purchase_price,
            "residential_status": residential_status,
            "current_properties_value": current_properties_value,
        })

    def sgx_stock(self, ticker: str) -> dict:
        """
        Complete SGX stock profile.
        Args:
            ticker: SGX ticker (e.g. "DBS", "UOB", "OCBC")
        """
        return self._post_json("/sgx/stock", {"ticker": ticker})

    def sgx_portfolio(self, tickers: list[str]) -> dict:
        """
        Batch SGX stock lookup (up to 20 tickers).
        More efficient than calling /sgx/stock N times.
        """
        return self._post_json("/sgx/portfolio", {"tickers": tickers})

    def sgx_price(self, ticker: str) -> dict:
        """Real-time SGX stock price."""
        return self._post_json("/sgx/price", {"ticker": ticker})

    def coe_prices(self) -> dict:
        """Latest COE premiums for all 5 categories."""
        return self._post_json("/coe/prices", {})

    def fire(
        self,
        current_age: int,
        current_savings: float,
        monthly_expenses: float,
        target_age: int = 55,
    ) -> dict:
        """
        Singapore FIRE calculator.
        Args:
            current_age: Current age
            current_savings: Total savings (CPF OA + liquid)
            monthly_expenses: Monthly expenses
            target_age: Target retirement age
        """
        return self._post_json("/fire", {
            "current_age": current_age,
            "current_savings": current_savings,
            "monthly_expenses": monthly_expenses,
            "target_age": target_age,
        })

    def refinance(self, outstanding_balance: float, property_value: float, loan_type: str = "hdb") -> dict:
        """
        Singapore mortgage refinance analyzer.
        Compares current bank vs HDB vs best alternative.
        """
        return self._post_json("/refinance", {
            "outstanding_balance": outstanding_balance,
            "property_value": property_value,
            "loan_type": loan_type,
        })

    def financial_health_score(self, transactions: list[dict]) -> dict:
        """Calculate Singapore financial health score."""
        return self._post_json("/financial-health", {"transactions": transactions})

    # ── Internal Helpers ───────────────────────────────────────────────────────

    def _post_json(self, path: str, payload: dict) -> dict:
        """Make a paid x402 request (auto-handles 402 payment flow)."""
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        if self.x402:
            resp = self.x402.post(url, json=payload, headers=headers)
        else:
            resp = self._client.post(url, json=payload, headers=headers)

        if resp.status_code == 402:
            payment = self._handle_payment_required(resp)
            raise PaymentRequiredError(payment)
        resp.raise_for_status()
        return resp.json()

    def _post_multipart(self, path: str, files: dict, data: dict) -> dict:
        """Make a paid x402 multipart request."""
        url = f"{self.base_url}{path}"
        if self.x402:
            resp = self.x402.post(url, data=data, files=files)
        else:
            resp = self._client.post(url, data=data, files=files)
        if resp.status_code == 402:
            payment = self._handle_payment_required(resp)
            raise PaymentRequiredError(payment)
        resp.raise_for_status()
        return resp.json()

    def _handle_payment_required(self, resp: httpx.Response) -> dict:
        """Parse 402 response and return payment requirements."""
        return resp.json()


class PaymentRequiredError(Exception):
    """Raised when an endpoint requires payment (HTTP 402)."""
    def __init__(self, payment_info: dict):
        self.payment_info = payment_info
        super().__init__(f"Payment required: {payment_info}")


# ── Quick Demo ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    client = FinancialDataClient(
        wallet_private_key=os.environ.get("WALLET_PRIVATE_KEY")
    )

    # Free endpoint — no wallet needed
    print("=== Free: Merchant Cleaning ===")
    result = client.clean_merchant("DBSS MART F&B PL")
    print(f"  {result}")

    print("\n=== Free: Singapore Holidays ===")
    holidays = client.list_holidays(2026)
    print(f"  Found {len(holidays.get('holidays', []))} holidays")
