lexer grammar StringLexer;

TABS : [\t]+ -> skip ;

LBRACKET : '[' -> pushMode(CodeMode);

NL : '\r'? '\n' | '\r' ;
WS : ' ' ;
CHAR : ~'[' ;

mode CodeMode;
CODESKIP : [ \t\r\n]+ -> skip ;

RBRACKET : ']' -> popMode;
COMMA : ',' ;
SYMBOL : [A-Za-z_][A-Za-z0-9_]* ;
NUMBER : '-'? ([0-9]+ | '0x' [0-9A-Fa-f]+ | '0b' [01]+) ;
