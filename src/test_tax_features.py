from models import SimulationParams, Asset, IncomeSource, Person, AssetOwnership
from engine import run_simulation

def test_multi_owner_tax_split():
    # Setup two people
    p1 = Person(id="p1", name="Alice")
    p2 = Person(id="p2", name="Bob")
    
    # 150k GIA asset owned 50/50
    # Expected yield: 4% = 6000 total dividends -> 3000 each.
    # Each person has £500 dividend allowance.
    gia = Asset(
        id="gia", 
        name="Joint GIA", 
        type="general", 
        balance=150000, 
        annual_growth_rate=0, 
        annual_contribution=0,
        is_withdrawable=True,
        dividend_yield=4.0,
        owners=[
            AssetOwnership(person_id="p1", share=0.5),
            AssetOwnership(person_id="p2", share=0.5)
        ]
    )
    
    params = SimulationParams(
        current_age=60,
        retirement_age=60,
        life_expectancy=61,
        inflation_rate=0,
        desired_annual_income=0, # No withdrawals needed
        people=[p1, p2],
        assets=[gia],
        incomes=[],
        withdrawal_priority=["general"]
    )
    
    result = run_simulation(params)
    year0 = result["timeline"][0]
    
    alice_tax = year0["tax_breakdown"]["Alice"]
    bob_tax = year0["tax_breakdown"]["Bob"]
    
    # Alice: 3000 divs. 500 allowance. 2500 taxable at 8.75% (since no other income)
    # 2500 * 0.0875 = 218.75
    assert alice_tax["dividends"] == 3000
    assert alice_tax["dividend_tax"] == 218.75
    assert bob_tax["dividend_tax"] == 218.75

def test_pension_tax_free_ufpls():
    p1 = Person(id="p1", name="Alice")
    
    # 100k pension
    pension = Asset(
        id="pen", 
        name="Pension", 
        type="pension", 
        balance=100000, 
        annual_growth_rate=0, 
        annual_contribution=0,
        is_withdrawable=True,
        owners=[AssetOwnership(person_id="p1", share=1.0)]
    )
    
    params = SimulationParams(
        current_age=60,
        retirement_age=60,
        life_expectancy=60,
        inflation_rate=0,
        desired_annual_income=40000,
        people=[p1],
        assets=[pension],
        incomes=[],
        withdrawal_priority=["pension"]
    )
    
    result = run_simulation(params)
    year0 = result["timeline"][0]
    
    alice_tax = year0["tax_breakdown"]["Alice"]
    # 40000 withdrawal. 25% tax free = 10000. 30000 taxable.
    # Taxable income should be 30000.
    assert alice_tax["taxable_income"] == 30000
    # Income tax on 30000: (30000 - 12570) * 0.20 = 17430 * 0.20 = 3486
    assert alice_tax["income_tax"] == 3486.0

def test_pension_lifetime_limit():
    p1 = Person(id="p1", name="Alice")
    
    # Large pension withdrawal to hit lifetime limit (268,275)
    # We'll do it over two years
    pension = Asset(
        id="pen", 
        name="Big Pension", 
        type="pension", 
        balance=2000000, 
        annual_growth_rate=0, 
        annual_contribution=0,
        is_withdrawable=True,
        owners=[AssetOwnership(person_id="p1", share=1.0)]
    )
    
    params = SimulationParams(
        current_age=60,
        retirement_age=60,
        life_expectancy=61,
        inflation_rate=0,
        desired_annual_income=1200000, # Withdraw 1.2M each year
        people=[p1],
        assets=[pension],
        incomes=[],
        withdrawal_priority=["pension"]
    )
    
    result = run_simulation(params)
    year0 = result["timeline"][0]
    year1 = result["timeline"][1]
    
    # Year 0: 1.2M withdrawal. 25% = 300k. Limit = 268,275.
    # Tax free taken = 268,275. Taxable = 1,200,000 - 268,275 = 931,725.
    assert year0["tax_breakdown"]["Alice"]["taxable_income"] == 931725.0
    
    # Year 1: Limit already hit. 1.2M withdrawal. Taxable = 1.2M.
    assert year1["tax_breakdown"]["Alice"]["taxable_income"] == 800000.0 # Balance was 2M total. 2M - 1.2M = 800k left.
    # Wait, balance in year 1 is 800k.
    # Year 1 withdrawal is 800k. All taxable.
    assert year1["tax_breakdown"]["Alice"]["taxable_income"] == 800000.0
