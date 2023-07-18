from typing import List
import yaml
import os


def __extract_personal_keyword(**kwargs) -> (List[str], List[str]):
    personal_keyword = {}
    basic_info = []
    assistant_info = kwargs.get('assistant_info', {})
    if 'reflection' in assistant_info:
        for reflection_name, item in assistant_info['reflection'].items():
            personal_keyword[reflection_name] = item['description']
    if 'variable' in assistant_info:
        for variable_name, item in assistant_info['variable'].items():
            basic_info.append(variable_name)
    return personal_keyword, basic_info


os.chdir(os.path.dirname(__file__))
with open('tpl/emma.yml', 'r') as f:
    emma_config = yaml.safe_load(f)
emma_personality_dict, emma_basic_info = __extract_personal_keyword(**emma_config)

with open('tpl/npc.yml', 'r') as f:
    npc_config = yaml.safe_load(f)
npc_personality_dict, npc_basic_info = __extract_personal_keyword(**npc_config)

with open('tpl/tina.yml', 'r') as f:
    tina_config = yaml.safe_load(f)
tina_personality_dict, tina_basic_info = __extract_personal_keyword(**tina_config)
