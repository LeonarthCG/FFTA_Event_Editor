grammar Script;

script : statement* ;

eol: LINE_COMMENT | NL ;
statement : label | instruction | raw | thread | if | eol;

label : SYMBOL ':' ;

instruction : op arg* eol ;
op : SYMBOL ;
arg : NUMBER | SYMBOL ;

raw : BYTE arg+ eol ;

thread : RUN (arg)? code_block ;
code_block : eol? '{' statement* '}' eol? ;

if : if_block (ELSE if_block)? else_block? ;
if_block : IF NOT? FLAG arg code_block;
else_block : ELSE code_block;

BLOCK_COMMENT : '/*' .*? '*/' NL? -> skip;
LINE_COMMENT : '//' ~[\r\n]* NL ;

RUN: 'run thread' ;
IF: 'if' ;
NOT: 'not' ;
FLAG: 'flag' ;
ELSE: 'else' ;
BYTE : 'BYTE' ;
NUMBER : '-'? ([0-9]+ | '0x' [0-9A-Fa-f]+ | '0b' [01]+) ;
SYMBOL : [A-Za-z_$][A-Za-z0-9_]* ;

WS : [ \t]+ -> skip ;
NL : EOF | ('\r'? '\n' | '\r' | ';')+ ;
