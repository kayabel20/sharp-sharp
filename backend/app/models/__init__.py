"""All database models for the lending platform."""
from app.models.user import User, UserKYC, UserDevice, UserAddress
from app.models.loan import (
    LoanProduct, LoanApplication, Loan, LoanOffer,
    LoanRepayment, LoanSchedule, LoanLadder
)
from app.models.risk import (
    CreditBureauReport, FraudScore, MLScore,
    RiskTier, IncomeEstimate, FeatureSnapshot
)
from app.models.collections import (
    CollectionAction, CollectionAssignment, CollectionTier
)
from app.models.integration import (
    BankStatement, BankTransaction, PaymentTransaction,
    IntegrationLog
)

__all__ = [
    "User", "UserKYC", "UserDevice", "UserAddress",
    "LoanProduct", "LoanApplication", "Loan", "LoanOffer",
    "LoanRepayment", "LoanSchedule", "LoanLadder",
    "CreditBureauReport", "FraudScore", "MLScore",
    "RiskTier", "IncomeEstimate", "FeatureSnapshot",
    "CollectionAction", "CollectionAssignment", "CollectionTier",
    "BankStatement", "BankTransaction", "PaymentTransaction",
    "IntegrationLog",
]
