from typing import List, Dict, Any, Optional
from models import SimulationParams, Asset, IncomeSource, Person

# ─────────────────────────────────────────────
# UK Tax Helpers (2024/25 tax year rates)
# ─────────────────────────────────────────────

PERSONAL_ALLOWANCE = 12_570
BASIC_RATE_LIMIT = 50_270
HIGHER_RATE_LIMIT = 125_140
PA_TAPER_THRESHOLD = 100_000
CGT_ANNUAL_EXEMPT = 3_000


def _effective_personal_allowance(gross_income: float) -> float:
    """Taper personal allowance above £100k (£1 lost per £2 earned over threshold)."""
    if gross_income > PA_TAPER_THRESHOLD:
        reduction = min(PERSONAL_ALLOWANCE, (gross_income - PA_TAPER_THRESHOLD) / 2)
        return max(0, PERSONAL_ALLOWANCE - reduction)
    return PERSONAL_ALLOWANCE


def calculate_uk_income_tax(income: float) -> float:
    """Compute UK income tax for the given gross income (2024/25 bands)."""
    if income <= 0:
        return 0.0

    # Inflate personal allowance is static (ignoring indexation for simplicity)
    pa = _effective_personal_allowance(income)
    taxable = max(0.0, income - pa)

    tax = 0.0
    # Basic rate 20%: taxable income up to (BASIC_RATE_LIMIT - pa)
    basic_band = max(0.0, BASIC_RATE_LIMIT - pa)
    basic = min(taxable, basic_band)
    tax += basic * 0.20
    remainder = taxable - basic

    # Higher rate 40%: up to HIGHER_RATE_LIMIT
    higher_band = HIGHER_RATE_LIMIT - BASIC_RATE_LIMIT
    higher = min(remainder, higher_band)
    tax += higher * 0.40
    remainder -= higher

    # Additional rate 45%
    tax += remainder * 0.45

    return round(tax, 2)


def calculate_uk_cgt(gains: float, taxable_income: float, is_property: bool = False) -> float:
    """Compute UK CGT on realised gains given the person's other taxable income (2024/25)."""
    net_gain = max(0.0, gains - CGT_ANNUAL_EXEMPT)
    if net_gain <= 0:
        return 0.0

    # How much basic-rate band remains after income has been stacked
    remaining_basic = max(0.0, BASIC_RATE_LIMIT - taxable_income)

    if is_property:
        rate_basic, rate_higher = 0.18, 0.24
    else:
        rate_basic, rate_higher = 0.10, 0.20

    in_basic = min(net_gain, remaining_basic)
    in_higher = net_gain - in_basic

    return round(in_basic * rate_basic + in_higher * rate_higher, 2)


DIVIDEND_ALLOWANCE = 500  # £500 for 2024/25


def calculate_uk_dividend_tax(dividends: float, taxable_income: float) -> float:
    """Compute UK dividend tax given dividends received and other taxable income (2024/25)."""
    net_dividends = max(0.0, dividends - DIVIDEND_ALLOWANCE)
    if net_dividends <= 0:
        return 0.0

    # Dividends sit on top of income; determine which rate band they fall into
    remaining_basic = max(0.0, BASIC_RATE_LIMIT - taxable_income)
    remaining_higher = max(0.0, HIGHER_RATE_LIMIT - max(BASIC_RATE_LIMIT, taxable_income))

    in_basic = min(net_dividends, remaining_basic)
    remainder = net_dividends - in_basic
    in_higher = min(remainder, remaining_higher)
    in_additional = max(0.0, remainder - remaining_higher)

    return round(in_basic * 0.0875 + in_higher * 0.3375 + in_additional * 0.3935, 2)


# ─────────────────────────────────────────────
# Asset tax treatment helpers
# ─────────────────────────────────────────────

def _is_tax_free_withdrawal(asset: Asset) -> bool:
    """ISA, Cash, and Premium Bond withdrawals are tax-free."""
    return asset.type in ("isa", "cash", "premium_bonds")


