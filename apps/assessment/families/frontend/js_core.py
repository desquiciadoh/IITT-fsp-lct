"""JavaScript language families (topic js.core).

fe.js.closure_loop.v1  var vs let in a loop that schedules callbacks (choice, redraw distractors)
fe.js.coercion.v2      value of a mixed-type expression that prints an integer (typed)
fe.js.array_chain.v1   map/filter/reduce chain on a literal array (typed)

Each program prints its answer with console.log, so tests/ml runs a sample through real Node.js
(`NODE_CHECK`, `node_answer`). In Python, generators and oracles use two separately written
models of the semantics: the generator works on drawn parameters, the oracle parses the code.
"""
from __future__ import annotations

import math
import re

from ..base import FamilyMeta
from ..builder import RedrawChoiceFamily, TypedNumberFamily

F = ("frontend",)


def node_answer(stdout: str) -> str:
    """How a program's console output maps onto the answer text (lines joined by ', ')."""
    return ", ".join(line.rstrip() for line in stdout.strip().splitlines())


# ── closures in loops ──────────────────────────────────────────────────────

class ClosureLoop(RedrawChoiceFamily):
    """b = 0.0 (junior/middle boundary): with `var` every callback sees the one function-scoped
    variable after the loop ends; `let` makes a fresh binding per iteration. Distractors are lists of
    the same length from the same loop (per-iteration, last iteration, first value, shifted by one
    step), so the loop count and the printed expression do not rule any of them out (ML-6 review)."""

    meta = FamilyMeta(id="fe.js.closure_loop.v1", version=1, specs=F, topic="js.core",
                      skills=("javascript",), format="code_output", a=1.3, b=0.0, c=0.25, time_limit_s=90)
    SEMANTIC = ('decl', 'start', 'n', 'step', 'k', 'op')
    NODE_CHECK = True

    def draw(self, rng):
        return {"decl": rng.choice(("var", "let")), "start": rng.randint(0, 99), "n": rng.randint(2, 5),
                "step": rng.randint(1, 4), "k": rng.randint(2, 500), "op": rng.choice(("*", "+")),
                "var": rng.choice(("i", "j", "n", "idx", "step", "k", "t", "pos", "counter", "val", "num", "ptr", "offset", "item")),
                "delay": rng.randint(10, 500) * 10}

    def _vals(self, p):
        return [p["start"] + p["step"] * t for t in range(p["n"])]

    def _apply(self, v, p):
        return v * p["k"] if p["op"] == "*" else v + p["k"]

    def answer(self, p):
        vals = self._vals(p)
        final = vals[-1] + p["step"]                    # the value that ends the loop
        seen = vals if p["decl"] == "let" else [final] * len(vals)
        return ", ".join(str(self._apply(v, p)) for v in seen)

    def alternatives(self, p, rng):
        vals = self._vals(p)
        final = vals[-1] + p["step"]
        n = len(vals)
        seqs = [vals,                                   # a fresh binding per iteration (let)
                [final] * n,                            # the shared variable after the loop (var)
                [vals[-1]] * n,                         # "the last iteration's value"
                vals[1:] + [final],                     # shifted by one step
                [vals[0]] * n]                          # "captured once, at the first value"
        return [", ".join(str(self._apply(v, p)) for v in x) for x in seqs]

    def render(self, p):
        v = p["var"]
        end = p["start"] + p["step"] * p["n"]
        inc = f"{v}++" if p["step"] == 1 else f"{v} += {p['step']}"
        code = (f"for ({p['decl']} {v} = {p['start']}; {v} < {end}; {inc}) {{\n"
                f"  setTimeout(() => console.log({v} {p['op']} {p['k']}), {p['delay']});\n"
                "}")
        return ("Что выведет скрипт? Значения перечислены через запятую в порядке вывода.",
                {"lang": "javascript", "text": code})

    def oracle_answer(self, inst):
        m = re.search(r"for \((var|let) (\w+) = (\d+); \w+ < (\d+); \w+(?:\+\+| \+= (\d+))\)", inst.code["text"])
        decl, _, start, end, step = m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5) or 1)
        op, k = re.search(r"console\.log\(\w+ ([*+]) (\d+)\)", inst.code["text"]).groups()
        bindings, x = [], start
        while x < end:                                   # run the loop
            bindings.append(x)
            x += step
        seen = bindings if decl == "let" else [x] * len(bindings)   # var: the shared final value
        return ", ".join(str(v * int(k) if op == "*" else v + int(k)) for v in seen)


