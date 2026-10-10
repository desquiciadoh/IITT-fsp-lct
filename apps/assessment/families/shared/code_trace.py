"""Shared code-reading families: trace a short Python program and type the printed number.

sh.code.binary_search_steps.v1  loop iterations of a binary search on a visible sorted list
sh.code.stack_queue.v1          pops from a stack or a queue, encoded as digits (order matters)
sh.code.loop_trace.v1           nested loops with a filter, the accumulated total
sh.code.recursion_calls.v1      how many times a tree-recursive function is called

Every answer is a typed number (c = 0). The generator computes it from the drawn parameters in
plain Python; the oracle executes the program the candidate sees (builder.run_python) and reads
what it prints, so a rendering bug makes them disagree.
"""
from __future__ import annotations

from ..base import FamilyMeta
from ..builder import TypedNumberFamily, run_python

NAMES = ("data", "items", "values", "arr", "nums", "xs", "seq", "batch")
ALL_SPECS = ("backend", "frontend", "ml_data")


class _ExecOracle(TypedNumberFamily):
    def oracle_value(self, inst):
        return float(run_python(inst.code["text"]))


class BinarySearchSteps(_ExecOracle):
    """b = 0.3 (lower middle): the loop is textbook, but counting iterations needs exact tracking
    of lo/hi/mid with integer division, and a target that is absent runs to the end."""

    meta = FamilyMeta(id="sh.code.binary_search_steps.v1", version=1, specs=ALL_SPECS,
                      topic="algorithms.code_reading", skills=("algorithms",), format="code_output",
                      a=1.2, b=0.3, c=0.0, time_limit_s=150)

    def draw(self, rng):
        n = rng.randint(9, 19)
        arr = sorted(rng.sample(range(1, 100), n))
        absent = [x for x in range(1, 100) if x not in arr]
        target = rng.choice(arr) if rng.random() < 0.6 else rng.choice(absent)
        return {"arr": arr, "target": target, "name": rng.choice(NAMES)}

    def solve(self, p):
        a, x = p["arr"], p["target"]
        lo, hi, steps = 0, len(a) - 1, 0
        while lo <= hi:
            steps += 1
            mid = (lo + hi) // 2
            if a[mid] == x:
                break
            if a[mid] < x:
                lo = mid + 1
            else:
                hi = mid - 1
        return steps

    def render(self, p):
        a = p["name"]
        lines = [
            f"def search({a}, x):",
            f"    lo, hi = 0, len({a}) - 1",
            "    steps = 0",
            "    while lo <= hi:",
            "        steps += 1",
            "        mid = (lo + hi) // 2",
            f"        if {a}[mid] == x:",
            "            return steps",
            f"        if {a}[mid] < x:",
            "            lo = mid + 1",
            "        else:",
            "            hi = mid - 1",
            "    return steps",
            "",
            "",
            f"print(search({p['arr']}, {p['target']}))",
        ]
        return "Что напечатает программа?", {"lang": "python", "text": "\n".join(lines)}


class StackQueue(_ExecOracle):
    """b = -1.2 (intern/junior): LIFO vs FIFO is basic, but the pops are interleaved with pushes,
    so the candidate has to track the structure, not recall a rule."""

    meta = FamilyMeta(id="sh.code.stack_queue.v1", version=1, specs=ALL_SPECS,
                      topic="algorithms.data_structures", skills=("data_structures",), format="code_output",
                      a=1.1, b=-1.2, c=0.0, time_limit_s=120)

    def draw(self, rng):
        kind = rng.choice(("stack", "queue"))
        values = rng.sample(range(1, 10), 9)
        ops, size, pops, vi = [], 0, 0, 0
        while pops < 4:
            if size and (vi >= len(values) or rng.random() < 0.45):
                ops.append(["pop"])
                size -= 1
                pops += 1
            else:
                ops.append(["push", values[vi]])
                vi += 1
                size += 1
        return {"kind": kind, "ops": ops, "name": rng.choice(("buf", "box", "pile", "line", "store"))}

    def solve(self, p):
        buf, result = [], 0
        for op in p["ops"]:
            if op[0] == "push":
                buf.append(op[1])
            else:
                v = buf.pop() if p["kind"] == "stack" else buf.pop(0)
                result = result * 10 + v
        return result

    def render(self, p):
        name = p["name"]
        lines = [f"{name} = []", "result = 0"]
        for op in p["ops"]:
            if op[0] == "push":
                lines.append(f"{name}.append({op[1]})")
            else:
                take = f"{name}.pop()" if p["kind"] == "stack" else f"{name}.pop(0)"
                lines.append(f"result = result * 10 + {take}")
        lines.append("print(result)")
        return "Что напечатает программа?", {"lang": "python", "text": "\n".join(lines)}


