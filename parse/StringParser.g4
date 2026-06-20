parser grammar StringParser;

options { tokenVocab=StringLexer; }

string : token* ;

token : NL | WS | CHAR | code ;

code : LBRACKET arg (COMMA arg)? RBRACKET NL? ;
arg : NUMBER | SYMBOL ;
