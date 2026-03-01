from pydantic import BaseModel
from typing import List, Literal, Optional

AssetType = Literal["isa", "pension", "general", "cash", "property", "rsu", "premium_bonds"]
IncomeSourceType = Literal["state_pension", "db_pension", "employment", "other"]

class Person(BaseModel):
    id: str
    name: str

class AssetOwnership(BaseModel):
    person_id: str
    share: float  # 0.0 to 1.0 (e.g. 0.5 for 50%)

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
    withdrawal_priority: List[AssetType]  # e.g., ["cash", "general", "isa", "pension"]
