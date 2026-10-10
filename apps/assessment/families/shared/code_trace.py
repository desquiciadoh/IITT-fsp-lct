"""Shared code-reading families: trace a short Python program and type the printed number.

sh.code.binary_search_steps.v2  sum of the mid indices a binary search visits on a visible progression
sh.code.stack_queue.v1          pops from a stack or a queue, encoded as digits (order matters)
sh.code.loop_trace.v1           nested loops with a filter, the accumulated total
sh.code.recursion_calls.v2      sum of the values a pruned recursive tree walk visits

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
    """b = 0.5 (middle): the loop is textbook, but the printed value is the sum of every `mid`
    visited, so the candidate has to track lo/hi/mid with integer division on an arithmetic
    progression of 20-60 elements, and an absent target runs to the end. Version 2: version 1
    printed the step count, and "4" was right on 55 % of items (ML-6 review)."""

    meta = FamilyMeta(id="sh.code.binary_search_steps.v2", version=2, specs=ALL_SPECS,
                      topic="algorithms.code_reading", skills=("algorithms",), format="code_output",
                      a=1.2, b=0.5, c=0.0, time_limit_s=180)
    SEMANTIC = ("n", "first", "d", "target")

    def draw(self, rng):
        n, first, d = rng.randint(20, 60), rng.randint(0, 50), rng.randint(2, 9)
        if rng.random() < 0.6:
            target = first + d * rng.randrange(n)
        else:                                             # absent: between two elements or outside
            target = first + d * rng.randrange(-1, n + 1) + rng.randint(1, d - 1)
        return {"n": n, "first": first, "d": d, "target": target, "name": rng.choice(NAMES)}

    def solve(self, p):
        a = [p["first"] + p["d"] * i for i in range(p["n"])]
        lo, hi, trace = 0, len(a) - 1, 0
        while lo <= hi:
            mid = (lo + hi) // 2
            trace += mid
            if a[mid] == p["target"]:
                break
            if a[mid] < p["target"]:
                lo = mid + 1
            else:
                hi = mid - 1
        return trace

    def render(self, p):
        a = p["name"]
        stop = p["first"] + p["d"] * p["n"]
        lines = [
            f"def search({a}, x):",
            f"    lo, hi = 0, len({a}) - 1",
            "    trace = 0",
            "    while lo <= hi:",
            "        mid = (lo + hi) // 2",
            "        trace += mid",
            f"        if {a}[mid] == x:",
            "            return trace",
            f"        if {a}[mid] < x:",
            "            lo = mid + 1",
            "        else:",
            "            hi = mid - 1",
            "    return trace",
            "",
            "",
            f"print(search(list(range({p['first']}, {stop}, {p['d']})), {p['target']}))",
        ]
        return "Что напечатает программа?", {"lang": "python", "text": "\n".join(lines)}


class StackQueue(_ExecOracle):
    """b = -1.2 (intern/junior): LIFO vs FIFO is basic, but the pops are interleaved with pushes,
    so the candidate has to track the structure, not recall a rule."""

    meta = FamilyMeta(id="sh.code.stack_queue.v1", version=1, specs=ALL_SPECS,
                      topic="algorithms.data_structures", skills=("data_structures",), format="code_output",
                      a=1.1, b=-1.2, c=0.0, time_limit_s=120)
    SEMANTIC = ("kind", "ops")

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
    """b = -0.8 (junior): two nested loops with a modulo filter; careful bookkeeping, no tricks.
    Draws whose total is 0 are redrawn: "0" was right on 13 % of items (ML-6 review)."""

    meta = FamilyMeta(id="sh.code.loop_trace.v1", version=1, specs=ALL_SPECS,
                      topic="algorithms.code_reading", skills=("algorithms",), format="code_output",
                      a=1.0, b=-0.8, c=0.0, time_limit_s=180)
    SEMANTIC = ("n", "m", "mod", "rem", "start", "ka", "kb", "k")

    def draw(self, rng):
        acc = rng.choice(("total", "s", "acc", "res", "out", "sum_", "x", "cnt"))
        while True:
            mod = rng.randint(2, 5)
            p = {"n": rng.randint(3, 7), "m": rng.randint(3, 7), "mod": mod, "rem": rng.randrange(mod),
                 "start": rng.randint(0, 2), "ka": rng.randint(1, 4), "kb": rng.randint(1, 4),
                 "k": rng.randint(0, 19), "acc": acc}
            if self.solve(p):
                return p

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
    """b = 0.5 (middle): a recursive walk over a small tree that adds each visited value and stops
    descending below a node whose value is over the limit (the node itself is still added). The
    candidate has to follow the call tree and the early return, not a formula. Version 2: version
    1 counted calls of a two-branch recursion; with only a few hundred distinct call trees the
    same question repeated in 35 % of draws once names were excluded from the fingerprint (ML-6
    review)."""

    meta = FamilyMeta(id="sh.code.recursion_calls.v2", version=2, specs=ALL_SPECS,
                      topic="algorithms.code_reading", skills=("algorithms",), format="code_output",
                      a=1.2, b=0.5, c=0.0, time_limit_s=180)
    SEMANTIC = ("tree", "limit")

    def draw(self, rng):
        fn = rng.choice(("walk", "visit", "dfs", "go", "explore", "scan"))
        acc = rng.choice(("total", "acc", "s", "seen", "score"))
        while True:
            values = [rng.randint(1, 40) for _ in range(rng.randint(7, 11))]
            parents = [None] + [rng.randrange(i) for i in range(1, len(values))]
            nodes = [[v, []] for v in values]
            for child, parent in enumerate(parents):
                if parent is not None:
                    nodes[parent][1].append(nodes[child])
            limit = rng.randint(10, 35)
            p = {"tree": nodes[0], "limit": limit, "fn": fn, "acc": acc}
            pruned = [n for n in nodes if n[0] > limit and n[1]]
            if pruned and len(self._visited(p["tree"], limit)) < len(values):
                return p

    @staticmethod
    def _visited(node, limit):
        out = [node[0]]
        if node[0] <= limit:
            for kid in node[1]:
                out += RecursionCalls._visited(kid, limit)
        return out

    def solve(self, p):
        return sum(self._visited(p["tree"], p["limit"]))

    @staticmethod
    def _literal(node):
        return "(" + str(node[0]) + ", [" + ", ".join(RecursionCalls._literal(k) for k in node[1]) + "])"

    def render(self, p):
        fn, acc = p["fn"], p["acc"]
        lines = [
            f"tree = {self._literal(p['tree'])}",
            f"{acc} = 0",
            "",
            "",
            f"def {fn}(node):",
            f"    global {acc}",
            "    value, kids = node",
            f"    {acc} += value",
            f"    if value > {p['limit']}:",
            "        return",
            "    for kid in kids:",
            f"        {fn}(kid)",
            "",
            "",
            f"{fn}(tree)",
            f"print({acc})",
        ]
        return "Что напечатает программа?", {"lang": "python", "text": "\n".join(lines)}


FAMILIES = [BinarySearchSteps(), StackQueue(), LoopTrace(), RecursionCalls()]
