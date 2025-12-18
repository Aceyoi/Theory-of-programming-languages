# parser_flow.py
import ply.lex as lex
import ply.yacc as yacc
from flow import StartNode, EndNode, OperationNode, ConditionNode, FlowNode

# ---------- ЛЕКСЕР ----------

reserved = {
    'begin': 'BEGIN',
    'end': 'END',
    'if': 'IF',
    'then': 'THEN',
    'else': 'ELSE',
    'while': 'WHILE',
    'do': 'DO',
    'for': 'FOR',
    'to': 'TO',
    'downto': 'DOWNTO',
    'repeat': 'REPEAT',
    'until': 'UNTIL',
    'writeln': 'WRITELN',
    'write': 'WRITE',
    'readln': 'READLN',
    'read': 'READ',
    'var': 'VAR',
    'integer': 'INTEGER',
    'real': 'REAL',
    'boolean': 'BOOLEAN',
    'and': 'AND',
    'or': 'OR',
    'not': 'NOT',
    'div': 'DIV',
    'mod': 'MOD',
}

tokens = [
    'ID', 'INT', 'FLOAT',
    'PLUS', 'MINUS', 'TIMES', 'DIVIDE',
    'ASSIGN',
    'EQ', 'NE', 'LT', 'LE', 'GT', 'GE',
    'LPAREN', 'RPAREN',
    'SEMI', 'COLON', 'COMMA', 'DOT'
] + list(reserved.values())

t_PLUS   = r'\+'
t_MINUS  = r'-'
t_TIMES  = r'\*'
t_DIVIDE = r'/'
t_ASSIGN = r':='
t_EQ     = r'='
t_NE     = r'<>'
t_LE     = r'<='
t_LT     = r'<'
t_GE     = r'>='
t_GT     = r'>'
t_LPAREN = r'\('
t_RPAREN = r'\)'
t_SEMI   = r';'
t_COLON  = r':'
t_COMMA  = r','
t_DOT    = r'\.'

t_ignore = ' \t\r'


def t_FLOAT(t):
    r'\d+\.\d+'
    t.value = float(t.value)
    return t


def t_INT(t):
    r'\d+'
    t.value = int(t.value)
    return t


def t_ID(t):
    r'[A-Za-z_][A-Za-z0-9_]*'
    lower = t.value.lower()
    if lower in reserved:
        t.type = reserved[lower]
    else:
        t.value = t.value
    return t


def t_newline(t):
    r'\n+'
    t.lexer.lineno += len(t.value)


def t_comment(t):
    r'\{[^}]*\}'
    pass


def t_error(t):
    raise SyntaxError(f"Illegal character '{t.value[0]}' at line {t.lineno}")


lexer = lex.lex()

# ---------- Вспомогательная структура для списков узлов ----------

class FlowSegment:
    """
    Часть блок‑схемы: входной узел first и последний узел last.
    """
    def __init__(self, first: FlowNode, last: FlowNode):
        self.first = first
        self.last = last


# ---------- ПАРСЕР ----------

precedence = (
    ('left', 'OR'),
    ('left', 'AND'),
    ('left', 'EQ', 'NE', 'LT', 'LE', 'GT', 'GE'),
    ('left', 'PLUS', 'MINUS'),
    ('left', 'TIMES', 'DIVIDE', 'DIV', 'MOD'),
    ('right', 'NOT'),
)

def binop_to_c(op: str) -> str:
    m = {
        'and': '&&', 'or': '||', 'div': '/', 'mod': '%',
        '=': '==', '<>': '!=',
    }
    return m.get(op.lower(), op)

# expr → строка C
def make_bin_expr(a: str, op: str, b: str) -> str:
    return f"({a} {binop_to_c(op)} {b})"


# program ::= [var ..;] begin stmt_list end .
def p_program(p):
    '''program : opt_var_section BEGIN stmt_list END DOT'''
    start = StartNode()
    end = EndNode()
    seg: FlowSegment = p[3]
    start.connect(seg.first)
    seg.last.connect(end)
    p[0] = FlowSegment(start, end)


def p_opt_var_section(p):
    '''opt_var_section : VAR var_decls
                       | empty'''
    p[0] = None


def p_var_decls(p):
    '''var_decls : var_decls var_decl
                 | var_decl'''
    pass


def p_var_decl(p):
    '''var_decl : id_list COLON type_name SEMI'''
    pass


def p_type_name(p):
    '''type_name : INTEGER
                 | REAL
                 | BOOLEAN'''
    p[0] = p[1]


def p_id_list(p):
    '''id_list : ID
               | id_list COMMA ID'''
    pass


# stmt_list → FlowSegment (цепочка операций)
def p_stmt_list(p):
    '''stmt_list : stmt_list SEMI stmt
                 | stmt'''
    if len(p) == 2:
        # один stmt
        p[0] = p[1] if isinstance(p[1], FlowSegment) else FlowSegment(p[1].first, p[1].last)
    else:
        seg1: FlowSegment = p[1]
        seg2: FlowSegment = p[3]
        seg1.last.connect(seg2.first)
        p[0] = FlowSegment(seg1.first, seg2.last)


def p_stmt(p):
    '''stmt : assign_stmt
            | if_stmt
            | while_stmt
            | for_stmt
            | repeat_stmt
            | io_stmt
            | block
            | empty'''
    if p[1] is None:
        # пустой оператор: создадим пустой узел
        n = OperationNode("/* empty */")
        p[0] = FlowSegment(n, n)
    else:
        p[0] = p[1]


