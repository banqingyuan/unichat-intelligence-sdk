
ActionAtomStatus_Waiting = 'waiting'
ActionAtomStatus_Done = 'done'

StrategyActionType_BluePrint = 'blue_print'
StrategyActionType_Action = 'action'

ActionType_Program = 'program'
ActionType_Atom = 'atom'

BPNodeType_Router = 'router'
BPNodeType_Action = 'action'

TriggerType_LUI = 'LUI_trigger'
TriggerType_Scene = 'scene_trigger'

CollectionName_LUI = 'LUI_trigger_database'

router_prompt = """
##### Mission Purpose
{mission_purpose}

##### Known Conditions
{known_conditions}

##### Expected Output
You MUST select a function from the given functions
"""

function_call_prompt = """You should choose the appropriate function call based on the contextual information provided; in principle, always use function call, and if there is no appropriate function, output "no appropriate function call".Don't make assumptions about what values to plug into functions."""