def _is_pension_withdrawal(asset: Asset) -> bool:
    return asset.type == "pension"


def _is_cgt_asset(asset: Asset) -> bool:
    """GIA, RSU withdrawals are subject to CGT."""
    return asset.type in ("general", "rsu")


def _is_property_cgt(asset: Asset) -> bool:
    return asset.type == "property"


# ─────────────────────────────────────────────
# Main simulation
# ─────────────────────────────────────────────

def calculate_total_balance(assets: List[Asset]) -> float:
    return sum(a.balance for a in assets)


def run_simulation(params: SimulationParams) -> Dict[str, Any]:
    current_age = params.current_age
    retirement_age = params.retirement_age
    life_expectancy = params.life_expectancy
    inflation_rate = params.inflation_rate / 100.0

    # Build lookup: person_id -> Person
    people = {p.id: p for p in params.people}

    # Track remaining tax-free pension cash per person (2024/25 lifetime limit: £268,275)
    PENSION_TAX_FREE_LIFETIME_LIMIT = 268_275.0
    person_tax_free_remaining: Dict[str, float] = {
        pid: PENSION_TAX_FREE_LIFETIME_LIMIT for pid in people
    }

    assets = [Asset(**a.model_dump()) for a in params.assets]

    yearly_data = []

    for age in range(current_age, life_expectancy + 1):

        # 1. Required (inflation-adjusted) income in retirement
        required_income = 0.0
        if age >= retirement_age:
            years_inflated = age - current_age
            required_income = params.desired_annual_income * ((1 + inflation_rate) ** years_inflated)

        # 2. Scheduled income sources
        generated_income = 0.0
        income_breakdown: Dict[str, float] = {}

        # Per-person taxable income, CGT gains, and dividend accumulators
        person_taxable_income: Dict[str, float] = {pid: 0.0 for pid in people}
        person_cgt_gains: Dict[str, float] = {pid: 0.0 for pid in people}
        person_cgt_property_gains: Dict[str, float] = {pid: 0.0 for pid in people}
        person_dividend_income: Dict[str, float] = {pid: 0.0 for pid in people}

        for inc in params.incomes:
            if inc.start_age <= age <= inc.end_age:
                years_elapsed = age - current_age
                inflated_inc = inc.amount * ((1 + inflation_rate) ** years_elapsed)
                generated_income += inflated_inc
                income_breakdown[inc.name] = inflated_inc

                # Attribute income to owning person
                if inc.person_id and inc.person_id in people:
                    person_taxable_income[inc.person_id] = (
                        person_taxable_income[inc.person_id] + inflated_inc
                    )
            else:
                income_breakdown[inc.name] = 0.0

        # 3. Apply growth and contributions to assets
        for asset in assets:
            growth = asset.balance * (asset.annual_growth_rate / 100.0)
            asset.balance += growth
            if age < retirement_age:
                asset.balance += asset.annual_contribution

        # 3b. Attribute GIA dividends (taxable each year regardless of retirement)
        for asset in assets:
            if asset.type == "general" and asset.dividend_yield:
                dividends = asset.balance * (asset.dividend_yield / 100.0)
                if not asset.owners:
                    if people:
                        pid = next(iter(people))
                        person_dividend_income[pid] = person_dividend_income[pid] + dividends
                else:
                    for ownership in asset.owners:
                        pid = ownership.person_id
                        if pid in people:
                            person_dividend_income[pid] = (
                                person_dividend_income[pid] + dividends * ownership.share
                            )

        # 4. Withdraw from assets if income shortfall
        shortfall = max(0.0, required_income - generated_income)

        if shortfall > 0:
            withdrawable_assets = [a for a in assets if a.is_withdrawable]
            priority_map = {ptype: i for i, ptype in enumerate(params.withdrawal_priority)}
            sorted_assets = sorted(withdrawable_assets, key=lambda a: priority_map.get(a.type, 999))

            remaining_shortfall = shortfall
            for asset in sorted_assets:
                if remaining_shortfall <= 0:
                    break
                if asset.balance > 0:
                    max_draw = (
                        asset.max_annual_withdrawal
                        if asset.max_annual_withdrawal is not None
                        else float("inf")
                    )
                    withdrawal = min(asset.balance, remaining_shortfall, max_draw)
                    asset.balance -= withdrawal
                    remaining_shortfall -= withdrawal
                    generated_income += withdrawal
                    income_breakdown[f"Withdrawal: {asset.name}"] = withdrawal

                    # ── Tax attribution by ownership ──
                    if not asset.owners:
                        # Unassigned – lump to first person if any exist
                        if people:
                            pid = next(iter(people))
                            _attribute_withdrawal_tax(
                                pid, withdrawal, asset,
                                person_taxable_income, person_cgt_gains, person_cgt_property_gains,
                                person_tax_free_remaining
                            )
                    else:
                        for ownership in asset.owners:
                            pid = ownership.person_id
                            if pid not in people:
                                continue
                            share_amount = withdrawal * ownership.share
                            _attribute_withdrawal_tax(
                                pid, share_amount, asset,
                                person_taxable_income, person_cgt_gains, person_cgt_property_gains,
                                person_tax_free_remaining
                            )

        # 5. Compute tax per person
        person_tax: Dict[str, Dict[str, float]] = {}
        for pid, person in people.items():
            taxable_inc = person_taxable_income[pid]
            cgt_gains = person_cgt_gains[pid]
            prop_gains = person_cgt_property_gains[pid]
            dividends = person_dividend_income[pid]

            income_tax = calculate_uk_income_tax(taxable_inc)
            cgt = calculate_uk_cgt(cgt_gains, taxable_inc, is_property=False)
            property_cgt = calculate_uk_cgt(prop_gains, taxable_inc + cgt_gains, is_property=True)
            dividend_tax = calculate_uk_dividend_tax(dividends, taxable_inc)

            person_tax[person.name] = {
                "income_tax": income_tax,
                "cgt": cgt,
                "property_cgt": property_cgt,
                "dividend_tax": dividend_tax,
                "total": round(income_tax + cgt + property_cgt + dividend_tax, 2),
                "taxable_income": round(taxable_inc, 2),
                "cgt_gains": round(cgt_gains, 2),
                "dividends": round(dividends, 2),
            }

        # 6. Record state for this year
        year_record = {
            "age": age,
            "required_income": required_income,
            "generated_income": generated_income,
            "total_assets": calculate_total_balance(assets),
            "asset_balances": {a.name: a.balance for a in assets},
            "income_breakdown": income_breakdown,
            "shortfall_remaining": max(0.0, required_income - generated_income),
            "tax_breakdown": person_tax,
        }
        yearly_data.append(year_record)

    return {
        "params": params.model_dump(),
        "timeline": yearly_data,
    }


def _attribute_withdrawal_tax(
    pid: str,
    amount: float,
    asset: Asset,
    person_taxable_income: Dict[str, float],
    person_cgt_gains: Dict[str, float],
    person_cgt_property_gains: Dict[str, float],
    person_tax_free_remaining: Dict[str, float],
) -> None:
    """Attribute withdrawal to the correct tax bucket for a person."""
    if _is_tax_free_withdrawal(asset):
        pass  # ISA, cash – no tax
    elif _is_pension_withdrawal(asset):
        # Apply 25% tax-free allowance (UFPLS) up to the £268,275 lifetime limit
        tax_free_available = person_tax_free_remaining.get(pid, 0.0)
        tax_free_portion = min(amount * 0.25, tax_free_available)
        taxable_portion = amount - tax_free_portion
        person_tax_free_remaining[pid] = tax_free_available - tax_free_portion
        person_taxable_income[pid] = person_taxable_income[pid] + taxable_portion
    elif _is_cgt_asset(asset):
        person_cgt_gains[pid] = person_cgt_gains[pid] + amount
    elif _is_property_cgt(asset):
        person_cgt_property_gains[pid] = person_cgt_property_gains[pid] + amount
