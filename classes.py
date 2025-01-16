from dataclasses import dataclass,asdict,field
from typing import List

@dataclass
class Suggestion:
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class BetterActivationTimeSuggestion(Suggestion):
    suggestion_type:str="better_activation"
    days:List[str]= field(default_factory=list) 
    new_activation_time:str=''
    monthly_saved_money:float=0.0

@dataclass
class ConflictResolutionActivationTimeSuggestion(Suggestion):
    new_activation_time:list[str]=field(default_factory=list)
    suggestion_type:str="conflict_time_change"

@dataclass
class ConflictResolutionDeactivateAutomationsSuggestion(Suggestion):
    automations_list:list[str]=field(default_factory=list)
    suggestion_type:str="conflict_deactivate_automations"
    

@dataclass
class ConflictResolutionSplitSuggestion(Suggestion):
    actions_split:list=field(default_factory=list) 
    suggestion_type:str="conflict_split_automation"