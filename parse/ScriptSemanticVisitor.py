from dataclasses import dataclass

from ffta import InstructionSet, SCRIPT_INSTRUCTION_SET, CONDITIONALS_INSTRUCTION_SET
from parse.ScriptParser import ScriptParser
from parse.ScriptVisitor import ScriptVisitor


@dataclass
class SymbolReference:
    symbol: str
    line: int
    column: int


class ScriptSemanticVisitor(ScriptVisitor):
    symbols : set[str]
    references: list[SymbolReference]
    errors : list[str]
    result : bool
    instruction_set : InstructionSet

    def __init__(self, instruction_set: InstructionSet):
        self.instruction_set = instruction_set

    def visitScript(self, ctx:ScriptParser.ScriptContext):
        self.symbols = set()
        self.references = []
        self.errors = []
        self.result = False

        for statement in ctx.statement():
            self.visit(statement)

        # check that all referenced symbols were eventually defined
        for reference in self.references:
            if reference.symbol == 'BLOCK_START' or reference.symbol == 'BLOCK_END':
                continue
            if reference.symbol not in self.symbols:
                self.errors.append(f'At {reference.line},{reference.column}: Referenced non-existing label "{reference.symbol}".')

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
        if symbol in self.symbols:
            self.errors.append(f'At {ctx.start.line},{ctx.start.column}: Redefined label "{symbol}".')
        elif symbol == 'BLOCK_START' or symbol == 'BLOCK_END':
            self.errors.append(f'At {ctx.start.line},{ctx.start.column}: Redefined reserved label "{symbol}".')
        else:
            self.symbols.add(symbol)

    def visitInstruction(self, ctx:ScriptParser.InstructionContext):
        instruction_name = ctx.op().getText()
        opcode = self.instruction_set.get_opcode_by_name(instruction_name)
        if opcode is None:
            self.errors.append(f'At {ctx.start.line},{ctx.start.column}: Invoked non-existing opcode "{instruction_name}".')
        else:
            arg_count = opcode.get_arg_count()
            if opcode.get_arg_count() != len(ctx.arg()):
                self.errors.append(f'At {ctx.start.line},{ctx.start.column}: Wrong number of arguments for "{instruction_name}" (expected {arg_count}, got {len(ctx.arg())}).')

        for arg in ctx.arg():
            self.visit(arg)

    def visitRaw(self, ctx:ScriptParser.RawContext):
        for arg in ctx.arg():
            self.visit(arg)

    def visitThread(self, ctx:ScriptParser.ThreadContext):
        if self.instruction_set == CONDITIONALS_INSTRUCTION_SET:
            self.errors.append(f'At {ctx.start.line},{ctx.start.column}: Thread blocks are unavailable for conditionals.')

        if ctx.arg():
            self.visit(ctx.arg())
        self.visit(ctx.code_block())

    def visitCode_block(self, ctx:ScriptParser.Code_blockContext):
        for statement in ctx.statement():
            self.visit(statement)

    def visitIf(self, ctx:ScriptParser.IfContext):
        for if_block in ctx.if_block():
            self.visit(if_block)
        if ctx.else_block():
            self.visit(ctx.else_block())

    def visitIf_block(self, ctx:ScriptParser.If_blockContext):
        self.visit(ctx.arg())
        self.visit(ctx.code_block())

    def visitElse_block(self, ctx:ScriptParser.Else_blockContext):
        self.visit(ctx.code_block())

    def visitArg(self, ctx:ScriptParser.ArgContext):
        if ctx.SYMBOL():
            symbol = ctx.SYMBOL().getText()
            self.references.append(SymbolReference(symbol, ctx.start.line, ctx.start.column))
