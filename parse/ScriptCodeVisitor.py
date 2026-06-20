from dataclasses import dataclass
from typing import Optional
from collections import deque

from ffta import InstructionSet
from parse.ScriptParser import ScriptParser
from parse.ScriptVisitor import ScriptVisitor


@dataclass
class IfStatemetData:
    offsets : list[int]
    current_block : int
    block_count : int


class ScriptCodeVisitor(ScriptVisitor):
    _offset : int
    symbols : dict[str, int]
    labels: dict[str, int]
    _threads_entered: int
    _current_thread : deque[int]
    _thread_start_offsets : dict[int, int]
    _thread_end_offsets : dict[int, int]
    _thread_after_offsets : dict[int, int]
    _if_data : deque[IfStatemetData]
    _current_if_data : IfStatemetData
    errors : list[str]
    result : bool
    code : list[int]
    instruction_set : InstructionSet
    _building : bool

    def __init__(self, instruction_set: InstructionSet):
        self.instruction_set = instruction_set

    def _add_instruction(self, instruction_name:str, values:Optional[list[int]]=None):
        if values is None:
            values = []
        opcode = self.instruction_set.get_opcode_by_name(instruction_name)
        if self._building:
            code = opcode.build(self._offset, values)
            self.code.extend(code)
        self._offset += opcode.get_size()

    def visitScript(self, ctx:ScriptParser.ScriptContext):
        self.symbols = {}
        self._thread_start_offsets = {}
        self._thread_end_offsets = {}
        self._thread_after_offsets = {}
        self._if_data = deque()
        self.errors = []
        self.result = False
        self.code = []

        """
        we perform two passes
        the first pass gathers symbols and calculates offsets
        the second pass generates the code
        """
        self._building = False
        for _ in range(2):
            self._offset = 0
            self._threads_entered = 0
            self._current_thread = deque()
            for statement in ctx.statement():
                self.visit(statement)
            self._add_instruction('END', [])
            self._building = True

        self.labels = {k: v for k, v in self.symbols.items() if not k.startswith('$')}
        self.result = len(self.errors) == 0

    def visitStatement(self, ctx:ScriptParser.StatementContext):
        if ctx.label():
            self.visit(ctx.label())
        elif ctx.instruction():
            self.visit(ctx.instruction())
        elif ctx.raw():
            self.visit(ctx.raw())
        elif ctx.thread():
            self.visit(ctx.thread())
        elif ctx.if_():
            self.visit(ctx.if_())

    def visitLabel(self, ctx:ScriptParser.LabelContext):
        symbol = ctx.SYMBOL().getText()
        self.symbols[symbol] = self._offset

    def visitInstruction(self, ctx:ScriptParser.InstructionContext):
        instruction_name = ctx.op().getText()
        values = [self.visit(arg) for arg in ctx.arg()] if self._building else []
        self._add_instruction(instruction_name, values)

    def visitRaw(self, ctx:ScriptParser.RawContext):
        self._offset += len(ctx.arg())

        if self._building:
            for arg in ctx.arg():
                byte = self.visit(arg) & 0xFF
                self.code.append(byte)

    def visitThread(self, ctx:ScriptParser.ThreadContext):
        self._threads_entered += 1
        current_thread = self._threads_entered
        self._current_thread.append(current_thread)

        tag = 0
        if ctx.arg():
            tag = self.visit(ctx.arg())
        start_offset = 0
        after_offset = 0
        if self._building:
            start_offset = self._thread_start_offsets[current_thread]
            after_offset = self._thread_after_offsets[current_thread]
        self._add_instruction('THREAD_WITH_TAG', [tag, start_offset])
        self._add_instruction('GO_TO', [after_offset])

        if not self._building:
            self._thread_start_offsets[current_thread] = self._offset
        self.visit(ctx.code_block())
        if not self._building:
            self._thread_end_offsets[current_thread] = self._offset
        self._add_instruction('END', [])
        if not self._building:
            self._thread_after_offsets[current_thread] = self._offset

        self._current_thread.pop()

    def visitCode_block(self, ctx:ScriptParser.Code_blockContext):
        for statement in ctx.statement():
            self.visit(statement)

    def visitIf(self, ctx:ScriptParser.IfContext):
        if self._building:
            if_data = self._if_data.popleft()
            if_data.current_block = 0
        else:
            block_count = len(ctx.if_block()) + (1 if ctx.else_block() else 0)
            if_data = IfStatemetData([], 0, block_count)
            self._if_data.append(if_data)

        for if_block in ctx.if_block():
            if not self._building:
                if_data.offsets.append(self._offset)
            self._current_if_data = if_data
            self.visit(if_block)
            if_data.current_block += 1

        if ctx.else_block():
            if not self._building:
                if_data.offsets.append(self._offset)
            self._current_if_data = if_data
            self.visit(ctx.else_block())
            if_data.current_block += 1

        if not self._building:
            if_data.offsets.append(self._offset)

    def visitIf_block(self, ctx:ScriptParser.If_blockContext):
        next_jump = self._current_if_data.current_block + 1
        next_jump_offset = 0
        final_jump_offset = 0
        if self._building:
            next_jump_offset = self._current_if_data.offsets[next_jump]
            final_jump_offset = self._current_if_data.offsets[-1]

        flag = self.visit(ctx.arg())
        if ctx.NOT():
            self._add_instruction('GO_TO_IF_FLAG', [flag, next_jump_offset])
        else:
            code_start_offset = self._offset
            code_start_offset += self.instruction_set.get_opcode_by_name('GO_TO_IF_FLAG').get_size()
            code_start_offset += self.instruction_set.get_opcode_by_name('GO_TO').get_size()
            self._add_instruction('GO_TO_IF_FLAG', [flag, code_start_offset])
            self._add_instruction('GO_TO', [next_jump_offset])

        self.visit(ctx.code_block())

        is_last_block = next_jump == self._current_if_data.block_count
        if not is_last_block:
            self._add_instruction('GO_TO', [final_jump_offset])

    def visitElse_block(self, ctx:ScriptParser.Else_blockContext):
        self.visit(ctx.code_block())

    def visitArg(self, ctx:ScriptParser.ArgContext) -> int:
        value : int
        if ctx.NUMBER():
            string = ctx.NUMBER().getText()
            if string.startswith('0x'):
                value = int(string, 16)
            elif string.startswith('0b'):
                value = int(string, 2)
            else:
                value = int(string)
        else:
            symbol = ctx.SYMBOL().getText()
            if symbol == 'BLOCK_START':
                value = self._thread_start_offsets[self._current_thread[-1]]
            elif symbol == 'BLOCK_END':
                value = self._thread_end_offsets[self._current_thread[-1]]
            else:
                value = self.symbols[symbol]
        return value
