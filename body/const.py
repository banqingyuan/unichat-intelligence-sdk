
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

router_prompt = """
##### Mission Purpose
{mission_purpose}

##### Known Conditions
{known_conditions}

##### Expected Output
You MUST select a function from the given functions
"""