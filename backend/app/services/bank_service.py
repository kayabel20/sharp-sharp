"""
Bank statement analysis service — Mono raw data + internal analysis engine.

How it works:
1. Mono/Okra connects to the customer's bank account (with consent)
2. We pull raw transactions for the last 6 months
3. OUR OWN CODE analyzes the transactions — we don't outsource analysis to Indicina
4. We extract: salary patterns, spending categories, risk flags, affordability

This gives us full control over the scoring logic and feature engineering.
"""
import logging
import re
from datetime import datetime, date as date_type, timedelta
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.loan import LoanApplication
from app.models.integration import BankStatement, BankTransaction
from app.integrations.mono import MonoClient

logger = logging.getLogger(__name__)

# ── Known patterns for transaction categorization ──
SALARY_KEYWORDS = [
    "salary", "sal", "payroll", "wage", "allowance", "ippis",
    "remuneration", "monthly pay", "staff salary",
]
GAMBLING_KEYWORDS = [
    "bet9ja", "sportybet", "nairabet", "betking", "1xbet",
    "betway", "merrybet", "betland", "accessbet", "lottonaija",
    "bet", "casino", "lotto", "stake", "odds",
]
LENDER_KEYWORDS = [
    "fairmoney", "carbon", "branch", "palmcredit", "renmoney",
    "aella", "quickcheck", "migo", "paylater", "sokoloan",
    "okash", "kcredit", "newcredit", "9credit", "lcredit",
    "loan", "credit", "lending",
]
TRANSFER_KEYWORDS = ["transfer", "nip", "pos", "atm", "ussd"]


