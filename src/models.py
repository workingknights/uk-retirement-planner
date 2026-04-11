from typing import List, Literal, Optional
import copy

AssetType = Literal["isa", "pension", "general", "cash", "property", "rsu", "premium_bonds"]
IncomeSourceType = Literal["state_pension", "db_pension", "employment", "other"]
WithdrawalStrategy = Literal["sequential", "blended"]

class Dict2Obj:
    """A lightweight Pydantic drop-in replacement for the simulation engine."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if isinstance(v, dict):
                setattr(self, k, Dict2Obj(**v))
            elif isinstance(v, list):
                setattr(self, k, [Dict2Obj(**x) if isinstance(x, dict) else x for x in v])
            else:
                setattr(self, k, v)
                
    def __getattr__(self, name):
        return None

                
    def dict(self):
        res = {}
        for k, v in self.__dict__.items():
            if isinstance(v, Dict2Obj):
                res[k] = v.dict()
            elif isinstance(v, list):
                res[k] = [x.dict() if isinstance(x, Dict2Obj) else copy.deepcopy(x) for x in v]
            else:
                res[k] = copy.deepcopy(v)
        return res

class BlendedStrategyParams(Dict2Obj): pass
class Person(Dict2Obj): pass
class AssetOwnership(Dict2Obj): pass
class LifeEvent(Dict2Obj): pass
class Asset(Dict2Obj): pass
class IncomeSource(Dict2Obj): pass
class SimulationParams(Dict2Obj): pass
