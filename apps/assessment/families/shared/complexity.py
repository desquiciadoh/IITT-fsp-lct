"""sh.algo.complexity.v2: tight asymptotic bound (Θ) of the running time of a short Python function.

Every item shows the same six options, Θ(log n), Θ(√n), Θ(n), Θ(n log n), Θ(n²), Θ(n³)
(so c = 1/6), and the answer class is drawn uniformly before a shape of that class. A fixed
option set with a uniform answer leaves nothing to guess from the options (ML-1 review:
per-shape distractor lists let the option set reveal the answer 65 % of the time). The stem
asks for Θ, not O, so exactly one option is true.

Twelve loop shapes (linear, nested, triangular, halving, n·log n, geometric sum, square root,
sequential, cubic, constant inner loop, log of a growing bound, two-pointer) with random
names, steps and bodies. The generator takes the class from the shape table; the oracle
never looks at the shape: it instruments every loop of the rendered code, counts iterations
for n = 12, 17, 24, 34, ... (x sqrt 2) and picks the growth class with the best log-log fit.

Difficulty prior b = 0.0 (junior/middle boundary): most shapes are textbook, but the geometric
sum (Θ(n), not Θ(n log n)), the square-root bound and the two-pointer loop separate those
who count iterations from those who count nested loops. Shapes differ in difficulty, so the
family's single b is an average and a = 0.9 is set lower than for homogeneous families.

Known limits:
- Leak resistance comes from reasoning, not from the variant space: 12 shapes behind many
  cosmetic variants. A candidate who memorised the shapes can recognise them. The exposure
  monitor (ML-11) should count exposures per shape, which is the first field of the hashed
  parameters.
- The oracle counts loop iterations only: no recursion, and only `range` among builtins.
  A new shape that uses recursion or calls (sorted, `in` on a list) needs a different oracle.
"""
from __future__ import annotations

import ast
import math
import random

from ..base import FamilyMeta, Instance, fingerprint_of
from ..kit import choice_options, is_choice_correct, option_key_for_text

META = FamilyMeta(id="sh.algo.complexity.v2", version=2, specs=("backend", "frontend", "ml_data"),
                  topic="algorithms.complexity", skills=("algorithms",), format="complexity",
                  a=0.9, b=0.0, c=1 / 6, time_limit_s=90)

CLASSES = ("O(log n)", "O(√n)", "O(n)", "O(n log n)", "O(n^2)", "O(n^3)")

def theta(label: str) -> str:
    """Display form of a class: O(n^2) -> Θ(n²)."""
    return "Θ" + label[1:].replace("^2", "²").replace("^3", "³")


# shape -> (class, distractors in order of plausibility, body template); every item shows all
# six classes, the distractor lists document the typical confusion for each shape.
# Templates use {f} function, {i} {j} {k} loop variables, {acc} accumulator, {s} step, {c} constant.
SHAPES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "linear": ("O(n)", ("O(log n)", "O(n log n)", "O(n^2)"), """\
def {f}(n):
{guard}    {acc} = {init}
    for {i} in range(0, n, {s}):
        {acc} += {i} * {c} % {m}
    return {acc}"""),
    "nested": ("O(n^2)", ("O(n)", "O(n log n)", "O(n^3)"), """\
def {f}(n):
{guard}    {acc} = {init}
    for {i} in range(n):
        for {j} in range(n):
            {acc} += ({i} ^ {j}) % {m}
    return {acc}"""),
    "triangular": ("O(n^2)", ("O(n log n)", "O(n)", "O(n^3)"), """\
def {f}(n):
{guard}    {acc} = {init}
    for {i} in range(n):
        for {j} in range({i}, n):
            {acc} += ({j} - {i}) % {m}
    return {acc}"""),
    "halving": ("O(log n)", ("O(n)", "O(√n)", "O(n log n)"), """\
def {f}(n):
{guard}    {acc} = {init}
    {i} = n
    while {i} > 0:
        {acc} += {i} % {c}
        {i} //= {s2}
    return {acc}"""),
    "n_log_n": ("O(n log n)", ("O(n^2)", "O(n)", "O(log n)"), """\
def {f}(n):
{guard}    {acc} = {init}
    for {i} in range(n):
        {j} = 1
        while {j} < n:
            {acc} += ({i} + {j}) % {m}
            {j} *= {s2}
    return {acc}"""),
    "geometric": ("O(n)", ("O(n log n)", "O(log n)", "O(n^2)"), """\
def {f}(n):
{guard}    {acc} = {init}
    {i} = 1
    while {i} < n:
        for {j} in range({i}):
            {acc} += {j} % {m}
        {i} *= 2
    return {acc}"""),
    "sqrt": ("O(√n)", ("O(log n)", "O(n)", "O(n log n)"), """\
def {f}(n):
{guard}    {acc} = {init}
    {i} = 1
    while {i} * {i} <= n:
        {acc} += {i} % {m}
        {i} += 1
    return {acc}"""),
    "sequential": ("O(n)", ("O(n^2)", "O(n log n)", "O(log n)"), """\
def {f}(n):
{guard}    {acc} = {init}
    for {i} in range(n):
        {acc} += {i} % {m}
    for {j} in range(n):
        {acc} -= {j} % {c}
    return {acc}"""),
    "cubic": ("O(n^3)", ("O(n^2)", "O(n log n)", "O(n)"), """\
def {f}(n):
{guard}    {acc} = {init}
    for {i} in range(n):
        for {j} in range(n):
            for {k} in range(n):
                {acc} += {m}
    return {acc}"""),
    "const_inner": ("O(n)", ("O(n^2)", "O(n log n)", "O(log n)"), """\
def {f}(n):
{guard}    {acc} = {init}
    for {i} in range(n):
        for {j} in range({c2}):
            {acc} += {i} * {j} % {m}
    return {acc}"""),
    "log_sum": ("O(n log n)", ("O(n^2)", "O(n)", "O(log n)"), """\
def {f}(n):
{guard}    {acc} = {init}
    for {i} in range(1, n):
        {j} = {i}
        while {j} > 0:
            {acc} += {m}
            {j} //= 2
    return {acc}"""),
    "two_pointer": ("O(n)", ("O(n^2)", "O(n log n)", "O(log n)"), """\
def {f}(n):
{guard}    {acc} = {init}
    {i}, {j} = 0, n - 1
    while {i} < {j}:
        if ({i} + {j}) % {c} == 0:
            {i} += 1
        else:
            {j} -= 1
        {acc} += {m}
    return {acc}"""),
}