class BankStatementService:
    """
    Pulls raw bank data from Mono, then runs our own internal analysis.
    No third-party analysis engine — we own the logic.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.mono = MonoClient()

    async def analyze(self, user: User, application: LoanApplication) -> dict:
        """
        Full bank analysis pipeline:
        1. Pull raw transactions from Mono
        2. Categorize each transaction
        3. Detect salary pattern
        4. Calculate cash flow metrics
        5. Flag risk indicators
        6. Compute affordability
        """

        # Step 1: Pull raw data from Mono
        raw_data = None
        try:
            mono_account_id = getattr(user, "mono_account_id", None)
            if mono_account_id:
                raw_data = await self.mono.get_account_statement(
                    account_id=mono_account_id,
                    period="last6months",
                )
        except Exception as e:
            logger.warning(f"Mono pull failed for user {user.id}: {e}")

        if not raw_data or not raw_data.get("raw_response"):
            logger.info(f"No bank data for user {user.id}, returning empty analysis")
            return self._empty_analysis()

        # Extract raw transactions from Mono response
        raw_transactions = (
            raw_data.get("raw_response", {})
            .get("data", {})
            .get("transactions", [])
        )

        if not raw_transactions:
            return self._empty_analysis()

        # Step 2: Categorize every transaction
        categorized = [self._categorize_transaction(txn) for txn in raw_transactions]

        # Step 3: Run our analysis engine
        analysis = self._run_analysis(categorized, raw_data)

        # Step 4: Save summary to DB (before transactions, so we have statement_id)
        stmt = BankStatement(
            user_id=user.id,
            application_id=application.id,
            provider="mono",
            provider_reference=raw_data.get("reference"),
            bank_name=raw_data.get("bank_name"),
            account_number=application.disbursement_account_number,
            account_name=raw_data.get("account_name"),
            period_start=analysis.get("period_start"),
            period_end=analysis.get("period_end"),
            months_covered=analysis["months_covered"],
            average_balance=analysis["average_balance"],
            average_monthly_credit=analysis["average_monthly_credit"],
            average_monthly_debit=analysis["average_monthly_debit"],
            highest_balance=analysis["highest_balance"],
            lowest_balance=analysis["lowest_balance"],
            salary_frequency=analysis["salary_frequency"],
            estimated_salary=analysis["estimated_salary"],
            salary_employer=analysis["salary_employer"],
            salary_day_of_month=analysis["salary_day_of_month"],
            recurring_credits_count=analysis["recurring_credits_count"],
            gambling_transactions=analysis["gambling_transaction_count"],
            loan_repayments_detected=analysis["loan_repayment_total"],
            other_lender_count=analysis["other_lender_count"],
            days_with_zero_balance=analysis["days_with_zero_balance"],
            overdraft_count=analysis["overdraft_count"],
            return_cheque_count=analysis.get("return_cheque_count", 0),
            net_monthly_income=analysis["net_monthly_income"],
            net_monthly_expenses=analysis["net_monthly_expenses"],
            disposable_income=analysis["disposable_income"],
            affordability_score=analysis["affordability_score"],
            transaction_count=len(categorized),
            status="success",
        )
        self.db.add(stmt)
        await self.db.flush()

        # Step 5: Save individual transactions linked to statement
        for txn in categorized:
            bank_txn = BankTransaction(
                statement_id=stmt.id,
                user_id=user.id,
                transaction_date=txn["date"],
                amount=txn["amount"],
                transaction_type=txn["type"],
                narration=txn["narration"],
                category=txn["category"],
                is_salary=txn["is_salary"],
                is_recurring=txn.get("is_recurring", False),
            )
            self.db.add(bank_txn)
        await self.db.flush()

        logger.info(
            f"Bank analysis complete for user {user.id}: "
            f"{len(categorized)} txns, salary={analysis['estimated_salary']}, "
            f"affordability={analysis['affordability_score']}"
        )

        return analysis

    # ═══════════════════════════════════════════════════════
    # TRANSACTION CATEGORIZATION — Our own logic
    # ═══════════════════════════════════════════════════════

    def _categorize_transaction(self, txn: dict) -> dict:
        """
        Categorize a single transaction by reading its narration.
        This is the core bank analysis — pattern matching on narrations
        to understand what each transaction represents.
        """
        narration = (txn.get("narration") or txn.get("description") or "").lower().strip()
        amount = abs(txn.get("amount", 0))
        # Mono returns amounts in kobo (minor units)
        if amount > 100_000_000:  # likely in kobo
            amount = amount / 100
        txn_type = txn.get("type", "").lower()  # "credit" or "debit"

        # Date parsing
        raw_date = txn.get("date") or txn.get("created_at") or ""
        try:
            txn_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
        except (ValueError, AttributeError):
            txn_date = date_type.today()

        # ── Categorization rules ──

        is_salary = False
        is_gambling = False
        is_loan_repayment = False
        category = "other"

        # Salary detection
        if txn_type == "credit":
            if any(kw in narration for kw in SALARY_KEYWORDS):
                is_salary = True
                category = "salary"
            elif amount >= 30_000 and self._looks_like_salary(narration):
                # Large recurring credits that look like salary
                is_salary = True
                category = "salary"
            else:
                category = "income_other"

        # Gambling detection
        if any(kw in narration for kw in GAMBLING_KEYWORDS):
            is_gambling = True
            category = "gambling"

        # Loan repayment / other lender detection
        if txn_type == "debit" and any(kw in narration for kw in LENDER_KEYWORDS):
            is_loan_repayment = True
            category = "loan_repayment"

        # Other debit categories
        if txn_type == "debit" and category == "other":
            if any(kw in narration for kw in TRANSFER_KEYWORDS):
                category = "transfer"
            elif "airtime" in narration or "recharge" in narration or "mtn" in narration:
                category = "airtime"
            elif "food" in narration or "restaurant" in narration or "eat" in narration:
                category = "food"
            elif "transport" in narration or "uber" in narration or "bolt" in narration:
                category = "transport"
            elif "rent" in narration or "house" in narration:
                category = "rent"
            elif "school" in narration or "tuition" in narration or "fees" in narration:
                category = "education"

        return {
            "date": txn_date,
            "amount": amount,
            "type": txn_type,
            "narration": narration,
            "category": category,
            "is_salary": is_salary,
            "is_gambling": is_gambling,
            "is_loan_repayment": is_loan_repayment,
        }

    def _looks_like_salary(self, narration: str) -> bool:
        """Heuristic: does this credit narration look like a salary payment?"""
        # Company payment patterns
        company_patterns = [
            r"ltd", r"limited", r"plc", r"inc", r"corp",
            r"enterprise", r"services", r"group",
        ]
        return any(re.search(p, narration) for p in company_patterns)

    # ═══════════════════════════════════════════════════════
    # ANALYSIS ENGINE — Our own calculations
    # ═══════════════════════════════════════════════════════

    def _run_analysis(self, transactions: list[dict], raw_data: dict) -> dict:
        """
        Run the full internal analysis on categorized transactions.
        This is where all the intelligence lives — not in Mono, not in Indicina, HERE.
        """
        if not transactions:
            return self._empty_analysis()

        credits = [t for t in transactions if t["type"] == "credit"]
        debits = [t for t in transactions if t["type"] == "debit"]

        # ── Date range ──
        dates = [t["date"] for t in transactions]
        period_start = min(dates)
        period_end = max(dates)
        total_days = max((period_end - period_start).days, 1)
        months_covered = max(total_days / 30, 1)

        # ── Basic cash flow ──
        total_credit = sum(t["amount"] for t in credits)
        total_debit = sum(t["amount"] for t in debits)
        avg_monthly_credit = total_credit / months_covered
        avg_monthly_debit = total_debit / months_covered

        # ── Balance tracking ──
        # Simulate running balance from transactions
        running_balance = 0
        daily_balances = defaultdict(float)
        for txn in sorted(transactions, key=lambda t: t["date"]):
            if txn["type"] == "credit":
                running_balance += txn["amount"]
            else:
                running_balance -= txn["amount"]
            daily_balances[txn["date"]] = running_balance

        balance_values = list(daily_balances.values()) or [0]
        avg_balance = sum(balance_values) / len(balance_values)
        highest_balance = max(balance_values)
        lowest_balance = min(balance_values)
        zero_balance_days = sum(1 for b in balance_values if b <= 0)
        overdraft_count = sum(1 for b in balance_values if b < 0)

        # ── Salary detection ──
        salary_txns = [t for t in transactions if t["is_salary"]]
        salary_result = self._detect_salary_pattern(salary_txns)

        # ── Gambling analysis ──
        gambling_txns = [t for t in transactions if t["is_gambling"]]
        gambling_count = len(gambling_txns)
        gambling_total = sum(t["amount"] for t in gambling_txns)

        # ── Loan / other lender analysis ──
        loan_txns = [t for t in transactions if t["is_loan_repayment"]]
        loan_repayment_total = sum(t["amount"] for t in loan_txns)
        loan_repayment_monthly = loan_repayment_total / months_covered

        # Count unique lenders from narrations
        lender_names = set()
        for t in loan_txns:
            for kw in LENDER_KEYWORDS[:10]:  # Check actual lender names only
                if kw in t["narration"]:
                    lender_names.add(kw)
        other_lender_count = len(lender_names)

        # ── Recurring credits (non-salary regular income) ──
        recurring = self._find_recurring_credits(credits)

        # ── Spending categories breakdown ──
        category_totals = defaultdict(float)
        for t in debits:
            category_totals[t["category"]] += t["amount"]

        # ── Affordability calculation ──
        net_monthly_income = avg_monthly_credit
        net_monthly_expenses = avg_monthly_debit
        disposable_income = net_monthly_income - net_monthly_expenses

        # Affordability score (0-100)
        # Factors: disposable income ratio, balance stability, gambling, lenders
        affordability_score = self._calculate_affordability_score(
            disposable_income=disposable_income,
            net_income=net_monthly_income,
            zero_balance_days=zero_balance_days,
            gambling_count=gambling_count,
            other_lender_count=other_lender_count,
            months_covered=months_covered,
        )

        return {
            "provider": "mono",
            "period_start": str(period_start),
            "period_end": str(period_end),
            "months_covered": round(months_covered),
            "transaction_count": len(transactions),
            "average_balance": round(avg_balance, 2),
            "average_monthly_credit": round(avg_monthly_credit, 2),
            "average_monthly_debit": round(avg_monthly_debit, 2),
            "highest_balance": round(highest_balance, 2),
            "lowest_balance": round(lowest_balance, 2),
            "days_with_zero_balance": zero_balance_days,
            "overdraft_count": overdraft_count,
            # Salary
            "estimated_salary": salary_result["amount"],
            "salary_frequency": salary_result["frequency"],
            "salary_employer": salary_result["employer"],
            "salary_day_of_month": salary_result["day_of_month"],
            "salary_confidence": salary_result["confidence"],
            # Risk flags
            "gambling_transaction_count": gambling_count,
            "gambling_total_amount": round(gambling_total, 2),
            "loan_repayment_total": round(loan_repayment_monthly, 2),
            "other_lender_count": other_lender_count,
            "other_lender_names": list(lender_names),
            # Income
            "recurring_credits_count": len(recurring),
            "net_monthly_income": round(net_monthly_income, 2),
            "net_monthly_expenses": round(net_monthly_expenses, 2),
            "disposable_income": round(disposable_income, 2),
            "affordability_score": affordability_score,
            # Categories
            "spending_categories": dict(category_totals),
        }

    def _detect_salary_pattern(self, salary_txns: list[dict]) -> dict:
        """
        Detect salary pattern from transactions flagged as salary.
        Looks for: consistent amount, consistent timing, employer name.
        """
        if not salary_txns:
            return {
                "amount": None, "frequency": None,
                "employer": None, "day_of_month": None, "confidence": 0,
            }

        # Group by month to find recurring pattern
        monthly_salaries = defaultdict(list)
        for t in salary_txns:
            month_key = t["date"].strftime("%Y-%m")
            monthly_salaries[month_key].append(t)

        # Most common salary amount (mode)
        amounts = [t["amount"] for t in salary_txns]
        # Find the most frequent amount (within 10% tolerance)
        amount_clusters = self._cluster_amounts(amounts)
        if not amount_clusters:
            return {
                "amount": None, "frequency": None,
                "employer": None, "day_of_month": None, "confidence": 0,
            }

        main_salary = amount_clusters[0]  # Largest cluster

        # Day of month
        days = [t["date"].day for t in salary_txns if abs(t["amount"] - main_salary["avg"]) / max(main_salary["avg"], 1) < 0.1]
        avg_day = round(sum(days) / len(days)) if days else None

        # Frequency
        months_with_salary = len(monthly_salaries)
        if months_with_salary >= 3:
            frequency = "monthly"
        elif months_with_salary >= 1:
            frequency = "irregular"
        else:
            frequency = None

        # Employer (most common narration source)
        narrations = [t["narration"] for t in salary_txns]
        employer = self._extract_employer(narrations)

        # Confidence based on consistency
        confidence = min(months_with_salary / 6, 1.0) * (0.9 if main_salary["count"] >= 3 else 0.5)

        return {
            "amount": round(main_salary["avg"], 2),
            "frequency": frequency,
            "employer": employer,
            "day_of_month": avg_day,
            "confidence": round(confidence, 2),
        }

    def _cluster_amounts(self, amounts: list[float]) -> list[dict]:
        """Cluster similar amounts together (within 10% tolerance)."""
        if not amounts:
            return []

        sorted_amounts = sorted(amounts, reverse=True)
        clusters = []
        used = set()

        for i, amt in enumerate(sorted_amounts):
            if i in used:
                continue
            cluster = [amt]
            used.add(i)
            for j, other in enumerate(sorted_amounts):
                if j in used:
                    continue
                if abs(amt - other) / max(amt, 1) < 0.10:  # Within 10%
                    cluster.append(other)
                    used.add(j)
            clusters.append({
                "avg": sum(cluster) / len(cluster),
                "count": len(cluster),
                "min": min(cluster),
                "max": max(cluster),
            })

        return sorted(clusters, key=lambda c: c["count"], reverse=True)

    def _extract_employer(self, narrations: list[str]) -> str | None:
        """Try to extract employer name from salary narrations."""
        # Count word frequency across narrations (excluding common words)
        stop_words = {"salary", "sal", "payroll", "payment", "transfer", "from", "the", "of", "for", "nip", "a", "to"}
        word_counts = defaultdict(int)

        for narration in narrations:
            words = narration.split()
            for word in words:
                clean = re.sub(r'[^a-z]', '', word.lower())
                if clean and len(clean) > 2 and clean not in stop_words:
                    word_counts[clean] += 1

        if not word_counts:
            return None

        # Most frequent non-stop word is likely the employer
        top_word = max(word_counts, key=word_counts.get)
        return top_word.title() if word_counts[top_word] >= 2 else None

    def _find_recurring_credits(self, credits: list[dict]) -> list[dict]:
        """Find non-salary recurring credits (e.g., side income, dividends)."""
        non_salary = [c for c in credits if not c["is_salary"]]

        # Group by similar amounts
        clusters = self._cluster_amounts([c["amount"] for c in non_salary])

        # Recurring = appears 3+ times with similar amount
        recurring = [c for c in clusters if c["count"] >= 3]
        return recurring

    def _calculate_affordability_score(self, disposable_income: float,
                                        net_income: float,
                                        zero_balance_days: int,
                                        gambling_count: int,
                                        other_lender_count: int,
                                        months_covered: float) -> int:
        """
        Calculate affordability score 0-100.
        Our own scoring logic — not from any third party.

        Factors:
        - Disposable income ratio (40% weight)
        - Balance stability / zero-balance days (25% weight)
        - Gambling activity (15% weight)
        - Other lender exposure (20% weight)
        """
        score = 0

        # Factor 1: Disposable income ratio (0-40 points)
        if net_income > 0:
            ratio = disposable_income / net_income
            if ratio >= 0.4:
                score += 40
            elif ratio >= 0.25:
                score += 30
            elif ratio >= 0.1:
                score += 20
            elif ratio > 0:
                score += 10

        # Factor 2: Balance stability (0-25 points)
        zero_pct = zero_balance_days / max(months_covered * 30, 1)
        if zero_pct == 0:
            score += 25
        elif zero_pct < 0.05:
            score += 20
        elif zero_pct < 0.15:
            score += 12
        elif zero_pct < 0.30:
            score += 5

        # Factor 3: Gambling (0-15 points, penalize gamblers)
        if gambling_count == 0:
            score += 15
        elif gambling_count <= 3:
            score += 8
        elif gambling_count <= 10:
            score += 3
        # else 0

        # Factor 4: Other lender exposure (0-20 points)
        if other_lender_count == 0:
            score += 20
        elif other_lender_count == 1:
            score += 15
        elif other_lender_count == 2:
            score += 10
        elif other_lender_count <= 4:
            score += 5
        # else 0

        return min(score, 100)

    def _empty_analysis(self) -> dict:
        return {
            "provider": "none",
            "months_covered": 0,
            "average_balance": None,
            "average_monthly_credit": None,
            "average_monthly_debit": None,
            "highest_balance": None,
            "lowest_balance": None,
            "estimated_salary": None,
            "salary_frequency": None,
            "salary_employer": None,
            "salary_day_of_month": None,
            "salary_confidence": 0,
            "gambling_transaction_count": 0,
            "gambling_total_amount": 0,
            "loan_repayment_total": 0,
            "other_lender_count": 0,
            "other_lender_names": [],
            "recurring_credits_count": 0,
            "net_monthly_income": 0,
            "net_monthly_expenses": 0,
            "disposable_income": 0,
            "affordability_score": 0,
            "days_with_zero_balance": 0,
            "overdraft_count": 0,
            "spending_categories": {},
        }
