"""Frontend families on React, the browser, TypeScript and web security.

fe.react.state_batching.v1  value after one click with batched setState calls (typed)
fe.react.effect_runs.v1     how many times a useEffect runs over a sequence of renders (typed)
fe.web.cache_control.v1     what the browser does with a cached response (classification, 3 classes)
fe.ts.assignability.v1      which of four lines fails to type-check (find_bug, 4 line options)
fe.sec.xss_sink.v1          which of four lines inserts user input unsafely (find_bug, 4 line options)
"""
from __future__ import annotations

import re

from ..base import FamilyMeta, Instance
from ..builder import ClassificationFamily, TypedNumberFamily

F = ("frontend",)
STATE = ("count", "clicks", "score", "total", "votes", "likes")


class StateBatching(TypedNumberFamily):
    """b = 0.6 (middle): updates in one handler are batched; `setX(x + n)` reads the value from
    this render every time, `setX(prev => prev + n)` chains on the queued value, and a plain
    `setX(v)` replaces whatever was queued before it."""

    meta = FamilyMeta(id="fe.react.state_batching.v1", version=1, specs=F, topic="web.react",
                      skills=("react",), format="code_output", a=1.3, b=0.6, c=0.0, time_limit_s=120)

    def draw(self, rng):
        calls = []
        for _ in range(rng.randint(3, 5)):
            kind = rng.choice(("stale", "fn", "fn", "set"))
            calls.append([kind, rng.randint(1, 9) if kind != "set" else rng.randint(0, 50)])
        return {"init": rng.randint(0, 20), "calls": calls, "name": rng.choice(STATE),
                "comp": rng.choice(("Counter", "Voter", "Score", "Likes", "Panel"))}

    def solve(self, p):
        value = p["init"]                         # the queue is applied in order on the next render
        for kind, n in p["calls"]:
            if kind == "stale":
                value = p["init"] + n
            elif kind == "fn":
                value = value + n
            else:
                value = n
        return value

    def render(self, p):
        x = p["name"]
        setter = "set" + x[0].upper() + x[1:]
        body = []
        for kind, n in p["calls"]:
            if kind == "stale":
                body.append(f"    {setter}({x} + {n});")
            elif kind == "fn":
                body.append(f"    {setter}(prev => prev + {n});")
            else:
                body.append(f"    {setter}({n});")
        code = (f"function {p['comp']}() {{\n  const [{x}, {setter}] = useState({p['init']});\n"
                "  function handleClick() {\n" + "\n".join(body) + "\n  }\n"
                f"  return <button onClick={{handleClick}}>{{{x}}}</button>;\n}}")
        return ("Компонент отрисован впервые, затем пользователь один раз нажал кнопку (React 18). "
                "Какое число будет на кнопке после повторного рендера?", {"lang": "javascript", "text": code})

    def oracle_value(self, inst):
        text = inst.code["text"]
        init = int(re.search(r"useState\((\d+)\)", text).group(1))
        name = re.search(r"const \[(\w+),", text).group(1)
        queue = []
        for line in text.split("handleClick() {")[1].split("\n  }")[0].strip().split("\n"):
            arg = line.strip()[line.strip().index("(") + 1:-2]
            if arg.startswith("prev =>"):
                n = int(arg.split("+")[1])
                queue.append(lambda v, n=n: v + n)
            elif arg.startswith(name):
                n = int(arg.split("+")[1])
                queue.append(lambda v, n=n: init + n)       # closure over this render's value
            else:
                queue.append(lambda v, n=int(arg): n)
        value = init
        for update in queue:
            value = update(value)
        return float(value)