# ── coercion ───────────────────────────────────────────────────────────────

class _Undef:
    def __repr__(self):
        return "undefined"


UNDEF = _Undef()


def _lit(src: str):
    """Generator model: a literal as a Python value (arrays as lists)."""
    if src.startswith("'"):
        return src[1:-1]
    if src in ("true", "false"):
        return src == "true"
    if src == "null":
        return None
    if src == "undefined":
        return UNDEF
    if src.startswith("["):
        return [int(src[1:-1])] if src != "[]" else []
    return int(src)


def _to_prim(v):
    return ",".join(str(x) for x in v) if isinstance(v, list) else v


def _to_num(v):
    v = _to_prim(v)
    if v is UNDEF:
        return math.nan
    if v is None:
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, str):
        return 0 if v.strip() == "" else (int(v) if re.fullmatch(r"-?\d+", v.strip()) else math.nan)
    return v


def _to_str(v):
    v = _to_prim(v)
    if v is UNDEF:
        return "undefined"
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and math.isnan(v):
        return "NaN"
    return str(v)


def _loose_eq(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return False                                     # two different objects
    if (a is None or a is UNDEF) or (b is None or b is UNDEF):
        return (a is None or a is UNDEF) and (b is None or b is UNDEF)
    if isinstance(a, list) or isinstance(b, list):
        return _loose_eq(_to_prim(a), _to_prim(b))
    if isinstance(a, bool) or isinstance(b, bool):
        return _loose_eq(_to_num(a) if isinstance(a, bool) else a, _to_num(b) if isinstance(b, bool) else b)
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    na, nb = _to_num(a), _to_num(b)
    return na == nb


def _strict_eq(a, b):
    if isinstance(a, list) or isinstance(b, list):
        return False
    if type(a) is not type(b):
        return False
    if isinstance(a, float) and math.isnan(a):
        return False
    return a == b


def js_eval(left: str, op: str, right: str) -> tuple[str, str]:
    """(typeof, printed value) of `left op right` under the generator's model."""
    a, b = _lit(left), _lit(right)
    if op == "+":
        pa, pb = _to_prim(a), _to_prim(b)
        if isinstance(pa, str) or isinstance(pb, str):
            return "string", _to_str(pa) + _to_str(pb)
        return "number", _num_str(_to_num(pa) + _to_num(pb))
    if op in ("-", "*"):
        x, y = _to_num(a), _to_num(b)
        return "number", _num_str(x - y if op == "-" else x * y)
    result = _loose_eq(a, b) if op == "==" else _strict_eq(a, b)
    return "boolean", "true" if result else "false"


def _num_str(x) -> str:
    if isinstance(x, float) and math.isnan(x):
        return "NaN"
    return str(int(x)) if float(x).is_integer() else str(x)


CHAIN_OPERANDS = (*(str(n) for n in range(0, 31)), *(f"'{n}'" for n in range(0, 31)), "true", "false", "null",
                  "[4]", "[9]", "[17]", "[]")
CHAIN_OPS = ("+", "-", "*")


def _to_literal(kind: str, value: str) -> str:
    """An intermediate primitive written back as a literal (number or quoted string)."""
    return f"'{value}'" if kind == "string" else value


def _step(left: str, op: str, right: str) -> tuple[str, str] | None:
    kind, value = js_eval(left, op, right)
    return None if value == "NaN" else (kind, value)


def chain_eval(operands: list[str], ops: list[str]) -> tuple[str, str] | None:
    """Generator model of `a op1 b op2 c` with JS precedence: * binds before + and -, which are
    left-associative. None if any step is NaN (a different lesson, excluded)."""
    a, b, c = operands
    if ops[1] == "*" and ops[0] != "*":
        inner = _step(b, "*", c)
        return inner and _step(a, ops[0], _to_literal(*inner))
    first = _step(a, ops[0], b)
    return first and _step(_to_literal(*first), ops[1], c)


class Coercion(TypedNumberFamily):
    """b = 0.5 (middle): * binds before + and -, which go left to right; + concatenates as soon as
    one side is a string (1 + 2 + '3' is '33', '1' + 2 + 3 is '123'), - and * always convert to
    numbers, arrays become strings first, null is 0 and true is 1. Only expressions whose printed
    value is a plain integer are drawn, so the answer is typed. Version 2: as a choice item with
    "number X" / "string X" options, the type word and the few distinct misreadings let an
    option-only strategy beat chance (ML-6 review)."""

    meta = FamilyMeta(id="fe.js.coercion.v2", version=2, specs=F, topic="js.core",
                      skills=("javascript",), format="code_output", a=1.2, b=0.5, c=0.0, time_limit_s=90)
    NODE_CHECK = True
    SEMANTIC = ("operands", "ops")

    def draw(self, rng):
        while True:
            operands = [rng.choice(CHAIN_OPERANDS) for _ in range(3)]
            ops = [rng.choice(CHAIN_OPS) for _ in range(2)]
            got = chain_eval(operands, ops)
            if got and re.fullmatch(r"-?(0|[1-9]\d{0,8})", got[1]):
                return {"operands": operands, "ops": ops, "var": rng.choice(("x", "r", "res", "v", "out", "val"))}

    def solve(self, p):
        return int(chain_eval(p["operands"], p["ops"])[1])

    def render(self, p):
        a, b, c = p["operands"]
        v = p["var"]
        code = f"const {v} = {a} {p['ops'][0]} {b} {p['ops'][1]} {c};\nconsole.log({v});"
        return "Что выведет код?", {"lang": "javascript", "text": code}

    def oracle_value(self, inst):
        """Precedence by reduction: fold every * first (left to right), then + and - (left to right)."""
        expr = re.search(r"= (.+);\n", inst.code["text"]).group(1)
        tokens = re.findall(r"'[^']*'|\[\d*\]|[+*-]|\w+", expr)
        for level in (("*",), ("+", "-")):
            i = 1
            while i < len(tokens):
                if tokens[i] in level:
                    kind, value = _oracle_coerce(tokens[i - 1], tokens[i], tokens[i + 1]).split(" ", 1)
                    tokens[i - 1:i + 2] = [f"'{value}'" if kind == "string" else value]
                else:
                    i += 2
        return float(tokens[0].strip(chr(39)))


def _oracle_coerce(left: str, op: str, right: str) -> str:
    """Oracle model, table-driven on literal text: ToPrimitive, ToNumber, ToString, ==, ===."""
    def prim_of(t):
        return ("string", t[1:-1])                       # [] -> "", [n] -> "n"

    def kind_of(t):
        if t.startswith("'"):
            return "string", t[1:-1]
        if t in ("true", "false"):
            return "boolean", t
        if t in ("null", "undefined"):
            return t, t
        if t.startswith("["):
            return "object", t
        return "number", t

    def as_prim(t):
        k, v = kind_of(t)
        return prim_of(t) if k == "object" else (k, v)

    def number(k, v):
        table = {"undefined": "NaN", "null": "0", "boolean": "1" if v == "true" else "0"}
        if k in table:
            return table[k]
        if k == "string":
            return "0" if v == "" else (v if re.fullmatch(r"-?\d+", v) else "NaN")
        return v

    def text(k, v):
        return v

    def arith(x, y, f):
        if "NaN" in (x, y):
            return "NaN"
        return str(f(int(x), int(y)))

    ka, va = kind_of(left)
    kb, vb = kind_of(right)
    if op == "+":
        (pa, xa), (pb, xb) = as_prim(left), as_prim(right)
        if "string" in (pa, pb):
            return f"string {text(pa, xa)}{text(pb, xb)}"
        return f"number {arith(number(pa, xa), number(pb, xb), lambda x, y: x + y)}"
    if op in ("-", "*"):
        (pa, xa), (pb, xb) = as_prim(left), as_prim(right)
        f = (lambda x, y: x - y) if op == "-" else (lambda x, y: x * y)
        return f"number {arith(number(pa, xa), number(pb, xb), f)}"
    if op == "===":
        same = ka == kb and ka != "object" and va == vb
        return f"boolean {'true' if same else 'false'}"
    # loose equality, ECMAScript 7.2.15 order
    if ka == "object" and kb == "object":
        eq = False
    elif {ka, kb} <= {"null", "undefined"}:
        eq = True
    elif "null" in (ka, kb) or "undefined" in (ka, kb):
        eq = False
    elif ka == kb:
        eq = va == vb
    else:
        (pa, xa), (pb, xb) = as_prim(left), as_prim(right)
        if pa == pb == "string":
            eq = xa == xb
        else:
            na, nb = number(pa, xa), number(pb, xb)
            eq = "NaN" not in (na, nb) and int(na) == int(nb)
    return f"boolean {'true' if eq else 'false'}"


# ── array chains ───────────────────────────────────────────────────────────

class ArrayChain(TypedNumberFamily):
    """b = -0.9 (junior): map, then filter, then reduce with an initial value; the order of the
    steps and the initial value are where answers go wrong."""

    meta = FamilyMeta(id="fe.js.array_chain.v1", version=1, specs=F, topic="js.core",
                      skills=("javascript",), format="code_output", a=1.0, b=-0.9, c=0.0, time_limit_s=90)
    SEMANTIC = ('arr', 'mul', 'add', 'mod', 'rem', 'init')
    NODE_CHECK = True

    def draw(self, rng):
        mod = rng.randint(2, 4)
        return {"arr": [rng.randint(1, 20) for _ in range(rng.randint(4, 7))], "mul": rng.randint(2, 5),
                "add": rng.randint(0, 9), "mod": mod, "rem": rng.randrange(mod), "init": rng.randint(0, 20),
                "name": rng.choice(("nums", "data", "xs", "values", "items", "list"))}

    def solve(self, p):
        mapped = [x * p["mul"] + p["add"] for x in p["arr"]]
        kept = [x for x in mapped if x % p["mod"] == p["rem"]]
        return p["init"] + sum(kept)

    def render(self, p):
        add = f" + {p['add']}" if p["add"] else ""
        code = (f"const {p['name']} = [{', '.join(str(x) for x in p['arr'])}];\n"
                f"const result = {p['name']}\n"
                f"  .map(x => x * {p['mul']}{add})\n"
                f"  .filter(x => x % {p['mod']} === {p['rem']})\n"
                f"  .reduce((sum, x) => sum + x, {p['init']});\n"
                "console.log(result);")
        return "Что выведет код?", {"lang": "javascript", "text": code}

    def oracle_value(self, inst):
        text = inst.code["text"]
        arr = [int(x) for x in re.search(r"= \[([\d, ]+)\]", text).group(1).split(",")]
        mul, add = re.search(r"\.map\(x => x \* (\d+)(?: \+ (\d+))?\)", text).groups()
        mod, rem = (int(x) for x in re.search(r"x % (\d+) === (\d+)", text).groups())
        init = int(re.search(r"sum \+ x, (\d+)\)", text).group(1))
        total = init
        for x in arr:                                    # one pass, applying each stage in turn
            y = x * int(mul) + int(add or 0)
            if y % mod == rem:
                total += y
        return float(total)


FAMILIES = [ClosureLoop(), Coercion(), ArrayChain()]
