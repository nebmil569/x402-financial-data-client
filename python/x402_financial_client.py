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


BASE_URL = os.getenv("X402_API_URL", "https://x402-financial-api.life.conway.tech")
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
            "annual_income": annual_income,
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

    # ── NEW Endpoints: Missing from client ───────────────────────────────────

    def invest_dca(
        self,
        monthly_amount: float,
        years: int,
        etf_return_override: float = None,
        cpf_oa_override: float = None,
        ssb_rate_override: float = None,
    ) -> dict:
        """
        Singapore Dollar Cost Averaging (DCA) simulator.
        Compares monthly investing into IWLU (iShares MSCI World UCITS ETF)
        vs CPF OA vs SSB with year-by-year projections.

        Args:
            monthly_amount: SGD monthly investment (50-50000)
            years: Projection period (1-30)
            etf_return_override: Override ETF expected return % (default 6%)
            cpf_oa_override: Override CPF OA rate % (default 2.5%)
            ssb_rate_override: Override SSB rate % (default 3%)
        """
        payload = {"monthly_amount": monthly_amount, "years": years}
        if etf_return_override is not None:
            payload["etf_return_override"] = etf_return_override
        if cpf_oa_override is not None:
            payload["cpf_oa_override"] = cpf_oa_override
        if ssb_rate_override is not None:
            payload["ssb_rate_override"] = ssb_rate_override
        return self._post_json("/invest/dca", payload)

    def tax_optimization(
        self,
        annual_income_sgd: float,
        cpf_contributions_sgd: float = 0,
        srs_contributions_sgd: float = 0,
        donations_sgd: float = 0,
        investment_losses_sgd: float = 0,
        home_owned: bool = False,
        age: int = 35,
        employment_type: str = "employed",
    ) -> dict:
        """
        AI-powered Singapore income tax optimization strategies.
        Analyzes income, CPF, SRS, investments, and donations to provide
        actionable tax reduction strategies specific to Singapore IRAS rules.

        Args:
            annual_income_sgd: Gross annual income (SGD)
            cpf_contributions_sgd: Annual CPF employee contributions
            srs_contributions_sgd: Annual SRS contributions (cap $15,300/yr for residents)
            donations_sgd: Annual donations (250% tax deduction)
            investment_losses_sgd: Investment losses to offset gains
            home_owned: Whether user owns a property
            age: Age for specific age-related reliefs
            employment_type: "employed" | "self-employed" | "both"
        """
        return self._post_json("/tax/optimization", {
            "annual_income_sgd": annual_income_sgd,
            "cpf_contributions_sgd": cpf_contributions_sgd,
            "srs_contributions_sgd": srs_contributions_sgd,
            "donations_sgd": donations_sgd,
            "investment_losses_sgd": investment_losses_sgd,
            "home_owned": home_owned,
            "age": age,
            "employment_type": employment_type,
        })

    def school_nearby(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 2.0,
        postal_code: str = None,
    ) -> dict:
        """
        Singapore primary school finder and proximity lookup.
        Given lat/lon or postal code, returns nearby schools ranked by distance.

        Args:
            latitude: Latitude of location
            longitude: Longitude of location
            radius_km: Search radius in km (default 2.0, max 10)
            postal_code: Optional postal code (alternative to lat/lon)
        """
        payload = {"latitude": latitude, "longitude": longitude, "radius_km": radius_km}
        if postal_code:
            payload["postal_code"] = postal_code
        return self._post_json("/school/nearby", payload)

    def school_nearby_secondary(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 2.0,
        postal_code: str = None,
    ) -> dict:
        """
        Singapore secondary school finder and proximity lookup.
        Given lat/lon or postal code, returns nearby secondary schools ranked by distance.
        """
        payload = {"latitude": latitude, "longitude": longitude, "radius_km": radius_km}
        if postal_code:
            payload["postal_code"] = postal_code
        return self._post_json("/school/nearby/secondary", payload)

    def retirement_community(
        self,
        location: str = None,
        budget: float = None,
        priority: str = "overall",
    ) -> dict:
        """
        Singapore Retirement Community Analyzer — ranks 8 Singapore neighborhoods
        for retirement suitability across amenities, healthcare, transport, cost.

        Args:
            location: Preferred location (optional)
            budget: Monthly budget in SGD (optional)
            priority: "overall" | "healthcare" | "affordability" | "transport"
        """
        payload = {"priority": priority}
        if location:
            payload["location"] = location
        if budget is not None:
            payload["budget"] = budget
        return self._post_json("/retirement/community", payload)

    def goal_plan(
        self,
        goal_type: str,
        goal_amount_sgd: float,
        time_horizon_years: float,
        current_savings_sgd: float = 0,
        monthly_contribution_sgd: float = 0,
        employment_income_sgd: float = 0,
        age: int = 30,
    ) -> dict:
        """
        Singapore financial goal planner — maps savings targets to actionable monthly plans.

        Args:
            goal_type: "emergency_fund" | "home_down_payment" | "retirement" | "education" |
                       "wedding" | "car" | "vacation" | "investment" | "custom"
            goal_amount_sgd: Target amount in SGD
            time_horizon_years: Years to reach goal
            current_savings_sgd: Money already saved/invested
            monthly_contribution_sgd: How much you can put aside per month
            employment_income_sgd: Annual employment income (for CPF/tax context)
            age: Current age (for retirement-specific calcs)
        """
        return self._post_json("/goal/plan", {
            "goal_type": goal_type,
            "goal_amount_sgd": goal_amount_sgd,
            "time_horizon_years": time_horizon_years,
            "current_savings_sgd": current_savings_sgd,
            "monthly_contribution_sgd": monthly_contribution_sgd,
            "employment_income_sgd": employment_income_sgd,
            "age": age,
        })

    def mortgage_compare(
        self,
        property_price_sgd: float,
        loan_type: str = "compare",
        cpf_oa_balance_sgd: float = 0,
        annual_household_income_sgd: float = 0,
        loan_tenure_years: int = 25,
    ) -> dict:
        """
        Singapore mortgage comparison — HDB bank loan (2.6%%) vs private bank vs best alternative.

        Args:
            property_price_sgd: Property price in SGD
            loan_type: "compare" | "hdb" | "bank"
            cpf_oa_balance_sgd: CPF OA balance (optional)
            annual_household_income_sgd: Annual household income (optional)
            loan_tenure_years: Loan tenure in years
        """
        return self._post_json("/mortgage/compare", {
            "property_price_sgd": property_price_sgd,
            "loan_type": loan_type,
            "cpf_oa_balance_sgd": cpf_oa_balance_sgd,
            "annual_household_income_sgd": annual_household_income_sgd,
            "loan_tenure_years": loan_tenure_years,
        })

    def insurance_analyze(
        self,
        age: int,
        annual_income: float,
        coverage_need: str = "comprehensive",
        existing_policies: list = None,
    ) -> dict:
        """
        Singapore multi-risk insurance coverage analyzer.
        Analyzes life, health, critical illness, and personal accident coverage gaps.

        Args:
            age: Current age
            annual_income: Annual income for coverage calculation
            coverage_need: "basic" | "standard" | "comprehensive"
            existing_policies: List of existing policy summaries
        """
        payload = {
            "age": age,
            "annual_income": annual_income,
            "coverage_need": coverage_need,
        }
        if existing_policies:
            payload["existing_policies"] = existing_policies
        return self._post_json("/insurance/analyze", payload)

    def property_rental_yield(
        self,
        property_value: float,
        monthly_rental: float,
        property_type: str = "condo",
    ) -> dict:
        """
        Singapore property rental yield calculator.
        Returns gross yield % and net yield % with expense breakdown.

        Args:
            property_value: Current market value in SGD
            monthly_rental: Monthly rental income in SGD
            property_type: "condo" | "hdb" | "landed"
        """
        return self._post_json("/property/rental-yield", {
            "property_value": property_value,
            "monthly_rental": monthly_rental,
            "property_type": property_type,
        })

    def invest_grow(
        self,
        initial_amount: float,
        years: int,
        top_up_annual: float = 0,
        ssb_rate_override: float = None,
        tbill_rate_override: float = None,
    ) -> dict:
        """
        Singapore compound growth comparison calculator.
        Compares how a starting amount grows across CPF OA, CPF SA, SSB, and T-bills.
        Shows year-by-year projections, breakeven points, and total interest earned.

        Args:
            initial_amount: SGD starting amount
            years: Projection period (1-50)
            top_up_annual: Annual top-up amount in SGD (optional)
            ssb_rate_override: Override SSB rate % (optional)
            tbill_rate_override: Override T-bill rate % (optional)
        """
        payload = {"initial_amount": initial_amount, "years": years}
        if top_up_annual:
            payload["top_up_annual"] = top_up_annual
        if ssb_rate_override is not None:
            payload["ssb_rate_override"] = ssb_rate_override
        if tbill_rate_override is not None:
            payload["tbill_rate_override"] = tbill_rate_override
        return self._post_json("/invest/grow", payload)

    def tax_corporate(
        self,
        revenue: float,
        allowable_expenses: float = 0,
        capital_allowances: float = 0,
        tax_exemptions: float = 0,
    ) -> dict:
        """
        Singapore corporate income tax calculator for sole props/partnerships.

        Args:
            revenue: Total revenue for the financial year (SGD)
            allowable_expenses: Total allowable business expenses
            capital_allowances: Capital allowances claimed
            tax_exemptions: Tax-exempt income (e.g. start-up exemptions)
        """
        return self._post_json("/tax/corporate", {
            "revenue": revenue,
            "allowable_expenses": allowable_expenses,
            "capital_allowances": capital_allowances,
            "tax_exemptions": tax_exemptions,
        })

    def invoice_generate(
        self,
        company_name: str,
        gst_registration: str = "non-gst",
        issue_date: str = None,
        due_date: str = None,
        client_name: str = None,
        client_address: str = None,
        line_items: list = None,
        amount: float = None,
        description: str = None,
    ) -> dict:
        """
        Generate a professional Singapore GST-compliant invoice PDF.

        Args:
            company_name: Your company/business name
            gst_registration: "gst" | "non-gst" (default)
            issue_date: Invoice issue date YYYY-MM-DD (default: today)
            due_date: Payment due date YYYY-MM-DD
            client_name: Client company name
            client_address: Client address
            line_items: List of {"description": str, "quantity": int, "unit_price": float}
            amount: Simple mode — total amount (alternative to line_items)
            description: Simple mode — item description (alternative to line_items)
        """
        payload = {
            "company_name": company_name,
            "gst_registration": gst_registration,
        }
        if issue_date:
            payload["issue_date"] = issue_date
        if due_date:
            payload["due_date"] = due_date
        if client_name:
            payload["client_name"] = client_name
        if client_address:
            payload["client_address"] = client_address
        if line_items:
            payload["line_items"] = line_items
        if amount is not None:
            payload["amount"] = amount
        if description:
            payload["description"] = description
        return self._post_json("/invoice/generate", payload)

    def cpf_topup(
        self,
        cpf_balance: float,
        annual_income: float,
        age: int,
        cpf_account: str = "sa",
        topup_amount: float = None,
    ) -> dict:
        """
        Singapore CPF top-up optimization analyzer.
        Calculates optimal CPF top-up amounts and retirement benefits.

        Args:
            cpf_balance: Current CPF SA or RA balance (SGD)
            annual_income: Gross annual employment income (SGD)
            age: Current age
            cpf_account: "sa" | "ra" (Special Account or Retirement Account)
            topup_amount: Desired top-up amount (optional — calculates optimal)
        """
        payload = {
            "cpf_balance": cpf_balance,
            "annual_income": annual_income,
            "age": age,
            "cpf_account": cpf_account,
        }
        if topup_amount is not None:
            payload["topup_amount"] = topup_amount
        return self._post_json("/cpf/topup", payload)

    def bto_topup_suggestions(
        self,
        flat_type: str,
        estate: str,
        household_income: float,
        cpf_balance: float,
        grant_eligibility: str = "standard",
    ) -> dict:
        """
        Singapore BTO top-up and grants optimization analyzer.
        Suggests how to maximize housing grants and CPF usage for BTO flats.

        Args:
            flat_type: "2-room" | "3-room" | "4-room" | "5-room"
            estate: Estate name (e.g. "Tampines", "Jurong West")
            household_income: Gross monthly household income (SGD)
            cpf_balance: Combined CPF OA balance (SGD)
            grant_eligibility: "standard" | "enhanced" | "first-timer"
        """
        return self._post_json("/bto/topup-suggestions", {
            "flat_type": flat_type,
            "estate": estate,
            "household_income": household_income,
            "cpf_balance": cpf_balance,
            "grant_eligibility": grant_eligibility,
        })

    def driving_demerit(
        self,
        offence_date: str,
        points: int,
        licence_type: str = "car",
        years_holding_license: int = 3,
        current_demerit_points: int = 0,
    ) -> dict:
        """
        Singapore Driving License Demerit Points Analyzer.

        Args:
            offence_date: Date of traffic offence (YYYY-MM-DD)
            points: Demerit points received
            licence_type: "car" | "motorcycle" | "bus"
            years_holding_license: Years with full license
            current_demerit_points: Existing points on license
        """
        return self._post_json("/driving/demerit", {
            "offence_date": offence_date,
            "points": points,
            "licence_type": licence_type,
            "years_holding_license": years_holding_license,
            "current_demerit_points": current_demerit_points,
        })

    def salary_market_rates(
        self,
        job_title: str,
        years_experience: int,
        industry: str = "general",
        education_level: str = "degree",
    ) -> dict:
        """
        Singapore salary market rate estimator.
        Compares income against Singapore workforce benchmarks by job title and experience.

        Args:
            job_title: Job title or profession
            years_experience: Years of relevant experience
            industry: Industry sector (default: "general")
            education_level: "secondary" | "diploma" | "degree" | "master" | "phd"
        """
        return self._post_json("/salary/market-rates", {
            "job_title": job_title,
            "years_experience": years_experience,
            "industry": industry,
            "education_level": education_level,
        })

    def singapore_benefits(
        self,
        age: int,
        citizenship: str,
        household_income: float,
        housing_status: str = "renting",
        has_children: bool = False,
    ) -> dict:
        """
        Check eligibility for Singapore government assistance schemes.
        Includes ComCare, GST Voucher, SURE, CDC vouchers, and more.

        Args:
            age: Current age
            citizenship: "citizen" | "pr"
            household_income: Gross monthly household income (SGD)
            housing_status: "own" | "renting" | "sublet"
            has_children: Whether there are children in household
        """
        return self._post_json("/singapore/benefits", {
            "age": age,
            "citizenship": citizenship,
            "household_income": household_income,
            "housing_status": housing_status,
            "has_children": has_children,
        })

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
