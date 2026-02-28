from typing import List, Dict, Any
from models import SimulationParams, Asset, IncomeSource

def calculate_total_balance(assets: List[Asset]) -> float:
    return sum(a.balance for a in assets)

def run_simulation(params: SimulationParams) -> Dict[str, Any]:
    current_age = params.current_age
    retirement_age = params.retirement_age
    life_expectancy = params.life_expectancy
    inflation_rate = params.inflation_rate / 100.0

    assets = [Asset(**a.model_dump()) for a in params.assets]
    
    yearly_data = []

    for age in range(current_age, life_expectancy + 1):
        # 1. Apply inflation to desired income if we are in retirement
        # Assume desired income is from retirement age onwards.
        required_income = 0
        if age >= retirement_age:
            years_inflated = age - current_age
            required_income = params.desired_annual_income * ((1 + inflation_rate) ** years_inflated)

        # 2. Add incomes logic
        generated_income = 0
        income_breakdown = {}
        for inc in params.incomes:
            if inc.start_age <= age <= inc.end_age:
                # Assuming state pension and other incomes also inflate (simplified assumption)
                inflated_inc = inc.amount * ((1 + inflation_rate) ** (age - current_age))
                generated_income += inflated_inc
                income_breakdown[inc.name] = inflated_inc
            else:
                income_breakdown[inc.name] = 0

        # 3. Apply growth and contributions to assets
        for asset in assets:
            growth = asset.balance * (asset.annual_growth_rate / 100.0)
            asset.balance += growth
            if age < retirement_age:
                 asset.balance += asset.annual_contribution

        # 4. Withdraw from assets if required income > generated income
        shortfall = max(0, required_income - generated_income)
        asset_withdrawals = {a.id: 0 for a in assets}

        if shortfall > 0:
            # Order assets by user's priority (only those that are withdrawable)
            withdrawable_assets = [a for a in assets if a.is_withdrawable]
            priority_map = {ptype: i for i, ptype in enumerate(params.withdrawal_priority)}
            # Find matching assets, default to lowest priority if type isn't explicitly listed
            sorted_assets = sorted(withdrawable_assets, key=lambda a: priority_map.get(a.type, 999))

            remaining_shortfall = shortfall
            for asset in sorted_assets:
                if remaining_shortfall <= 0:
                    break
                if asset.balance > 0:
                    withdrawal = min(asset.balance, remaining_shortfall)
                    asset.balance -= withdrawal
                    asset_withdrawals[asset.id] = withdrawal
                    remaining_shortfall -= withdrawal
                    generated_income += withdrawal
                    income_breakdown[f"Withdrawal: {asset.name}"] = withdrawal

        # 5. Record state for this year
        year_record = {
            "age": age,
            "required_income": required_income,
            "generated_income": generated_income,
            "total_assets": calculate_total_balance(assets),
            "asset_balances": {a.name: a.balance for a in assets},
            "income_breakdown": income_breakdown,
            "shortfall_remaining": max(0, required_income - generated_income)
        }
        yearly_data.append(year_record)

    return {
        "params": params.model_dump(),
        "timeline": yearly_data
    }