def p_block(p):
    '''block : BEGIN stmt_list END'''
    p[0] = p[2]


def p_assign_stmt(p):
    '''assign_stmt : ID ASSIGN expr'''
    code = f"{p[1]} = {p[3]};"
    node = OperationNode(code)
    p[0] = FlowSegment(node, node)


def p_if_stmt(p):
    '''if_stmt : IF expr THEN stmt opt_else'''
    cond_code = p[2]
    cond_node = ConditionNode(cond_code)

    then_seg: FlowSegment = p[4]
    cond_node.true_branch = then_seg.first

    if p[5] is not None:
        else_seg: FlowSegment = p[5]
        cond_node.false_branch = else_seg.first
        # объединяем хвосты then/else в один dummy
        join = OperationNode("/* join */")
        then_seg.last.connect(join)
        else_seg.last.connect(join)
        last = join
    else:
        # без else ветка False идёт сразу дальше
        join = OperationNode("/* join */")
        cond_node.false_branch = join
        then_seg.last.connect(join)
        last = join

    p[0] = FlowSegment(cond_node, last)


def p_opt_else(p):
    '''opt_else : ELSE stmt
                | empty'''
    if len(p) == 3:
        p[0] = p[2]
    else:
        p[0] = None


def p_while_stmt(p):
    '''while_stmt : WHILE expr DO stmt'''
    cond = ConditionNode(p[2])
    body_seg: FlowSegment = p[4]

    cond.true_branch = body_seg.first
    body_seg.last.connect(cond)
    # выход из цикла
    after = OperationNode("/* after while */")
    cond.false_branch = after

    p[0] = FlowSegment(cond, after)


def p_for_stmt(p):
    '''for_stmt : FOR ID ASSIGN expr TO expr DO stmt
                | FOR ID ASSIGN expr DOWNTO expr DO stmt'''
    var = p[2]
    start = p[4]
    end = p[6]
    downto = (p[5].lower() == 'downto')
    init = OperationNode(f"{var} = {start};")
    cond_code = f"{var} >= {end}" if downto else f"{var} <= {end}"
    cond = ConditionNode(cond_code)
    body_seg: FlowSegment = p[8]
    step_code = f"{var}--;" if downto else f"{var}++;"
    step = OperationNode(step_code)

    init.connect(cond)
    cond.true_branch = body_seg.first
    body_seg.last.connect(step)
    step.connect(cond)

    after = OperationNode("/* after for */")
    cond.false_branch = after

    p[0] = FlowSegment(init, after)


def p_repeat_stmt(p):
    '''repeat_stmt : REPEAT stmt_list UNTIL expr'''
    body_seg: FlowSegment = p[2]
    cond = ConditionNode(p[4])
    body_seg.last.connect(cond)
    cond.true_branch = OperationNode("/* after repeat */")
    cond.false_branch = body_seg.first
    p[0] = FlowSegment(body_seg.first, cond.true_branch)


def p_io_stmt(p):
    '''io_stmt : WRITELN LPAREN expr_list RPAREN
               | WRITE LPAREN expr_list RPAREN
               | READLN LPAREN id_expr_list RPAREN
               | READ LPAREN id_expr_list RPAREN'''
    f = p[1].lower()
    if f in ('writeln', 'write'):
        fmt = "%d " * len(p[3])
        fmt = fmt.rstrip()
        args = ", ".join(p[3])
        code = f'printf("{fmt}\\n", {args});'
        node = OperationNode(code)
    else:
        code = " ".join(f'scanf("%d", &{v});' for v in p[3])
        node = OperationNode(code)
    p[0] = FlowSegment(node, node)


def p_expr_list(p):
    '''expr_list : expr
                 | expr_list COMMA expr'''
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = p[1]
        p[0].append(p[3])


def p_id_expr_list(p):
    '''id_expr_list : ID
                    | id_expr_list COMMA ID'''
    if len(p) == 2:
        p[0] = [p[1]]
    else:
        p[0] = p[1]
        p[0].append(p[3])


# ===== выражения → просто строки C =====

def p_expr_binop(p):
    '''expr : expr PLUS expr
            | expr MINUS expr
            | expr TIMES expr
            | expr DIVIDE expr
            | expr DIV expr
            | expr MOD expr
            | expr EQ expr
            | expr NE expr
            | expr LT expr
            | expr LE expr
            | expr GT expr
            | expr GE expr
            | expr AND expr
            | expr OR expr'''
    p[0] = make_bin_expr(p[1], p[2], p[3])


def p_expr_unary(p):
    '''expr : MINUS expr %prec NOT
            | NOT expr'''
    if p[1] == '-':
        p[0] = f"(-({p[2]}))"
    else:
        p[0] = f"!({p[2]})"


def p_expr_group(p):
    '''expr : LPAREN expr RPAREN'''
    p[0] = f"({p[2]})"


def p_expr_int(p):
    '''expr : INT'''
    p[0] = str(p[1])


def p_expr_real(p):
    '''expr : FLOAT'''
    p[0] = str(p[1])


def p_expr_var(p):
    '''expr : ID'''
    p[0] = p[1]


def p_empty(p):
    'empty :'
    p[0] = None


def p_error(p):
    if p:
        raise SyntaxError(f"Syntax error at '{p.value}'")
    else:
        raise SyntaxError("Syntax error at EOF")


parser = yacc.yacc()


def parse_pascal_to_flow(source: str) -> FlowSegment:
    return parser.parse(source, lexer=lexer)
