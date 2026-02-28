from models import SimulationParams, Asset, IncomeSource
from engine import run_simulation
from math import isclose

def test_basic_growth():
    params = SimulationParams(
        current_age=40,
        retirement_age=60,
        life_expectancy=41,
        inflation_rate=0.0,
        desired_annual_income=0.0,
        assets=[
            Asset(id="1", name="Test ISA", type="isa", balance=100000, annual_growth_rate=5.0, annual_contribution=0)
        ],
        incomes=[],
        withdrawal_priority=["isa"]
    )
    
    result = run_simulation(params)
    timeline = result["timeline"]
    
    assert len(timeline) == 2 # age 40 and age 41
    
    # Year 1 (age 40)
    year_40_balance = 100000 * 1.05
    assert isclose(timeline[0]["total_assets"], year_40_balance, rel_tol=1e-5)
    
    # Year 2 (age 41)
    year_41_balance = year_40_balance * 1.05
    assert isclose(timeline[1]["total_assets"], year_41_balance, rel_tol=1e-5)

def test_withdrawals():
    params = SimulationParams(
        current_age=60,
        retirement_age=60,
        life_expectancy=61,
        inflation_rate=0.0,
        desired_annual_income=20000,
        assets=[
            Asset(id="1", name="Cash", type="cash", balance=50000, annual_growth_rate=0.0, annual_contribution=0)
        ],
        incomes=[],
        withdrawal_priority=["cash"]
    )
    result = run_simulation(params)
    timeline = result["timeline"]
    
    # Year 1 (age 60): 50k balance -> required 20k -> withdrawal 20k -> remaining 30k
    assert timeline[0]["generated_income"] == 20000
    assert timeline[0]["total_assets"] == 30000
    
    # Year 1 (age 60): 30k balance -> required 20k -> withdrawal 20k -> remaining 10k
    assert timeline[1]["generated_income"] == 20000
    assert timeline[1]["total_assets"] == 10000

def test_property_and_db_pension():
    params = SimulationParams(
        current_age=60,
        retirement_age=60,
        life_expectancy=61,
        inflation_rate=0.0,
        desired_annual_income=25000,
        assets=[
            Asset(id="1", name="Cash", type="cash", balance=50000, annual_growth_rate=0.0, annual_contribution=0, is_withdrawable=True),
            Asset(id="2", name="House", type="property", balance=300000, annual_growth_rate=2.0, annual_contribution=0, is_withdrawable=False)
        ],
        incomes=[
            IncomeSource(id="1", name="DB Pension", type="db_pension", amount=15000, start_age=60, end_age=100)
        ],
        withdrawal_priority=["cash"]
    )
    result = run_simulation(params)
    timeline = result["timeline"]
    
    # Year 1 (age 60): Required 25k. Generated 15k from DB Pension. Shortfall 10k. 
    # Withdrawn from cash: 10k. Cash remaining: 40k. House remaining: 300k * 1.02 = 306k.
    # Total Assets = 346k
    assert timeline[0]["generated_income"] == 25000 # 15k + 10k
    assert timeline[0]["asset_balances"]["Cash"] == 40000
    assert timeline[0]["asset_balances"]["House"] == 306000
    assert timeline[0]["total_assets"] == 346000

    # Year 2 (age 61): Required 25k. Generated 15k from DB. Shortfall 10k.
    # Withdrawn from cash: 10k. Cash remaining: 30k. House remaining: 306k * 1.02 = 312120.
    # Total Assets = 342120
    assert timeline[1]["generated_income"] == 25000
    assert timeline[1]["asset_balances"]["Cash"] == 30000
    assert timeline[1]["asset_balances"]["House"] == 312120
    assert timeline[1]["total_assets"] == 342120
