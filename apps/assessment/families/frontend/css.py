"""CSS families (topic web.css).

fe.css.specificity.v1  which of four rules sets the text colour (specificity, order, !important)
fe.css.box_model.v2    content, offset or outer width of a box (content-box vs border-box, shorthands)
fe.css.flex_grow.v1    width of one flex item after free space is shared by flex-grow

Oracles parse the rendered HTML/CSS and recompute with their own rules (a selector specificity
counter, a shorthand parser, Fraction arithmetic).
"""
from __future__ import annotations

import re
from fractions import Fraction

from ..base import FamilyMeta, Instance, fingerprint_of
from ..builder import TypedNumberFamily
from ..kit import choice_options, is_choice_correct, option_key_for_text

F = ("frontend",)
COLORS = ("red", "blue", "green", "orange", "purple", "teal", "brown", "navy", "olive", "crimson", "gold", "gray")
CLASSES = ("note", "card", "title", "intro", "lead", "muted", "hint", "label", "item", "badge", "promo", "alert")
IDS = ("main", "hero", "summary", "msg", "first", "price", "headline", "status")
WRAPS = ("box", "panel", "page", "content", "layout", "wrapper")


class Specificity:
    """b = 0.4 (middle): an id beats any number of classes, classes beat elements, a later rule
    wins a tie, and !important beats specificity. Four colours, one wins."""

    meta = FamilyMeta(id="fe.css.specificity.v1", version=1, specs=F, topic="web.css",
                      skills=("css", "html"), format="code_output", a=1.2, b=0.4, c=0.25, time_limit_s=120)

    # selector templates and their specificity (ids, classes, elements)
    SELECTORS = (("p", (0, 0, 1)), ("div p", (0, 0, 2)), (".{c1}", (0, 1, 0)), ("p.{c1}", (0, 1, 1)),
                 (".{w} .{c1}", (0, 2, 0)), (".{c1}.{c2}", (0, 2, 0)), ("#{id}", (1, 0, 0)),
                 ("div #{id}", (1, 0, 1)), (".{w} p", (0, 1, 1)), ("div > p.{c2}", (0, 1, 2)),
                 (".{c2}", (0, 1, 0)), ("p#{id}", (1, 0, 1)))

    def generate(self, rng):
        names = {"c1": "", "c2": "", "id": rng.choice(IDS), "w": rng.choice(WRAPS)}
        names["c1"], names["c2"] = rng.sample(CLASSES, 2)
        picks = rng.sample(range(len(self.SELECTORS)), 4)
        colors = rng.sample(COLORS, 4)
        important = rng.randrange(4) if rng.random() < 0.3 else None
        rules = []
        for n, (sel_i, color) in enumerate(zip(picks, colors, strict=True)):
            sel, spec = self.SELECTORS[sel_i]
            rules.append((sel.format(**names), spec, color, n == important))
        # winner: !important first, then specificity, then the later rule
        ranked = sorted(range(4), key=lambda n: (rules[n][3], rules[n][1], n))
        winner = rules[ranked[-1]][2]
        css = "\n".join(f"{sel} {{ color: {color}{' !important' if imp else ''}; }}" for sel, _, color, imp in rules)
        html = (f"<div class=\"{names['w']}\">\n  <p id=\"{names['id']}\" class=\"{names['c1']} {names['c2']}\">"
                "Текст</p>\n</div>")
        options, key = choice_options(rng, winner, [c for c in colors if c != winner])
        stem = "Какого цвета будет текст абзаца?"
        code = {"lang": "html", "text": f"{html}\n\n<style>\n{css}\n</style>"}
        return Instance(stem_md=stem, input="choice", key=key, fingerprint=fingerprint_of({"picks": picks, "important": important, "colors": colors}),
                        code=code, options=options)

    def is_correct(self, key, answer):
        return is_choice_correct(key, answer)

    def oracle(self, inst: Instance):
        text = inst.code["text"]
        p_id = re.search(r'<p id="(\w+)"', text).group(1)
        p_cls = set(re.search(r'<p id="\w+" class="([\w ]+)"', text).group(1).split())
        wrap = re.search(r'<div class="(\w+)"', text).group(1)
        best = None
        for order, (sel, color, imp) in enumerate(re.findall(r"^(.+?) \{ color: (\w+)( !important)?; \}", text, re.M)):
            if not _matches(sel, p_id, p_cls, wrap):
                continue
            spec = (sel.count("#"), sel.count("."), len(re.findall(r"(?:^|[\s>])(div|p)\b", sel)))
            rank = (bool(imp), spec, order)
            if best is None or rank > best[0]:
                best = (rank, color)
        return option_key_for_text(inst.options, best[1]) if best else None


