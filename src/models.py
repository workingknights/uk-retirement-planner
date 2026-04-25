from pydantic import BaseModel
from typing import List, Literal, Optional, Dict

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
    age: int

class AssetOwnership(BaseModel):
    person_id: str
    share: float  # 0.0 to 1.0 (e.g. 0.5 for 50%)

class LifeEvent(BaseModel):
    id: str
    name: str
    age: int

class AssetAllocation(BaseModel):
    equities: float = 0.0
    bonds: float = 0.0
    cash: float = 0.0

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
    asset_allocation: AssetAllocation = AssetAllocation(equities=0.6, bonds=0.4, cash=0.0)


class IncomeSource(BaseModel):
    id: str
    name: str
    type: IncomeSourceType = "other"
    amount: float
    start_age: int
    end_age: int
    person_id: Optional[str] = None  # None = unassigned

class PlanEvent(BaseModel):
    id: str
    name: str
    amount: float
    timing_age: int  # Primary person's age when this goal occurs
    person_id: Optional[str] = None
    override_asset_id: Optional[str] = None  # if specified, draw from this asset first
    event_type: str = "custom"  # "retirement", "divorce", "downsizing", "custom"

class UserProfile(BaseModel):
    id: str = "default"
    withdrawal_priority: List[AssetType] = ["cash", "premium_bonds", "general", "rsu", "isa", "pension"]
    withdrawal_strategy: WithdrawalStrategy = "sequential"
    blended_params: Optional[BlendedStrategyParams] = None
    default_inflation_rate: float = 2.5
    default_cash_growth: float = 2.0
    default_stock_growth: float = 5.0


class Plan(BaseModel):
    id: str
    name: str
    retirement_age: int
    life_expectancy: int
    desired_annual_income: float
    people: List[Person] = []
    assets: List[Asset]
    incomes: List[IncomeSource]
    events: List[PlanEvent] = []

class MonteCarloParams(BaseModel):
    num_trials: int = 100
    expected_return_equities: float = 7.0
    std_dev_equities: float = 15.0
    expected_return_bonds: float = 3.0
    std_dev_bonds: float = 5.0
    expected_return_cash: float = 1.5
    std_dev_cash: float = 1.0
    inflation_mean: float = 2.5
    inflation_std_dev: float = 1.5

class SimulationRequest(BaseModel):
    plan: Plan
    profile: UserProfile
    run_monte_carlo: bool = False
    monte_carlo_params: Optional[MonteCarloParams] = None

