from pydantic import BaseModel
from typing import List, Literal

AssetType = Literal["isa", "pension", "general", "cash", "property", "rsu"]
IncomeSourceType = Literal["state_pension", "db_pension", "employment", "other"]

class Asset(BaseModel):
    id: str
    name: str
    type: AssetType
    balance: float
    annual_growth_rate: float
    annual_contribution: float
    is_withdrawable: bool = True
    max_annual_withdrawal: float | None = None  # Optional cap, e.g. £15,000 for RSU CGT reasons

class IncomeSource(BaseModel):
    id: str
    name: str
    type: IncomeSourceType = "other"
    amount: float
    start_age: int
    end_age: int

class SimulationParams(BaseModel):
    current_age: int
    retirement_age: int
    life_expectancy: int
    inflation_rate: float
    desired_annual_income: float
    assets: List[Asset]
    incomes: List[IncomeSource]
    withdrawal_priority: List[AssetType]  # e.g., ["cash", "general", "isa", "pension"]