FUNC_NAMES = ("solve", "process", "compute", "walk", "scan", "count_pairs", "run", "aggregate",
              "score", "fold", "visit", "measure", "evaluate", "reduce_all", "tally", "sweep")
VAR_SETS = (("i", "j", "k"), ("a", "b", "c_"), ("x", "y", "z"), ("p", "q", "r"), ("row", "col", "dep"),
            ("u", "v", "w"), ("lo", "hi", "mid"), ("m1", "m2", "m3"))
ACCS = ("res", "total", "acc", "out", "s", "h", "cnt", "value")


class Complexity:
    meta = META

    def generate(self, rng: random.Random) -> Instance:
        label = CLASSES[rng.randrange(len(CLASSES))]
        of_class = sorted(name for name, spec in SHAPES.items() if spec[0] == label)
        shape = of_class[rng.randrange(len(of_class))]
        _, _, tmpl = SHAPES[shape]
        i, j, k = VAR_SETS[rng.randrange(len(VAR_SETS))]
        params = {"shape": shape, "f": rng.choice(FUNC_NAMES), "vars": [i, j, k],
                  "acc": rng.choice(ACCS), "s": rng.randint(1, 3), "s2": rng.randint(2, 4),
                  "c": rng.randint(3, 9), "c2": rng.randint(3, 12), "m": rng.randint(2, 97),
                  "init": rng.randint(0, 9), "guard": rng.randint(0, 9)}
        # An O(1) early exit for tiny inputs on about half the items; it never changes the class.
        g = params["guard"]
        guard = f"    if n < {g}:\n        return {g}\n" if g > 4 else ""
        code = tmpl.format(f=params["f"], i=i, j=j, k=k, acc=params["acc"], s=params["s"],
                           s2=params["s2"], c=params["c"], c2=params["c2"], m=params["m"],
                           init=params["init"], guard=guard)
        options, key = choice_options(rng, theta(label), [theta(x) for x in CLASSES if x != label],
                                      k=len(CLASSES))
        # Draws a template doesn't use are not parameters of the item: hash what renders.
        params = {"shape": shape, "code": code}
        return Instance(stem_md="Какова точная асимптотическая оценка (Θ) времени работы функции "
                                "в худшем случае как функции от `n`?",
                        input="choice", key=key, fingerprint=fingerprint_of(params),
                        code={"lang": "python", "text": code}, options=options)

    def is_correct(self, key, answer: dict) -> bool:
        return is_choice_correct(key, answer)

    def oracle(self, inst: Instance):
        return option_key_for_text(inst.options, theta(measure_class(inst.code["text"])))


# ── empirical oracle ───────────────────────────────────────────────────────