def _matches(sel: str, p_id: str, p_cls: set[str], wrap: str) -> bool:
    """Does the selector match <p id=.. class=..> inside <div class=wrap>? (the shapes used here)"""
    parts = sel.replace(">", " ").split()
    target, ancestors = parts[-1], parts[:-1]
    m = re.fullmatch(r"(p)?(?:#(\w+))?((?:\.\w+)*)", target)
    if not m:
        return False
    if m.group(2) and m.group(2) != p_id:
        return False
    if any(c not in p_cls for c in m.group(3).split(".")[1:]):
        return False
    for a in ancestors:
        if a != "div" and a != f".{wrap}":
            return False
    return True


class BoxModel(TypedNumberFamily):
    """b = -0.4 (upper junior): content-box adds horizontal padding and borders to `width`,
    border-box puts them inside it; margin is outside the box, and the padding shorthand has 1, 2
    or 4 values. Version 2 asks for the measure that differs from the declared width: the content
    width of a border-box element, the offsetWidth of a content-box one, or the outer width with
    margins. Version 1 asked offsetWidth for both, so on border-box items the answer was the first
    number in the CSS (49 % of items; ML-6 re-review)."""

    meta = FamilyMeta(id="fe.css.box_model.v2", version=2, specs=F, topic="web.css",
                      skills=("css",), format="numeric_scenario", a=1.1, b=-0.4, c=0.0, time_limit_s=120)
    SEMANTIC = ("width", "form", "pads", "border", "margin", "sizing", "ask")
    STEMS = {"inner": "Какой будет ширина области контента элемента (без padding и border) в пикселях?",
             "offset": "Какой будет ширина элемента на странице (offsetWidth) в пикселях?",
             "outer": "Сколько пикселей по горизонтали занимает элемент вместе с внешними отступами (margin)?"}

    def draw(self, rng):
        cls = rng.choice(CLASSES)
        while True:
            form = rng.choice((1, 2, 4))
            pads = [rng.randint(0, 12) * 2 for _ in range(4)]
            if form == 1:
                pads = [pads[0]] * 4                       # unused values would only look different
            elif form == 2:
                pads = [pads[0], pads[1], pads[0], pads[1]]
            p = {"width": rng.randint(10, 60) * 10, "form": form, "pads": pads, "border": rng.randint(0, 6),
                 "margin": rng.randint(1, 20) * 2, "sizing": rng.choice(("content-box", "border-box")), "cls": cls}
            p["ask"] = rng.choice(("outer", "inner" if p["sizing"] == "border-box" else "offset"))
            if self._horizontal(p) + 2 * p["border"] > 0 and self.solve(p) > 0:
                return p

    @staticmethod
    def _horizontal(p):
        return p["pads"][1] + p["pads"][3]

    def _padding(self, p):
        t, r, b, left = p["pads"]
        return {1: f"{t}px", 2: f"{t}px {r}px", 4: f"{t}px {r}px {b}px {left}px"}[p["form"]]

    def solve(self, p):
        extra = self._horizontal(p) + 2 * p["border"]
        box = p["width"] if p["sizing"] == "border-box" else p["width"] + extra
        if p["ask"] == "outer":
            return box + 2 * p["margin"]
        return box - extra if p["ask"] == "inner" else box

    def render(self, p):
        css = (f".{p['cls']} {{\n  box-sizing: {p['sizing']};\n  width: {p['width']}px;\n  padding: {self._padding(p)};\n"
               f"  border: {p['border']}px solid black;\n  margin: {p['margin']}px;\n}}")
        return self.STEMS[p["ask"]], {"lang": "css", "text": css}

    def oracle_value(self, inst):
        css = inst.code["text"]
        decl = dict(re.findall(r"^\s+([\w-]+): (.+?);$", css, re.M))
        width = int(decl["width"].removesuffix("px"))
        pads = [int(x.removesuffix("px")) for x in decl["padding"].split()]
        trbl = {1: pads * 4, 2: pads * 2, 4: pads}[len(pads)][:4]
        border = int(decl["border"].split()[0].removesuffix("px"))
        margin = int(decl["margin"].removesuffix("px"))
        content = width - trbl[1] - trbl[3] - 2 * border if decl["box-sizing"] == "border-box" else width
        offset = content + trbl[1] + trbl[3] + 2 * border
        if "вместе с внешними отступами" in inst.stem_md:
            return float(offset + 2 * margin)
        return float(content if "области контента" in inst.stem_md else offset)