class LoopTrace(_ExecOracle):
    """b = -0.8 (junior): two nested loops with a modulo filter; careful bookkeeping, no tricks."""

    meta = FamilyMeta(id="sh.code.loop_trace.v1", version=1, specs=ALL_SPECS,
                      topic="algorithms.code_reading", skills=("algorithms",), format="code_output",
                      a=1.0, b=-0.8, c=0.0, time_limit_s=180)

    def draw(self, rng):
        mod = rng.randint(2, 5)
        return {"n": rng.randint(3, 6), "m": rng.randint(3, 6), "mod": mod, "rem": rng.randrange(mod),
                "start": rng.randint(0, 2), "ka": rng.randint(1, 4), "kb": rng.randint(1, 4),
                "k": rng.randint(0, 9),
                "acc": rng.choice(("total", "s", "acc", "res", "out", "sum_", "x", "cnt"))}

    @staticmethod
    def _expr(p):
        a = "i" if p["ka"] == 1 else f"{p['ka']} * i"
        b = "j" if p["kb"] == 1 else f"{p['kb']} * j"
        return f"{a} + {b}" + (f" + {p['k']}" if p["k"] else "")

    def solve(self, p):
        total = 0
        for i in range(p["start"], p["n"]):
            for j in range(i, p["m"] + 1):
                v = p["ka"] * i + p["kb"] * j + p["k"]
                if v % p["mod"] == p["rem"]:
                    total += v
        return total

    def render(self, p):
        acc = p["acc"]
        lines = [
            f"{acc} = 0",
            f"for i in range({p['start']}, {p['n']}):",
            f"    for j in range(i, {p['m']} + 1):",
            f"        v = {self._expr(p)}",
            f"        if v % {p['mod']} == {p['rem']}:",
            f"            {acc} += v",
            f"print({acc})",
        ]
        return "Что напечатает программа?", {"lang": "python", "text": "\n".join(lines)}


class RecursionCalls(_ExecOracle):
    """b = 0.6 (middle): counting calls of a two-branch recursion needs the call tree, not the
    value; `<` vs `<=` in the base case and two different step sizes are where people slip."""

    meta = FamilyMeta(id="sh.code.recursion_calls.v1", version=1, specs=ALL_SPECS,
                      topic="algorithms.code_reading", skills=("algorithms",), format="code_output",
                      a=1.2, b=0.6, c=0.0, time_limit_s=180)

    def draw(self, rng):
        while True:
            s1, s2 = rng.sample((1, 2, 3), 2)
            base = rng.randint(0, 2)
            p = {"s1": s1, "s2": s2, "base": base, "cmp": rng.choice(("<=", "<")),
                 "n": rng.randint(base + 2, base + 7), "n2": rng.randint(0, base + 4), "k": rng.randint(0, 9),
                 "join": rng.choice(("+", "*", "-")), "fn": rng.choice(("f", "walk", "g", "rec", "visit", "step")),
                 "counter": rng.choice(("calls", "count", "hits", "cnt"))}
            if 6 <= self.solve(p) <= 45:          # countable by hand within the time limit
                return p

    def solve(self, p):
        calls = 0

        def f(n):
            nonlocal calls
            calls += 1
            stop = n <= p["base"] if p["cmp"] == "<=" else n < p["base"]
            if stop:
                return 1
            return f(n - p["s1"]) + f(n - p["s2"])

        f(p["n"])
        f(p["n2"])
        return calls

    def render(self, p):
        fn, cnt = p["fn"], p["counter"]
        tail = f" {p['join']} {p['k']}" if p["k"] else ""
        lines = [
            f"{cnt} = 0",
            "",
            "",
            f"def {fn}(n):",
            f"    global {cnt}",
            f"    {cnt} += 1",
            f"    if n {p['cmp']} {p['base']}:",
            "        return 1",
            f"    return {fn}(n - {p['s1']}) + {fn}(n - {p['s2']}){tail}",
            "",
            "",
            f"{fn}({p['n']})",
            f"{fn}({p['n2']})",
            f"print({cnt})",
        ]
        return ("Что напечатает программа (сколько всего раз была вызвана функция)?",
                {"lang": "python", "text": "\n".join(lines)})


FAMILIES = [BinarySearchSteps(), StackQueue(), LoopTrace(), RecursionCalls()]
