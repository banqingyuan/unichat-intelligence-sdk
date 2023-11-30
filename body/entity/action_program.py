import logging
import threading
from typing import Dict, List, Optional
from common_py.utils.logger import wrapper_azure_log_handler, wrapper_std_output
from pydantic import BaseModel

from body.const import ActionAtomStatus_Waiting, ActionAtomStatus_Done
from body.entity.base_action import BaseAction, BaseActionMgr
from body.entity.function_call import FunctionDescribe, combine_parameters
from body.presist_object.action_atom_po import load_all_action_atom_po, ActionAtomPo
from body.presist_object.action_program_po import load_all_action_program_po, ActionProgramPo

logger = wrapper_azure_log_handler(
    wrapper_std_output(
        logging.getLogger(__name__)
    )
)


class ActionAtom(FunctionDescribe):
    """
    原子动作，由此构成一个自然连贯的动作组合
    ActionAtom中使用的 FunctionDescribe中的入参需求可以继承action_engine
    """
    # 同一种动作，在不同的编排中的id都是不同的，但只需保证全剧本中唯一即可。
    atom_id: str

    # required in FunctionDescribe
    # name: str 需要在动作编排中唯一或在全蓝图中唯一
    # description: str
    # parameters: Parameter

    action_engine: BaseAction

    # 不需要了，初始化时直接preset到parameter中
    # preset_value: Dict[str, str] = None

    # output_args: Optional[Dict[str, str]] = None

    # waiting, done
    execute_status: str = ActionAtomStatus_Waiting

    def set_output_args(self, **output_args):
        logger.info(f"set output args for {self.atom_id}: {output_args}")
        self.set_output_params(**output_args)

    def gen_function_call_describe(self):
        return self.action_engine.gen_function_call_describe()


class ActionProgram(FunctionDescribe):
    """
    原子动作的组合编排，由此构成一个自然连贯的动作组合
    可以被蓝图动作引用，也可以由LUI或触发器直接引用。
    program 使用的 FunctionDescribe中的入参需求需要自己编辑
    """
    action_program_id: str

    # required
    # name: str
    # description: str
    # parameters: Parameter

    # 所有存放的节点
    action_nodes: Dict[str, ActionAtom]

    portal_nodes: List[str] = []

    # 通过id索引的，上一个动作的id 通过索引构成的有向无环图
    # from one atom to another atom, with output_args to input_args
    action_graph: Dict[str, Dict[str, Dict[str, str]]]

    # 待运行节点依赖满足检查 key: 子节点 value: 父节点
    action_stash: Dict[str, List[str]] = {}
    # program_status: str = 'waiting'

    def __init__(self, **data):
        super().__init__(**data)
        self._analyse_action_dependency()
        self.portal_nodes = self._portal_actions()
        if len(self.portal_nodes) == 0:
            logger.error(f"action program {self.action_program_id} has no portal node")
            raise Exception(f"action program {self.action_program_id} has no portal node")
        self.parameters = combine_parameters([self.action_nodes[portal_node].parameters for portal_node in self.portal_nodes])

    def _analyse_action_dependency(self):
        for parent_action, child_actions in self.action_graph.items():
            for child_action in child_actions.keys():
                if child_action not in self.action_stash:
                    self.action_stash[child_action] = []
                self.action_stash[child_action].append(parent_action)
            if parent_action not in self.action_stash:
                self.action_stash[parent_action] = []

    def _portal_actions(self) -> List[str]:
        return [action_id for action_id, dependencies in self.action_stash.items() if len(dependencies) == 0]

    def ready_to_execute(self) -> List[str]:
        ready_actions = []
        for action_id, dependencies in self.action_stash.items():
            if len(dependencies) == 0 or all([self.action_nodes[dependency].execute_status == ActionAtomStatus_Done for dependency in dependencies]):
                for parent_id in dependencies:
                    self._args_preset(parent_id, action_id)
                ready_actions.append(action_id)
                del self.action_stash[action_id]
        return ready_actions

    def _args_preset(self, parent_id: str, child_id: str):
        parent_atom = self.action_nodes[parent_id]
        args = parent_atom.output_params
        mapped_args = self.action_graph[parent_id][child_id]

        args_to_fill = {}
        for source_args_name, target_args_name in mapped_args.items():
            if args.get_prop_value(source_args_name) is not None:
                args_to_fill[target_args_name] = args.get_prop_value(source_args_name)
        self.action_nodes[child_id].set_params(**args_to_fill)
        logger.info(f"preset args for {child_id} from {parent_id}: {args_to_fill}")

    def execute(self):
        ready_actions = self.ready_to_execute()
        for action_id in ready_actions:
            action_atom = self.action_nodes[action_id]
            yield action_atom


class ActionProgramMgr:
    _instance_lock = threading.Lock()

    def __init__(self):
        if not hasattr(self, "_ready"):
            ActionProgramMgr._ready = True

            self.action_atoms: Dict[str, ActionAtomPo] = {}
            self.action_programs: Dict[str, ActionProgramPo] = {}
            self.refresh()

    def _refresh_action_atoms(self):
        self.action_atoms = load_all_action_atom_po()

    def _refresh_action_programs(self):
        self.action_programs = load_all_action_program_po()

    def get_action_atom(self, atom_id: str) -> Optional[ActionAtom]:
        try:
            po = self.action_atoms.get(atom_id, None)
            if not po:
                logger.error(f"action atom {atom_id} not found")
                return None
            action_instance = BaseActionMgr().action_factory(po.action_type)

            action_atom = ActionAtom(
                atom_id=po.atom_id,
                name=po.atom_name,
                action_engine=action_instance,
                description=po.atom_description
            )
            if po.action_preset_args:
                action_atom.set_params(**po.action_preset_args)
            return action_atom
        except Exception as e:
            logger.exception(e)
            return None

    def get_action_program(self, program_id: str) -> Optional[ActionProgram]:
        try:
            program = self.action_programs.get(program_id, None)
            if not program:
                logger.error(f"action program {program_id} not found")
                return None
            action_nodes = {}
            for node in program.action_nodes:
                action_nodes[node] = self.get_action_atom(node)
            action_program = ActionProgram(
                action_program_id=program.program_id,
                name=program.program_name,
                action_nodes=action_nodes,
                action_graph=program.action_graph,
                description=program.description
            )
            return action_program
        except Exception as e:
            logger.exception(e)
            return None

    # refresh every 2 minutes
    def refresh(self):
        try:
            self._refresh_action_atoms()
            self._refresh_action_programs()
        except Exception as e:
            logger.exception(e)
        threading.Timer(120, self.refresh).start()

    def __new__(cls, *args, **kwargs):
        if not hasattr(ActionProgramMgr, "_instance"):
            with ActionProgramMgr._instance_lock:
                if not hasattr(ActionProgramMgr, "_instance"):
                    ActionProgramMgr._instance = object.__new__(cls)
        return ActionProgramMgr._instance