"""Python language families for backend and ML & Data (topic python.core).

bm.py.mutable_default.v2  a default list argument shared between calls (typed: sum of one result)
bm.py.slicing.v1          sum of a slice with negative indices and steps (typed)
bm.py.floor_mod.v1        // and % with negative operands (typed)
bm.py.late_binding.v2     closures created in a loop, with and without default-argument capture (typed)

Generators evaluate the semantics by hand-written rules; oracles execute the code the candidate
sees (builder.run_python).
"""
from __future__ import annotations

from ..base import FamilyMeta
from ..builder import TypedNumberFamily, run_python

BM = ("backend", "ml_data")
FN = ("add", "push", "collect", "remember", "track", "log_item", "keep", "store")


class MutableDefault(TypedNumberFamily):
    """b = 0.4 (middle): the default list is created once, at def time, so calls that rely on it
    share one list (and every name bound to it shows its final state), while a call that passes
    its own list does not touch the shared one. The program prints the sum of one result, which
    says exactly which values that list holds. Version 2 is typed: as a choice item, every set of
    distractors built from the same calls left an option-only strategy above chance (shortest
    option, value seen before; ML-6 review)."""

    meta = FamilyMeta(id="bm.py.mutable_default.v2", version=2, specs=BM, topic="python.core",
                      skills=("python",), format="code_output", a=1.3, b=0.4, c=0.0, time_limit_s=90)
    SEMANTIC = ("calls", "show")

    def draw(self, rng):
        """The shown result is always one that relies on the default list, and at least two calls
        share it, so "a new list every call" gives a different answer (ML-6 re-review: on a third
        of the first v2 items the answer was the shown call's own value)."""
        fn, arg = rng.choice(FN), rng.choice(("items", "acc", "bucket", "seen"))
        while True:
            calls = [[rng.randint(1, 99), rng.random() < 0.3] for _ in range(rng.randint(3, 5))]
            shared = [i for i, c in enumerate(calls) if not c[1]]
            if len(shared) >= 2:
                return {"calls": calls, "fn": fn, "arg": arg, "show": rng.choice(shared)}

    def solve(self, p):
        v, explicit = p["calls"][p["show"]]
        if explicit:
            return v
        return sum(c[0] for c in p["calls"] if not c[1])    # the shared list, as it is at the end

    def render(self, p):
        fn, arg = p["fn"], p["arg"]
        lines = [f"def {fn}(x, {arg}=[]):", f"    {arg}.append(x)", f"    return {arg}", ""]
        for i, (v, explicit) in enumerate(p["calls"]):
            lines.append(f"r{i} = {fn}({v}, [])" if explicit else f"r{i} = {fn}({v})")
        lines.append(f"print(sum(r{p['show']}))")
        return "Что напечатает программа?", {"lang": "python", "text": "\n".join(lines)}

    def oracle_value(self, inst):
        return float(run_python(inst.code["text"]))


class Slicing(TypedNumberFamily):
    """b = -0.6 (junior): start is inclusive, stop exclusive, negative indices count from the end,
    a negative step walks backwards; summing the slice checks all of it at once. Empty slices are
    redrawn: "0" was right on 16 % of items, which a guesser could exploit (ML-6 review)."""

    meta = FamilyMeta(id="bm.py.slicing.v1", version=1, specs=BM, topic="python.core",
                      skills=("python",), format="code_output", a=1.1, b=-0.6, c=0.0, time_limit_s=90)
    SEMANTIC = ("data", "start", "stop", "step")

    def draw(self, rng):
        n = rng.randint(7, 11)
        data = rng.sample(range(1, 50), n)
        name = rng.choice(("a", "xs", "vals", "data", "nums"))
        while True:
            step = rng.choice((1, 2, -1, -2, 3))
            start = rng.choice((None, rng.randint(-n + 1, n - 1)))
            stop = rng.choice((None, rng.randint(-n + 1, n - 1)))
            p = {"data": data, "start": start, "stop": stop, "step": step, "name": name}
            if self._items(p):
                return p

    def solve(self, p):
        return sum(self._items(p))

    def _items(self, p):
        a, n = p["data"], len(p["data"])
        step = p["step"]

        def norm(i, default):
            if i is None:
                return default
            i = i + n if i < 0 else i
            return min(max(i, -1 if step < 0 else 0), n - 1 if step < 0 else n)

        start = norm(p["start"], n - 1 if step < 0 else 0)
        stop = norm(p["stop"], -1 if step < 0 else n)
        out, i = [], start
        while (i < stop) if step > 0 else (i > stop):
            out.append(a[i])
            i += step
        return out

    def render(self, p):
        def part(v):
            return "" if v is None else str(v)
        step = "" if p["step"] == 1 else f":{p['step']}"
        sl = f"{part(p['start'])}:{part(p['stop'])}{step}"
        code = f"{p['name']} = {p['data']}\nprint(sum({p['name']}[{sl}]))"
        return "Что напечатает программа?", {"lang": "python", "text": code}

    def oracle_value(self, inst):
        return float(run_python(inst.code["text"]))