class EffectRuns(TypedNumberFamily):
    """b = -0.2 (upper junior): no dependency array runs after every render, `[]` once after
    mount, `[x]` on mount and whenever x changed since the previous render."""

    meta = FamilyMeta(id="fe.react.effect_runs.v1", version=1, specs=F, topic="web.react",
                      skills=("react",), format="code_output", a=1.1, b=-0.2, c=0.0, time_limit_s=90)

    def draw(self, rng):
        n = rng.randint(4, 8)
        values = [rng.randint(1, 4) for _ in range(n)]
        return {"deps": rng.choice(("none", "empty", "dep", "dep")), "values": values,
                "prop": rng.choice(("userId", "page", "query", "theme", "filter", "tab", "lang", "sort")),
                "comp": rng.choice(("Profile", "List", "Search", "Feed", "Chart", "Table", "Cart", "Inbox"))}

    def solve(self, p):
        v = p["values"]
        if p["deps"] == "none":
            return len(v)
        if p["deps"] == "empty":
            return 1
        return 1 + sum(1 for a, b in zip(v, v[1:], strict=False) if a != b)

    def render(self, p):
        deps = {"none": "", "empty": ", []", "dep": f", [{p['prop']}]"}[p["deps"]]
        code = (f"function {p['comp']}({{ {p['prop']} }}) {{\n"
                f"  useEffect(() => {{\n    console.log('effect');\n  }}{deps});\n"
                f"  return <div>{{{p['prop']}}}</div>;\n}}")
        renders = ", ".join(str(x) for x in p["values"])
        return (f"Компонент отрендерился {len(p['values'])} раз подряд (без размонтирования, без StrictMode) "
                f"со значениями `{p['prop']}`: {renders}. Сколько раз выполнится эффект (выведется 'effect')?",
                {"lang": "javascript", "text": code})

    def oracle_value(self, inst):
        values = [int(x) for x in re.search(r"`: ([\d, ]+)\.", inst.stem_md).group(1).split(",")]
        deps = re.search(r"\}(, \[[^\]]*\])?\);", inst.code["text"]).group(1)
        runs, previous = 0, None
        for i, v in enumerate(values):             # replay the renders
            if deps is None or (deps == ", []" and i == 0) or (deps not in (None, ", []") and (i == 0 or v != previous)):
                runs += 1
            previous = v
        return float(runs)


class CacheControl(ClassificationFamily):
    """b = 0.9 (upper middle): max-age decides freshness; a stale response with a validator is
    revalidated (304), `no-cache` always revalidates, `no-store` is never reused."""

    meta = FamilyMeta(id="fe.web.cache_control.v1", version=1, specs=F, topic="web.browser",
                      skills=("javascript", "rest_api"), format="concept_mcq", a=1.2, b=0.9, c=1 / 3,
                      time_limit_s=90)
    LABELS = ("Берёт ответ из кэша без запроса к серверу", "Отправляет условный запрос (If-None-Match)",
              "Загружает ресурс заново полностью")

    def draw(self, rng, label):
        etag = f'"{rng.getrandbits(32):08x}"'
        if label == self.LABELS[0]:
            max_age = rng.randint(2, 600) * 10
            return {"cc": f"max-age={max_age}", "etag": etag if rng.random() < 0.5 else None,
                    "age": rng.randint(0, max_age - 1), "path": _path(rng)}
        if label == self.LABELS[1]:
            if rng.random() < 0.5:
                return {"cc": "no-cache", "etag": etag, "age": rng.randint(0, 600), "path": _path(rng)}
            max_age = rng.randint(1, 600) * 10
            return {"cc": f"max-age={max_age}", "etag": etag, "age": max_age + rng.randint(1, 900),
                    "path": _path(rng)}
        choice = rng.randrange(3)
        if choice == 0:
            return {"cc": "no-store", "etag": etag if rng.random() < 0.5 else None, "age": rng.randint(0, 600),
                    "path": _path(rng)}
        if choice == 1:
            max_age = rng.randint(1, 600) * 10
            return {"cc": f"max-age={max_age}", "etag": None, "age": max_age + rng.randint(1, 900),
                    "path": _path(rng)}
        return {"cc": "no-cache", "etag": None, "age": rng.randint(0, 600), "path": _path(rng)}

    def render(self, p):
        headers = [f"Cache-Control: {p['cc']}"] + ([f"ETag: {p['etag']}"] if p["etag"] else [])
        code = "HTTP/1.1 200 OK\nContent-Type: application/json\n" + "\n".join(headers)
        return (f"Браузер получил ответ на `GET {p['path']}` с заголовками ниже (других заголовков кэширования "
                f"нет) и сохранил его в кэше. Через {p['age']} с страница снова запрашивает тот же URL. Что "
                "сделает браузер?", {"lang": "http", "text": code})

    def classify(self, inst: Instance):
        text = inst.code["text"]
        cc = re.search(r"Cache-Control: (.+)", text).group(1).strip()
        has_etag = "ETag:" in text
        age = int(re.search(r"Через (\d+) с", inst.stem_md).group(1))
        if cc == "no-store":
            return self.LABELS[2]
        fresh = cc.startswith("max-age=") and age < int(cc.split("=")[1])
        if fresh:
            return self.LABELS[0]
        return self.LABELS[1] if has_etag else self.LABELS[2]


