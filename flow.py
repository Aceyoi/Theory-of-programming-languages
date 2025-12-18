# flow.py
from typing import List, Optional


class FlowNode:
    _counter = 0
    def __init__(self, label: str = ""):
        self.id = FlowNode._counter
        FlowNode._counter += 1
        self.label = label
        self.next: List['FlowNode'] = []  # линейные переходы

    def connect(self, other: 'FlowNode'):
        self.next.append(other)


class StartNode(FlowNode):
    def __init__(self):
        super().__init__("START")


class EndNode(FlowNode):
    def __init__(self):
        super().__init__("END")


class OperationNode(FlowNode):
    def __init__(self, code: str):
        super().__init__("OP")
        self.code = code  # строка псевдо‑C


class ConditionNode(FlowNode):
    def __init__(self, cond_code: str):
        super().__init__("COND")
        self.cond_code = cond_code
        self.true_branch: Optional[FlowNode] = None
        self.false_branch: Optional[FlowNode] = None
