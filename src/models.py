from pydantic import BaseModel
from typing import List, Literal, Optional

AssetType = Literal["isa", "pension", "general", "cash", "property", "rsu", "premium_bonds"]
IncomeSourceType = Literal["state_pension", "db_pension", "employment", "other"]
WithdrawalStrategy = Literal["sequential", "blended"]


class BlendedStrategyParams(BaseModel):
    """Parameters for the blended tax-optimised withdrawal strategy."""
    isa_drawdown_pct: float = 4.0       # % of ISA balance to draw annually
    pension_drawdown_pct: float = 5.0   # % of DC pension balance to draw annually
    isa_topup_from_pension: float = 20000  # £ to recycle from pension drawdown into ISA each year

class Person(BaseModel):
    id: str
    name: str

class AssetOwnership(BaseModel):
    person_id: str
    share: float  # 0.0 to 1.0 (e.g. 0.5 for 50%)

class LifeEvent(BaseModel):
    id: str
    name: str
    age: int

class Asset(BaseModel):
    id: str
    name: str
    type: AssetType
    balance: float
    annual_growth_rate: float
    annual_contribution: float
    is_withdrawable: bool = True
    max_annual_withdrawal: float | None = None  # Optional cap, e.g. £15,000 for RSU CGT reasons
    owners: List[AssetOwnership] = []  # empty = unassigned/whole household
    dividend_yield: float | None = None  # Annual dividend yield % (GIA only)

class IncomeSource(BaseModel):
    id: str
    name: str
    type: IncomeSourceType = "other"
    amount: float
    start_age: int
    end_age: int
    person_id: Optional[str] = None  # None = unassigned

class SimulationParams(BaseModel):
    current_age: int
    retirement_age: int
    life_expectancy: int
    inflation_rate: float
    desired_annual_income: float
    people: List[Person] = []
    assets: List[Asset]
    incomes: List[IncomeSource]
    life_events: List[LifeEvent] = []
    withdrawal_priority: List[AssetType]  # e.g., ["cash", "general", "isa", "pension"]
    withdrawal_strategy: WithdrawalStrategy = "sequential"
    blended_params: Optional[BlendedStrategyParams] = None
