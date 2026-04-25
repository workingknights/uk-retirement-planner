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
    age: int

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

class Goal(BaseModel):
    id: str
    name: str
    amount: float
    timing_age: int  # Primary person's age when this goal occurs
    person_id: Optional[str] = None
    override_asset_id: Optional[str] = None  # if specified, draw from this asset first

class UserProfile(BaseModel):
    id: str = "default"
    withdrawal_priority: List[AssetType] = ["cash", "premium_bonds", "general", "rsu", "isa", "pension"]
    withdrawal_strategy: WithdrawalStrategy = "sequential"
    blended_params: Optional[BlendedStrategyParams] = None
    default_inflation_rate: float = 2.5
    default_cash_growth: float = 2.0
    default_stock_growth: float = 5.0

class DeathEvent(BaseModel):
    person_id: str
    year: int  # Calendar year of death

class DivorceEvent(BaseModel):
    year: int  # Calendar year of divorce

class Scenario(BaseModel):
    id: str
    name: str
    inflation_offset: float = 0.0
    growth_offset: float = 0.0
    death_events: List[DeathEvent] = []
    divorce_events: List[DivorceEvent] = []

class Plan(BaseModel):
    id: str
    name: str
    retirement_age: int
    life_expectancy: int
    desired_annual_income: float
    people: List[Person] = []
    assets: List[Asset]
    incomes: List[IncomeSource]
    goals: List[Goal] = []
    scenarios: List[Scenario] = []

class SimulationRequest(BaseModel):
    plan: Plan
    profile: UserProfile
    scenario_id: Optional[str] = None
