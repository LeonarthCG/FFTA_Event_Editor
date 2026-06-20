from typing import Optional

from ffta import CHARACTER_TABLE, CONTROL_CODES, LONG_CONTROL_CODES
from parse.StringParser import StringParser
from parse.StringParserVisitor import StringParserVisitor


class StringCodeVisitor(StringParserVisitor):
    errors : list[str]
    result : bool
    code : list[int]

    def visitString(self, ctx:StringParser.StringContext):
        self.errors = []
        self.result = False
        self.code = []

        for token in ctx.token():
            self.visit(token)
        self.code.append(0) # add the terminator

        self.result = len(self.errors) == 0

    def visitToken(self, ctx:StringParser.TokenContext):
        if ctx.CHAR():
            char : str = ctx.CHAR().getText()
            if char == '’':
                char = "'"
            if char in CHARACTER_TABLE:
                value : int = 0x8000 + CHARACTER_TABLE.index(char)
                self.code.extend([(value >> 8) & 0xFF, value & 0xFF])
            else:
                self.errors.append(f'At {ctx.start.line},{ctx.start.column}: Unknown character "{char}".')
        elif ctx.NL():
            self.code.extend([0x40, CONTROL_CODES['NL']])
        elif ctx.WS():
            self.code.extend([0x40, CONTROL_CODES['WS']])
        elif ctx.code():
            self.code.append(0x40)
            self.code.extend(self.visit(ctx.code()))

    def visitCode(self, ctx:StringParser.CodeContext) -> list[int]:
        result = []

        first = self.visit(ctx.arg(0))
        if first is None:
            return result
        result.append(first)

        # special case, long character codes
        if first in LONG_CONTROL_CODES:
            if len(ctx.arg()) == 2:
                second = self.visit(ctx.arg(1))
                if second is None:
                    second = 0
                result.append(second)
            else:
                self.errors.append(f'At {ctx.start.line},{ctx.start.column}: Wrong number of arguments for long control code (expected 2, got {len(ctx.arg())}).')
        # regular character codes
        else:
            if len(ctx.arg()) != 1:
                self.errors.append(f'At {ctx.start.line},{ctx.start.column}: Wrong number of arguments for control code (expected 1, got {len(ctx.arg())}).')

        # add NL if present, unless the control code is CLS
        if ctx.NL() and first != CONTROL_CODES['CLS']:
            result.append(CONTROL_CODES['NL'])

        return result

    def visitArg(self, ctx:StringParser.ArgContext) -> Optional[int]:
        value : Optional[int] = None
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
            if symbol in CONTROL_CODES.keys():
                value = CONTROL_CODES[symbol]
            else:
                self.errors.append(f'At {ctx.start.line},{ctx.start.column}: Ignored unknown control code "{symbol}".')
        return value
