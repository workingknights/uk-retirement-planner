from typing import List, Dict, Any, Optional
from models import SimulationRequest, Asset, IncomeSource, Person, BlendedStrategyParams, Plan, UserProfile, Scenario

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


def run_simulation(req: SimulationRequest) -> Dict[str, Any]:
    plan = req.plan
    profile = req.profile
    scenario = None
    if req.scenario_id:
        scenario = next((s for s in plan.scenarios if s.id == req.scenario_id), None)
    
    if not plan.people:
        return {"error": "Plan must have at least one person."}
        
    primary_person = plan.people[0]
    start_age = primary_person.age
    retirement_age = plan.retirement_age
    life_expectancy = plan.life_expectancy
    
    base_inflation = profile.default_inflation_rate
    inflation_rate = (base_inflation + (scenario.inflation_offset if scenario else 0.0)) / 100.0

    people = {p.id: p for p in plan.people}
    PENSION_TAX_FREE_LIFETIME_LIMIT = 268_275.0
    person_tax_free_remaining: Dict[str, float] = {
        pid: PENSION_TAX_FREE_LIFETIME_LIMIT for pid in people
    }

    # Clone assets and apply scenario growth offsets
    assets = []
    growth_offset = scenario.growth_offset if scenario else 0.0
    for a in plan.assets:
        asset_copy = Asset(**a.model_dump())
        asset_copy.annual_growth_rate += growth_offset
        assets.append(asset_copy)

    yearly_data = []
    
    # Pre-compute death and divorce years
    deaths = {}
    divorces = set()
    if scenario:
        for d in scenario.death_events:
            deaths[d.person_id] = d.year
        for d in scenario.divorce_events:
            divorces.add(d.year)

    current_calendar_year = 2024

    for age in range(start_age, life_expectancy + 1):
        year_idx = age - start_age
        current_year = current_calendar_year + year_idx
        
        # Calculate individual ages for this year
        current_ages = {}
        for pid, p in people.items():
            current_ages[pid] = p.age + year_idx
            
        # Apply Death Events
        dead_this_year = [pid for pid, d_year in deaths.items() if d_year == current_year]
        for dead_pid in dead_this_year:
            # Transfer assets owned solely by the deceased to the primary person (or surviving spouse)
            surviving_pid = next((pid for pid in people if pid != dead_pid and deaths.get(pid, 9999) > current_year), None)
            if surviving_pid:
                for a in assets:
                    if len(a.owners) == 1 and a.owners[0].person_id == dead_pid:
                        a.owners[0].person_id = surviving_pid
                    elif len(a.owners) > 1:
                        # Find deceased's share
                        deceased_share = next((o.share for o in a.owners if o.person_id == dead_pid), 0.0)
                        a.owners = [o for o in a.owners if o.person_id != dead_pid]
                        # Give share to survivor
                        surv_owner = next((o for o in a.owners if o.person_id == surviving_pid), None)
                        if surv_owner:
                            surv_owner.share += deceased_share
                        else:
                            a.owners.append(AssetOwnership(person_id=surviving_pid, share=deceased_share))
        
        # Apply Divorce Events
        if current_year in divorces:
            # Split jointly owned assets 50/50. For simplicity, just halve the balance of joint assets.
            for a in assets:
                if len(a.owners) > 1:
                    a.balance /= 2.0
                    a.owners = [a.owners[0]]
                    a.owners[0].share = 1.0

        # 1. Required (inflation-adjusted) income & Goals
        required_income = plan.desired_annual_income * ((1 + inflation_rate) ** year_idx)
        
        goals_this_year = [g for g in plan.goals if g.timing_age == age]
        total_goals_amount = sum(g.amount * ((1 + inflation_rate) ** year_idx) for g in goals_this_year)
        
        # We need to fund required_income + total_goals_amount
        total_required_funding = required_income + total_goals_amount



        # 2. Scheduled income sources
        generated_income = 0.0
        income_breakdown: Dict[str, float] = {}

        # Per-person taxable income, CGT gains, and dividend accumulators
        person_taxable_income: Dict[str, float] = {pid: 0.0 for pid in people}
        person_cgt_gains: Dict[str, float] = {pid: 0.0 for pid in people}
        person_cgt_property_gains: Dict[str, float] = {pid: 0.0 for pid in people}
        person_dividend_income: Dict[str, float] = {pid: 0.0 for pid in people}

        # Track sources for proportional tax allocation
        person_source_taxable: Dict[str, Dict[str, float]] = {pid: {} for pid in people}
        person_source_cgt: Dict[str, Dict[str, float]] = {pid: {} for pid in people}
        person_source_property_cgt: Dict[str, Dict[str, float]] = {pid: {} for pid in people}
        person_source_dividends: Dict[str, Dict[str, float]] = {pid: {} for pid in people}

        for inc in plan.incomes:
            # Check if person is alive
            if inc.person_id and deaths.get(inc.person_id, 9999) <= current_year:
                continue
                
            inc_person_age = current_ages.get(inc.person_id, age) if inc.person_id else age
            if inc.start_age <= inc_person_age <= inc.end_age:
                years_elapsed = year_idx
                inflated_inc = inc.amount * ((1 + inflation_rate) ** years_elapsed)
                generated_income += inflated_inc
                income_breakdown[inc.name] = inflated_inc

                # Attribute income to owning person
                if inc.person_id and inc.person_id in people:
                    pid = inc.person_id
                    person_taxable_income[pid] += inflated_inc
                    person_source_taxable[pid][inc.name] = person_source_taxable[pid].get(inc.name, 0.0) + inflated_inc
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
                
                # Dividends contribute to generated income
                generated_income += dividends
                src_name = f"Dividends: {asset.name}"
                income_breakdown[src_name] = dividends

                if not asset.owners:
                    if people:
                        pid = next(iter(people))
                        person_dividend_income[pid] += dividends
                        person_source_dividends[pid][src_name] = person_source_dividends[pid].get(src_name, 0.0) + dividends
                else:
                    for ownership in asset.owners:
                        pid = ownership.person_id
                        if pid in people:
                            share_amount = dividends * ownership.share
                            person_dividend_income[pid] += share_amount
                            person_source_dividends[pid][src_name] = person_source_dividends[pid].get(src_name, 0.0) + share_amount

        # 4. Withdraw from assets to cover income shortfall + goals
        # Only enforce the target lifestyle during retirement. Before retirement, assume living within means (but goals must be funded).
        if age < retirement_age:
            shortfall = max(0.0, total_goals_amount - generated_income)
            required_income = generated_income  # Baseline to actual generated income for lifestyle
        else:
            shortfall = max(0.0, total_required_funding - generated_income)

        if shortfall > 0:
            # First, try to satisfy specific goal overrides
            for goal in goals_this_year:
                if goal.override_asset_id and shortfall > 0:
                    override_asset = next((a for a in assets if a.id == goal.override_asset_id and a.balance > 0), None)
                    if override_asset:
                        goal_inflated = goal.amount * ((1 + inflation_rate) ** year_idx)
                        withdrawal = min(override_asset.balance, goal_inflated, shortfall)
                        override_asset.balance -= withdrawal
                        shortfall -= withdrawal
                        generated_income += withdrawal
                        src_name = f"Withdrawal: {override_asset.name}"
                        income_breakdown[src_name] = income_breakdown.get(src_name, 0.0) + withdrawal
                        # (tax attribution omitted for brevity on goal overrides, assuming simple withdrawal)

            if age < retirement_age:
                # ── Pre-Retirement Strategy (Fallback if forced by future life events) ──
                # Only use cash, premium_bonds, rsu, general (no ISA or Pension)
                allowed_types = {"cash", "premium_bonds", "rsu", "general"}
                withdrawable_assets = [a for a in assets if a.is_withdrawable and a.type in allowed_types]
                priority_map = {ptype: i for i, ptype in enumerate(profile.withdrawal_priority)}
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
                        src_name = f"Withdrawal: {asset.name}"
                        income_breakdown[src_name] = income_breakdown.get(src_name, 0.0) + withdrawal
                        
                        if not asset.owners:
                            if people:
                                pid = next(iter(people))
                                _attribute_withdrawal_tax_with_sources(
                                    pid, withdrawal, asset, src_name,
                                    person_taxable_income, person_cgt_gains, person_cgt_property_gains,
                                    person_tax_free_remaining,
                                    person_source_taxable, person_source_cgt, person_source_property_cgt
                                )
                        else:
                            for ownership in asset.owners:
                                pid = ownership.person_id
                                if pid not in people:
                                    continue
                                share_amount = withdrawal * ownership.share
                                _attribute_withdrawal_tax_with_sources(
                                    pid, share_amount, asset, src_name,
                                    person_taxable_income, person_cgt_gains, person_cgt_property_gains,
                                    person_tax_free_remaining,
                                    person_source_taxable, person_source_cgt, person_source_property_cgt
                                )
            else:
                use_blended = (profile.withdrawal_strategy == "blended")
                bp = profile.blended_params or BlendedStrategyParams()

                if use_blended:
                    # ── Blended Tax-Optimised Strategy ──
                    # Step A: Draw isa_drawdown_pct% from each ISA (tax-free)
                    isa_assets = [a for a in assets if a.type == "isa" and a.is_withdrawable and a.balance > 0]
                    for asset in isa_assets:
                        if shortfall <= 0:
                            break
                        draw_target = asset.balance * (bp.isa_drawdown_pct / 100.0)
                        withdrawal = min(asset.balance, draw_target, shortfall)
                        if withdrawal > 0:
                            asset.balance -= withdrawal
                            shortfall -= withdrawal
                            generated_income += withdrawal
                            src_name = f"Withdrawal: {asset.name}"
                            income_breakdown[src_name] = income_breakdown.get(src_name, 0.0) + withdrawal
                            # ISA is tax-free — no tax attribution needed, but track ownership
                            if not asset.owners:
                                pass  # tax-free, no attribution
                            else:
                                for ownership in asset.owners:
                                    pid = ownership.person_id
                                    if pid not in people:
                                        continue
                                    # ISA withdrawals are tax-free, no _attribute call

                    # Step B: Draw pension_drawdown_pct% from each DC pension (taxable)
                    pension_assets = [a for a in assets if a.type == "pension" and a.is_withdrawable and a.balance > 0]
                    isa_topup_remaining = bp.isa_topup_from_pension  # £20k default
                    for asset in pension_assets:
                        if shortfall <= 0 and isa_topup_remaining <= 0:
                            break
                        draw_target = asset.balance * (bp.pension_drawdown_pct / 100.0)
                        # Maximum useful draw is what's needed for the shortfall PLUS what we can recycle into ISA
                        max_useful_draw = shortfall + isa_topup_remaining
                        pension_draw = min(draw_target, max_useful_draw)

                        withdrawal = min(asset.balance, pension_draw)
                        if withdrawal <= 0:
                            continue

                        # Step C: Recycle part of the pension drawdown into ISA (intra-account transfer).
                        # This is calculated FIRST so we know how much of the withdrawal is real income vs transfer.
                        topup = 0.0
                        if isa_topup_remaining > 0 and isa_assets:
                            topup = min(withdrawal, isa_topup_remaining)
                            # Distribute sequentially across ISAs, capped at £20k each (annual allowance per person)
                            topup_left = topup
                            for isa in isa_assets:
                                if topup_left <= 0:
                                    break
                                # Each ISA can absorb up to £20k per year
                                isa_capacity = 20_000.0
                                deposit = min(topup_left, isa_capacity)
                                isa.balance += deposit
                                topup_left -= deposit
                            isa_topup_remaining -= topup
                            # The ISA top-up is purely an intra-account transfer — it does NOT
                            # appear in income_breakdown or generated_income.

                        # Only the portion that actually pays for lifestyle counts as a withdrawal/income
                        covers_shortfall = withdrawal - topup
                        asset.balance -= withdrawal
                        src_name = f"Withdrawal: {asset.name}"

                        if covers_shortfall > 0:
                            generated_income += covers_shortfall
                            income_breakdown[src_name] = income_breakdown.get(src_name, 0.0) + covers_shortfall
                            shortfall -= covers_shortfall

                        # Tax attribution is on the FULL pension withdrawal (HMRC taxes the gross draw,
                        # regardless of what portion ends up in an ISA wrapper).
                        if not asset.owners:
                            if people:
                                pid = next(iter(people))
                                _attribute_withdrawal_tax_with_sources(
                                    pid, withdrawal, asset, src_name,
                                    person_taxable_income, person_cgt_gains, person_cgt_property_gains,
                                    person_tax_free_remaining,
                                    person_source_taxable, person_source_cgt, person_source_property_cgt
                                )
                        else:
                            for ownership in asset.owners:
                                pid = ownership.person_id
                                if pid not in people:
                                    continue
                                share_amount = withdrawal * ownership.share
                                _attribute_withdrawal_tax_with_sources(
                                    pid, share_amount, asset, src_name,
                                    person_taxable_income, person_cgt_gains, person_cgt_property_gains,
                                    person_tax_free_remaining,
                                    person_source_taxable, person_source_cgt, person_source_property_cgt
                                )

                    # Step D: If still shortfall, fall back to sequential priority for remaining gap
                    if shortfall > 0:
                        withdrawable_assets = [a for a in assets if a.is_withdrawable]
                        priority_map = {ptype: i for i, ptype in enumerate(profile.withdrawal_priority)}
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
                                src_name = f"Withdrawal: {asset.name}"
                                income_breakdown[src_name] = income_breakdown.get(src_name, 0.0) + withdrawal
                                if not asset.owners:
                                    if people:
                                        pid = next(iter(people))
                                        _attribute_withdrawal_tax_with_sources(
                                            pid, withdrawal, asset, src_name,
                                            person_taxable_income, person_cgt_gains, person_cgt_property_gains,
                                            person_tax_free_remaining,
                                            person_source_taxable, person_source_cgt, person_source_property_cgt
                                        )
                                else:
                                    for ownership in asset.owners:
                                        pid = ownership.person_id
                                        if pid not in people:
                                            continue
                                        share_amount = withdrawal * ownership.share
                                        _attribute_withdrawal_tax_with_sources(
                                            pid, share_amount, asset, src_name,
                                            person_taxable_income, person_cgt_gains, person_cgt_property_gains,
                                            person_tax_free_remaining,
                                            person_source_taxable, person_source_cgt, person_source_property_cgt
                                        )

                else:
                    # ── Sequential (original) Strategy ──
                    withdrawable_assets = [a for a in assets if a.is_withdrawable]
                    priority_map = {ptype: i for i, ptype in enumerate(profile.withdrawal_priority)}
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
                            src_name = f"Withdrawal: {asset.name}"
                            income_breakdown[src_name] = withdrawal

                            # ── Tax attribution by ownership ──
                            if not asset.owners:
                                if people:
                                    pid = next(iter(people))
                                    _attribute_withdrawal_tax_with_sources(
                                        pid, withdrawal, asset, src_name,
                                        person_taxable_income, person_cgt_gains, person_cgt_property_gains,
                                        person_tax_free_remaining,
                                        person_source_taxable, person_source_cgt, person_source_property_cgt
                                    )
                            else:
                                for ownership in asset.owners:
                                    pid = ownership.person_id
                                    if pid not in people:
                                        continue
                                    share_amount = withdrawal * ownership.share
                                    _attribute_withdrawal_tax_with_sources(
                                        pid, share_amount, asset, src_name,
                                        person_taxable_income, person_cgt_gains, person_cgt_property_gains,
                                        person_tax_free_remaining,
                                        person_source_taxable, person_source_cgt, person_source_property_cgt
                                    )

        # 5. Compute tax per person and proportionally attribute to sources
        person_tax: Dict[str, Dict[str, float]] = {}
        tax_by_source: Dict[str, float] = {}

        for pid, person in people.items():
            taxable_inc = person_taxable_income[pid]
            cgt_gains = person_cgt_gains[pid]
            prop_gains = person_cgt_property_gains[pid]
            dividends = person_dividend_income[pid]

            income_tax = calculate_uk_income_tax(taxable_inc)
            cgt = calculate_uk_cgt(cgt_gains, taxable_inc, is_property=False)
            property_cgt = calculate_uk_cgt(prop_gains, taxable_inc + cgt_gains, is_property=True)
            dividend_tax = calculate_uk_dividend_tax(dividends, taxable_inc)

            # Proportional allocation
            if taxable_inc > 0:
                for src_name, amount in person_source_taxable[pid].items():
                    tax_by_source[src_name] = tax_by_source.get(src_name, 0.0) + (income_tax * (amount / taxable_inc))
            
            if cgt_gains > 0:
                for src_name, amount in person_source_cgt[pid].items():
                    tax_by_source[src_name] = tax_by_source.get(src_name, 0.0) + (cgt * (amount / cgt_gains))

            if prop_gains > 0:
                for src_name, amount in person_source_property_cgt[pid].items():
                    tax_by_source[src_name] = tax_by_source.get(src_name, 0.0) + (property_cgt * (amount / prop_gains))

            if dividends > 0:
                for src_name, amount in person_source_dividends[pid].items():
                    tax_by_source[src_name] = tax_by_source.get(src_name, 0.0) + (dividend_tax * (amount / dividends))

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

        # Round the tax by source mappings
        for k in tax_by_source:
            tax_by_source[k] = round(tax_by_source[k], 2)

        # Find any life events occurring this year
        # we mapped goals to this year, let's include them in life_events list for the UI
        events_this_year = [g.name for g in plan.goals if g.timing_age == age]
        if dead_this_year:
            events_this_year.append("Death Event")
        if current_year in divorces:
            events_this_year.append("Divorce Event")

        # 6. Record state for this year
        year_record = {
            "age": age,
            "year": current_year,
            "ages": current_ages,
            "required_income": total_required_funding,
            "total_income": generated_income, # renamed properly
            "deficit": max(0.0, total_required_funding - generated_income), # shortfall that couldn't be met
            "total_assets": calculate_total_balance(assets),
            "asset_balances": {a.name: a.balance for a in assets},
            "income_breakdown": income_breakdown,
            "tax_by_source": tax_by_source,
            "shortfall_remaining": max(0.0, total_required_funding - generated_income),
            "tax_breakdown": person_tax,
            "life_events": events_this_year,
        }
        yearly_data.append(year_record)

    return {
        "params": plan.model_dump(),
        "timeline": yearly_data,
    }


def _attribute_withdrawal_tax_with_sources(
    pid: str,
    amount: float,
    asset: Asset,
    src_name: str,
    person_taxable_income: Dict[str, float],
    person_cgt_gains: Dict[str, float],
    person_cgt_property_gains: Dict[str, float],
    person_tax_free_remaining: Dict[str, float],
    person_source_taxable: Dict[str, Dict[str, float]],
    person_source_cgt: Dict[str, Dict[str, float]],
    person_source_property_cgt: Dict[str, Dict[str, float]]
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
        person_taxable_income[pid] += taxable_portion
        person_source_taxable[pid][src_name] = person_source_taxable[pid].get(src_name, 0.0) + taxable_portion
    elif _is_cgt_asset(asset):
        person_cgt_gains[pid] += amount
        person_source_cgt[pid][src_name] = person_source_cgt[pid].get(src_name, 0.0) + amount
    elif _is_property_cgt(asset):
        person_cgt_property_gains[pid] += amount
        person_source_property_cgt[pid][src_name] = person_source_property_cgt[pid].get(src_name, 0.0) + amount
