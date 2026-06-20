import sys

from antlr4 import *

from parse.ScriptCodeVisitor import ScriptCodeVisitor
from parse.ScriptLexer import ScriptLexer
from parse.ScriptParser import ScriptParser
from parse.ScriptSemanticVisitor import ScriptSemanticVisitor
from ffta import SCRIPT_INSTRUCTION_SET


def main(argv):
    print(f'Loading script "{argv[1]}".')
    input_stream = FileStream(argv[1], encoding='utf-8')
    lexer = ScriptLexer(input_stream)
    stream = CommonTokenStream(lexer)
    print()

    print('Checking for syntactic errors.')
    parser = ScriptParser(stream)
    tree = parser.script()

    if parser.getNumberOfSyntaxErrors() > 0:
        # TODO: display syntax errors
        print("Syntax errors found. Aborting.")
        return
    print('No errors were found.')
    print()

    # TODO: narrowing conversion warnings? (eg: 0xFFFF used for a 1 byte argument)
    # TODO: mismatched sign warnings? (eg: -2 used for an unsigned argument)
    print('Checking for semantic errors.')
    semantic = ScriptSemanticVisitor(SCRIPT_INSTRUCTION_SET)
    semantic.visit(tree)

    if not semantic.errors:
        print('No errors were found.')
    elif len(semantic.errors) == 1:
        print('An error was found:')
    else:
        print(f'{len(semantic.errors)} errors were found:')
    for error in semantic.errors:
        print(f'\t {error}')

    if not semantic.result:
        print('Since errors were found, the script was not compiled.')
        return
    print()

    print('Compiling script.')
    compiler = ScriptCodeVisitor(SCRIPT_INSTRUCTION_SET)
    compiler.visit(tree)

    assert compiler.result # if the semantic visitor is complete, no errors should ever occur here

    print('Writing compiled script to file "test_output.bin".')
    with open('test_output.bin', 'wb') as f:
        f.write(compiler.code)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        exit(1)
    main(sys.argv)
