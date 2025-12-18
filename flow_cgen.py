# flow_cgen.py
from typing import Set
from flow import StartNode, EndNode, OperationNode, ConditionNode, FlowNode


class FlowCGenerator:
    def __init__(self):
        self.lines = []
        self.indent_level = 0
        self.visited: Set[int] = set()

    def indent(self):
        return "    " * self.indent_level

    def emit(self, line: str):
        self.lines.append(self.indent() + line)

    def generate(self, start: StartNode) -> str:
        self.emit("#include <stdio.h>")
        self.emit("")
        self.emit("int main() {")
        self.indent_level += 1
        self._walk(start)
        self.emit("return 0;")
        self.indent_level -= 1
        self.emit("}")
        return "\n".join(self.lines)

    def _walk(self, node: FlowNode):
        if node.id in self.visited:
            return
        self.visited.add(node.id)

        if isinstance(node, OperationNode):
            self.emit(node.code)
            for nxt in node.next:
                self._walk(nxt)

        elif isinstance(node, ConditionNode):
            self.emit(f"if ({node.cond_code}) {{")
            self.indent_level += 1
            if node.true_branch:
                self._walk(node.true_branch)
            self.indent_level -= 1
            if node.false_branch:
                self.emit("} else {")
                self.indent_level += 1
                self._walk(node.false_branch)
                self.indent_level -= 1
            self.emit("}")
            for nxt in node.next:
                self._walk(nxt)

        else:
            for nxt in node.next:
                self._walk(nxt)
