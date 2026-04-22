import json
from src.engine import run_simulation
from src.models import SimulationParams
default = {"current_age":55,"retirement_age":60,"life_expectancy":95,"inflation_rate":2.5,"desired_annual_income":40000,"people":[{"id":"1","name":"Primary"}],"assets":[],"incomes":[],"life_events":[],"withdrawal_priority":["cash","general","isa","pension"],"withdrawal_strategy":"sequential","blended_params":None}
params = SimulationParams(**default)
res = run_simulation(params)
print(json.dumps(res))