BUDGET = 150_000
N_START = 12           # above every guard (n < 10), so early exits never distort the counts
MIN_POINTS = 5         # cubic code gets exactly 5 points (n <= 48) under the budget
MAX_RMS = 0.35         # the winning model must fit the log counts within ~x1.4 (RMS) ...
MIN_SSE_RATIO = 3.0    # ... and clearly better than the runner-up
_MODELS = {
    "O(1)": lambda n: 1.0,          # never an option; it exists so constant work isn't misread
    "O(log n)": math.log2,
    "O(√n)": math.sqrt,
    "O(n)": lambda n: n,
    "O(n log n)": lambda n: n * math.log2(n),
    "O(n^2)": lambda n: n ** 2,
    "O(n^3)": lambda n: n ** 3,
}

# Constructs whose cost is the number of loop iterations. Anything else (comprehensions,
# `in`, slicing, calls other than range, recursion, try/except) does uncounted work, so the
# oracle refuses it instead of mis-measuring it.
_ALLOWED = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign,
            ast.AugAssign, ast.For, ast.While, ast.If, ast.Expr, ast.Name, ast.Load, ast.Store,
            ast.Constant, ast.Tuple, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.Call,
            ast.operator, ast.unaryop, ast.boolop, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq,
            ast.NotEq)


class _OverBudget(BaseException):
    """BaseException, so an `except Exception` in measured code can't swallow it."""


class _Counter(ast.NodeTransformer):
    """Prepend `__tick()` to the body of every loop."""

    def _visit_loop(self, node):
        self.generic_visit(node)
        tick = ast.Expr(ast.Call(func=ast.Name("__tick", ast.Load()), args=[], keywords=[]))
        node.body.insert(0, tick)
        return node

    visit_For = _visit_loop
    visit_While = _visit_loop


def _check_supported(tree: ast.Module, fname: str) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ValueError(f"unsupported construct for the iteration oracle: {type(node).__name__}")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id == "range"):
            raise ValueError("only range() calls are supported by the iteration oracle")
        if isinstance(node, ast.Name) and node.id == fname and isinstance(node.ctx, ast.Load):
            raise ValueError("recursion is not supported by the iteration oracle")


def _instrumented(code: str):
    tree = ast.parse(code)
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(tree.body) != 1 or len(funcs) != 1 or [a.arg for a in funcs[0].args.args] != ["n"]:
        raise ValueError("expected exactly one function of n")
    _check_supported(tree, funcs[0].name)
    tree = ast.fix_missing_locations(_Counter().visit(tree))
    state = {"count": 0}

    def tick():
        state["count"] += 1
        if state["count"] > BUDGET:
            raise _OverBudget

    ns = {"__tick": tick, "__builtins__": {"range": range}}
    exec(compile(tree, "<item>", "exec"), ns)  # harness only: runs the family's own generated code
    return ns[funcs[0].name], state


def iteration_counts(code: str) -> list[tuple[int, int]]:
    fn, state = _instrumented(code)
    points = []
    step = 0
    while (n := round(N_START * 2 ** (step / 2))) <= 1 << 20:     # n = 12, 17, 24, 34, 48, ...
        state["count"] = 0
        try:
            fn(n)
        except _OverBudget:
            break
        if state["count"] == 0:
            raise ValueError(f"no loop iterations at n = {n}: an early exit hides the growth")
        points.append((n, state["count"]))
        step += 1
    return points


def model_fits(points: list[tuple[int, int]]) -> dict[str, float]:
    """SSE of log(count) − log(f(n)) around its mean, per growth model."""
    fits = {}
    for label, f in _MODELS.items():
        resid = [math.log(c) - math.log(f(n)) for n, c in points]
        mean = sum(resid) / len(resid)
        fits[label] = sum((r - mean) ** 2 for r in resid)
    return fits


def measure_class(code: str) -> str:
    """The growth class whose log-log fit to the measured iteration counts is clearly best."""
    points = iteration_counts(code)
    if len(points) < MIN_POINTS:
        raise ValueError(f"too few measurable points: {points}")
    ranked = sorted(model_fits(points).items(), key=lambda kv: (kv[1], kv[0]))
    (best, best_sse), (_, second_sse) = ranked[0], ranked[1]
    rms = math.sqrt(best_sse / len(points))
    if rms > MAX_RMS or second_sse < MIN_SSE_RATIO * max(best_sse, 1e-9):
        raise ValueError(f"ambiguous growth: {best} rms={rms:.3f} sse={best_sse:.3f}, "
                         f"runner-up sse={second_sse:.3f}")
    if best not in CLASSES:
        raise ValueError(f"measured {best}, which is not an answer class")
    return best


FAMILY = Complexity()