def _path(rng):
    return f"/api/{rng.choice(('profile', 'catalog', 'feed', 'cart', 'settings', 'news'))}/{rng.randint(1, 99999)}"


# ── TypeScript assignability ───────────────────────────────────────────────

TS_PROPS = (("name", "string", "'Ann'"), ("age", "number", "30"), ("active", "boolean", "true"),
            ("email", "string", "'a@b.ru'"), ("score", "number", "7"), ("admin", "boolean", "false"))


class Assignability(ClassificationFamily):
    """b = 0.3 (lower middle): structural typing accepts extra properties from a variable, but an
    object literal gets the excess-property check; a missing required property or a wrong type
    fails either way, a missing optional one does not."""

    meta = FamilyMeta(id="fe.ts.assignability.v1", version=1, specs=F, topic="web.typescript",
                      skills=("typescript",), format="find_bug", a=1.2, b=0.3, c=0.25, time_limit_s=120)
    LABELS = ("Строка A", "Строка B", "Строка C", "Строка D")
    # (kind, is_error): literal_ok, literal_excess*, literal_missing*, literal_wrongtype*, var_extra (ok),
    # missing_optional (ok), var_missing*
    OK_KINDS = ("literal_ok", "var_extra", "missing_optional")
    BAD_KINDS = ("literal_excess", "literal_missing", "literal_wrongtype", "var_missing")

    def draw(self, rng, label):
        props = rng.sample(TS_PROPS, 3)
        optional = props[2][0]
        bad_at = self.LABELS.index(label)
        kinds = [rng.choice(self.BAD_KINDS) if i == bad_at else rng.choice(self.OK_KINDS) for i in range(4)]
        extra = rng.choice([p for p in TS_PROPS if p not in props])
        return {"props": [list(p) for p in props], "optional": optional, "kinds": kinds, "extra": list(extra),
                "type": rng.choice(("User", "Account", "Member", "Profile", "Person")),
                "vars": rng.sample(["u1", "u2", "u3", "u4", "a", "b", "c", "d"], 4)}

    def _literal(self, fields):
        return "{ " + ", ".join(f"{k}: {v}" for k, v in fields) + " }"

    def _line(self, i, p):
        req = [(k, v) for k, _, v in p["props"]]
        t, var = p["type"], p["vars"][i]
        kind = p["kinds"][i]
        if kind == "literal_ok":
            return f"const {var}: {t} = {self._literal(req)};"
        if kind == "missing_optional":
            return f"const {var}: {t} = {self._literal(req[:2])};"
        if kind == "literal_excess":
            return f"const {var}: {t} = {self._literal(req + [(p['extra'][0], p['extra'][2])])};"
        if kind == "literal_missing":
            return f"const {var}: {t} = {self._literal(req[1:])};"
        if kind == "literal_wrongtype":
            wrong = {"string": "42", "number": "'42'", "boolean": "'yes'"}[p["props"][0][1]]
            return f"const {var}: {t} = {self._literal([(req[0][0], wrong), *req[1:]])};"
        source = f"raw{i}"
        fields = req + [(p["extra"][0], p["extra"][2])] if kind == "var_extra" else req[1:]
        return f"const {source} = {self._literal(fields)};\nconst {var}: {t} = {source};"

    def render(self, p):
        fields = "\n".join(f"  {k}{'?' if k == p['optional'] else ''}: {t};" for k, t, _ in p["props"])
        lines = [f"interface {p['type']} {{\n{fields}\n}}", ""]
        for i in range(4):
            lines.append(f"// {self.LABELS[i]}\n{self._line(i, p)}")
        return ("Ровно одна из помеченных строк не пройдёт проверку типов TypeScript (strict). Какая?",
                {"lang": "typescript", "text": "\n".join(lines)})

    def classify(self, inst: Instance):
        text = inst.code["text"]
        iface = re.search(r"interface \w+ \{\n(.*?)\n\}", text, re.S).group(1)
        decl = {m[0]: (m[1] == "?", m[2]) for m in re.findall(r"(\w+)(\??): (\w+);", iface)}
        blocks = re.split(r"// (Строка [A-D])\n", text)[1:]
        literals = dict(re.findall(r"const (raw\d) = (\{.*?\});", text))
        errors = []
        for label, body in zip(blocks[0::2], blocks[1::2], strict=True):
            last = body.strip().split("\n")[-1]
            rhs = last.split(" = ", 1)[1].rstrip(";")
            fresh = rhs.startswith("{")
            obj = rhs if fresh else literals[rhs]
            fields = dict(re.findall(r"(\w+): ('[^']*'|\w+)", obj))
            def ts_type(v):
                return "string" if v.startswith("'") else "boolean" if v in ("true", "false") else "number"
            bad = any(not opt and k not in fields for k, (opt, _) in decl.items())
            bad |= any(k in decl and ts_type(v) != decl[k][1] for k, v in fields.items())
            bad |= fresh and any(k not in decl for k in fields)
            if bad:
                errors.append(label)
        return errors[0] if len(errors) == 1 else None


