from models import SimulationRequest, Asset, IncomeSource, Person, Plan, UserProfile, Goal, Scenario
from engine import run_simulation
from math import isclose

def test_basic_growth():
    req = SimulationRequest(
        plan=Plan(
            id="test1",
            name="Plan 1",
            retirement_age=60,
            life_expectancy=41,
            desired_annual_income=0.0,
            people=[Person(id="p1", name="P1", age=40)],
            assets=[
                Asset(id="1", name="Test ISA", type="isa", balance=100000, annual_growth_rate=5.0, annual_contribution=0)
            ],
            incomes=[],
            goals=[]
        ),
        profile=UserProfile(
            withdrawal_priority=["isa"],
            default_inflation_rate=0.0
        )
    )
    
    result = run_simulation(req)
    timeline = result["timeline"]
    
    assert len(timeline) == 2 # age 40 and age 41
    
    # Year 1 (age 40)
    year_40_balance = 100000 * 1.05
    assert isclose(timeline[0]["total_assets"], year_40_balance, rel_tol=1e-5)
    
    # Year 2 (age 41)
    year_41_balance = year_40_balance * 1.05
    assert isclose(timeline[1]["total_assets"], year_41_balance, rel_tol=1e-5)

def test_withdrawals():
    req = SimulationRequest(
        plan=Plan(
            id="test2",
            name="Plan 2",
            retirement_age=60,
            life_expectancy=61,
            desired_annual_income=20000,
            people=[Person(id="p1", name="P1", age=60)],
            assets=[
                Asset(id="1", name="Cash", type="cash", balance=50000, annual_growth_rate=0.0, annual_contribution=0)
            ],
            incomes=[]
        ),
        profile=UserProfile(
            withdrawal_priority=["cash"],
            default_inflation_rate=0.0
        )
    )
    result = run_simulation(req)
    timeline = result["timeline"]
    
    assert timeline[0]["total_income"] == 20000
    assert timeline[0]["total_assets"] == 30000
    
    assert timeline[1]["total_income"] == 20000
    assert timeline[1]["total_assets"] == 10000

def test_goals_and_deficit():
    req = SimulationRequest(
        plan=Plan(
            id="test3",
            name="Plan 3",
            retirement_age=65,
            life_expectancy=42, # test covers ages 40, 41, 42
            desired_annual_income=0,
            people=[Person(id="p1", name="P1", age=40)],
            assets=[
                Asset(id="1", name="Cash", type="cash", balance=10000, annual_growth_rate=0.0, annual_contribution=0)
            ],
            incomes=[],
            goals=[
                Goal(id="g1", name="Wedding", amount=15000, timing_age=41) # short by 5k
            ]
        ),
        profile=UserProfile(
            withdrawal_priority=["cash"],
            default_inflation_rate=0.0
        )
    )
    
    result = run_simulation(req)
    timeline = result["timeline"]
    
    # Age 40
    assert timeline[0]["total_assets"] == 10000
    assert timeline[0]["deficit"] == 0
    
    # Age 41: Goal 15k, but only 10k cash
    assert timeline[1]["total_assets"] == 0
    assert timeline[1]["total_income"] == 10000 # managed to withdraw 10k
    assert timeline[1]["deficit"] == 5000 # 15k needed - 10k withdrawn
    
def test_individual_ages_and_pensions():
    req = SimulationRequest(
        plan=Plan(
            id="test4",
            name="Plan 4",
            retirement_age=65,
            life_expectancy=65, # primary age 60 -> 65
            desired_annual_income=0,
            people=[
                Person(id="p1", name="P1", age=60),
                Person(id="p2", name="P2", age=63)
            ],
            assets=[],
            incomes=[
                # P2 gets pension at their age 64, which is year 2 (primary age 61)
                IncomeSource(id="1", name="P2 DB", type="db_pension", amount=10000, start_age=64, end_age=100, person_id="p2")
            ],
            goals=[]
        ),
        profile=UserProfile(default_inflation_rate=0.0)
    )
    
    result = run_simulation(req)
    timeline = result["timeline"]
    
    # Year 1 (primary 60, P2 63)
    assert timeline[0]["total_income"] == 0
    
    # Year 2 (primary 61, P2 64) -> pension starts!
    assert timeline[1]["total_income"] == 10000
