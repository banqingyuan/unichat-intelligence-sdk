
router_prompt = """
##### Mission Purpose
{mission_purpose}

##### Known Conditions
{known_conditions}

##### Next Action Options
{next_action_options}

##### Expected Output
Please select one of the given options and surround the output with *, for example *OptionName*
Given options: {expected_output}
"""