class FlexGrow(TypedNumberFamily):
    """b = 1.0 (senior boundary): flex-grow shares the *free* space (container minus bases and
    gaps) in proportion to the factors; it does not split the whole width."""

    meta = FamilyMeta(id="fe.css.flex_grow.v1", version=1, specs=F, topic="web.css",
                      skills=("css",), format="numeric_scenario", a=1.3, b=1.0, c=0.0, time_limit_s=150)
    SEMANTIC = ('bases', 'grows', 'gap', 'width', 'ask')
    DECIMALS = 1

    def draw(self, rng):
        while True:
            n = rng.randint(2, 4)
            bases = [rng.randint(2, 20) * 10 for _ in range(n)]
            grows = [rng.randint(0, 3) for _ in range(n)]
            gap = rng.choice((0, 0, 8, 10, 16, 20))
            width = rng.randint(30, 120) * 10
            if sum(grows) and width - sum(bases) - gap * (n - 1) > 0:
                return {"bases": bases, "grows": grows, "gap": gap, "width": width,
                        "ask": rng.choice([i for i in range(n) if grows[i]]), "cls": rng.choice(CLASSES)}

    def solve(self, p):
        free = p["width"] - sum(p["bases"]) - p["gap"] * (len(p["bases"]) - 1)
        i = p["ask"]
        return p["bases"][i] + free * p["grows"][i] / sum(p["grows"])

    def render(self, p):
        items = "\n".join(f".item-{k + 1} {{ flex-grow: {g}; flex-shrink: 0; flex-basis: {b}px; }}"
                          for k, (b, g) in enumerate(zip(p["bases"], p["grows"], strict=True)))
        css = (f".{p['cls']} {{ display: flex; width: {p['width']}px; gap: {p['gap']}px; padding: 0; }}\n"
               f"{items}")
        return (f"В контейнере `.{p['cls']}` по одному элементу каждого класса `.item-N` (без рамок, отступов и "
                f"min/max-размеров). Какой будет ширина элемента `.item-{p['ask'] + 1}` в пикселях?",
                {"lang": "css", "text": css})

    def oracle_value(self, inst):
        css = inst.code["text"]
        width = int(re.search(r"width: (\d+)px", css).group(1))
        gap = int(re.search(r"gap: (\d+)px", css).group(1))
        items = [(int(g), int(b)) for g, b in re.findall(r"flex-grow: (\d+); flex-shrink: 0; flex-basis: (\d+)px", css)]
        ask = int(re.search(r"элемента `\.item-(\d+)`", inst.stem_md).group(1)) - 1
        sizes = [Fraction(b) for _, b in items]
        free = width - sum(sizes) - gap * (len(items) - 1)
        total_grow = sum(g for g, _ in items)
        for k, (g, _) in enumerate(items):          # hand out the free space item by item
            sizes[k] += free * Fraction(g, total_grow)
        return float(sizes[ask])


FAMILIES = [Specificity(), BoxModel(), FlexGrow()]