class FloorMod(TypedNumberFamily):
    """b = 0.1 (middle boundary): Python's // rounds toward minus infinity and % takes the sign of
    the divisor, unlike C, Java or JavaScript; with negative operands most people answer the C way."""

    meta = FamilyMeta(id="bm.py.floor_mod.v1", version=1, specs=BM, topic="python.core",
                      skills=("python",), format="code_output", a=1.2, b=0.1, c=0.0, time_limit_s=90)
    SEMANTIC = ("terms", "joins")

    def draw(self, rng):
        terms = []
        for _ in range(rng.randint(2, 3)):
            x = rng.randint(5, 40) * rng.choice((1, -1))
            y = rng.randint(2, 9) * rng.choice((1, -1))
            if x > 0 and y > 0:
                x = -x
            terms.append([x, rng.choice(("//", "%")), y])
        return {"terms": terms, "joins": [rng.choice(("+", "-")) for _ in terms[1:]]}

    def solve(self, p):
        def ev(x, op, y):
            q = x // y
            return q if op == "//" else x - y * q

        total = ev(*p["terms"][0])
        for j, t in zip(p["joins"], p["terms"][1:], strict=True):
            total = total + ev(*t) if j == "+" else total - ev(*t)
        return total

    def render(self, p):
        def fmt(t):
            x, op, y = t
            return f"({x}) {op} ({y})" if y < 0 else f"({x}) {op} {y}"

        expr = fmt(p["terms"][0])
        for j, t in zip(p["joins"], p["terms"][1:], strict=True):
            expr += f" {j} {fmt(t)}"
        return "Что напечатает программа?", {"lang": "python", "text": f"print({expr})"}

    def oracle_value(self, inst):
        return float(run_python(inst.code["text"]))


class LateBinding(TypedNumberFamily):
    """b = 1.0 (senior boundary): closures look the loop variable up when called, so every lambda
    sees its last value, unless the value is bound as a default argument. The program prints the
    sum of the calls. Version 2 is typed: derived list options were guessable by their sums
    (ML-6 re-review)."""

    meta = FamilyMeta(id="bm.py.late_binding.v2", version=2, specs=BM, topic="python.core",
                      skills=("python",), format="code_output", a=1.4, b=1.0, c=0.0, time_limit_s=90)
    SEMANTIC = ("n", "start", "k", "op", "c", "bind")

    def draw(self, rng):
        return {"n": rng.randint(3, 6), "start": rng.randint(0, 30), "k": rng.randint(2, 50),
                "op": rng.choice(("*", "+", "-")), "c": rng.randint(0, 20), "bind": rng.random() < 0.5,
                "var": rng.choice(("i", "j", "x", "step", "n", "idx")),
                "fs": rng.choice(("fs", "funcs", "handlers", "ops", "jobs", "calls"))}

    def _value(self, i, p):
        base = {"*": i * p["k"], "+": i + p["k"], "-": i - p["k"]}[p["op"]]
        return base + p["c"]

    def solve(self, p):
        vals = range(p["start"], p["start"] + p["n"])
        return sum(self._value(i if p["bind"] else vals[-1], p) for i in vals)

    def render(self, p):
        v, fs = p["var"], p["fs"]
        body = f"{v} {p['op']} {p['k']}" + (f" + {p['c']}" if p["c"] else "")
        lam = f"lambda {v}={v}: {body}" if p["bind"] else f"lambda: {body}"
        lines = [f"{fs} = []", f"for {v} in range({p['start']}, {p['start'] + p['n']}):",
                 f"    {fs}.append({lam})", f"print(sum(f() for f in {fs}))"]
        return "Что напечатает программа?", {"lang": "python", "text": "\n".join(lines)}

    def oracle_value(self, inst):
        return float(run_python(inst.code["text"]))


FAMILIES = [MutableDefault(), Slicing(), FloorMod(), LateBinding()]