# ── XSS sinks ──────────────────────────────────────────────────────────────

SAFE_SINKS = ("{el}.textContent = {v};", "{el}.innerText = {v};", "{el}.setAttribute('title', {v});",
              "{el}.append(document.createTextNode({v}));", "{el}.value = {v};", "{el}.dataset.note = {v};")
UNSAFE_SINKS = ("{el}.innerHTML = {v};", "{el}.insertAdjacentHTML('beforeend', {v});",
                "document.write({v});", "{el}.outerHTML = {v};", "{el}.setAttribute('href', 'javascript:' + {v});")


class XssSink(ClassificationFamily):
    """b = -0.2 (upper junior): user input written through innerHTML-like sinks is parsed as
    HTML; textContent, attributes like title and text nodes are not."""

    meta = FamilyMeta(id="fe.sec.xss_sink.v1", version=1, specs=F, topic="web.security",
                      skills=("security", "javascript"), format="find_bug", a=1.1, b=-0.2, c=0.25,
                      time_limit_s=90)
    LABELS = ("Строка 1", "Строка 2", "Строка 3", "Строка 4")

    def draw(self, rng, label):
        bad = self.LABELS.index(label)
        safe = rng.sample(range(len(SAFE_SINKS)), 3)
        lines, k = [], 0
        for i in range(4):
            if i == bad:
                lines.append(["u", rng.randrange(len(UNSAFE_SINKS))])
            else:
                lines.append(["s", safe[k]])
                k += 1
        return {"lines": lines, "v": rng.choice(("comment", "userName", "query", "bio", "title", "message")),
                "els": [rng.choice(("box", "out", "card", "row", "cell", "badge", "note", "hint")) + str(rng.randint(1, 9))
                        for _ in range(4)],
                "param": rng.choice(("q", "name", "text", "c", "msg"))}

    def render(self, p):
        out = [f"const {p['v']} = new URLSearchParams(location.search).get('{p['param']}');"]
        for i, (kind, idx) in enumerate(p["lines"]):
            tpl = UNSAFE_SINKS[idx] if kind == "u" else SAFE_SINKS[idx]
            out.append(f"/* {i + 1} */ " + tpl.format(el=p["els"][i], v=p["v"]))
        return ("Значение берётся из адресной строки (его контролирует атакующий). Какая из пронумерованных строк "
                "создаёт XSS-уязвимость?", {"lang": "javascript", "text": "\n".join(out)})

    def classify(self, inst: Instance):
        dangerous = (r"\.innerHTML =", r"insertAdjacentHTML\(", r"document\.write\(", r"\.outerHTML =",
                     r"'javascript:'")
        hits = [m.group(1) for line in inst.code["text"].split("\n")
                if (m := re.match(r"/\* (\d) \*/", line)) and any(re.search(d, line) for d in dangerous)]
        return f"Строка {hits[0]}" if len(hits) == 1 else None


FAMILIES = [StateBatching(), EffectRuns(), CacheControl(), Assignability(), XssSink()]
