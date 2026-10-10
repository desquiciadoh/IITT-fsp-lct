"""Backend HTTP and security families (classification; fixed option sets, uniform answers).

be.http.status_code.v1  which status code fits a described situation (8 codes)
be.http.method.v1       which HTTP method fits a described operation (5 methods)
be.sec.vuln_class.v1    which vulnerability a short handler has (6 classes)

Oracles are rule tables over the rendered text that look for marker phrases or code
patterns, written separately from the generators and reviewed by hand. They catch rendering
and labelling errors, not reasoning errors.
"""
from __future__ import annotations

import re

from ..base import FamilyMeta, Instance
from ..builder import ClassificationFamily

RESOURCES = ("orders", "users", "invoices", "tickets", "projects", "comments", "payments", "files",
             "teams", "reports", "devices", "vacancies")
ROLES = ("viewer", "guest", "analyst", "support", "intern", "auditor")
# Each context carries its own preposition ("во внутреннем", not "в внутреннем").
CONTEXTS = ("В сервисе интернет-магазина", "В API банковского приложения", "Во внутреннем сервисе склада",
            "В CRM для отдела продаж", "В сервисе бронирования", "В API платформы курсов", "В сервисе доставки",
            "В API трекера задач", "В сервисе учёта рабочего времени", "В API медицинской системы",
            "В сервисе аренды самокатов", "В API маркетплейса")


def _plural(n: int, forms: tuple[str, str, str]) -> str:
    """Russian plural: 1 минуту, 2 минуты, 5 минут, 21 минуту, 12 минут."""
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return forms[1]
    return forms[2]


class StatusCode(ClassificationFamily):
    """b = -1.3 (intern/junior): 401 vs 403, 404, 409 vs 422 and 201/204 are what every backend
    developer meets on day one; the 401/403 and 409/422 pairs are the usual confusions. The
    "unique code already taken" scenario was removed in the ML-6 review: frameworks answer it
    with 400, 409 or 422, so its key was contestable. Concept item: the question is the label and
    the template; ids, resources and contexts are decoration (verify.CONCEPT_FAMILIES)."""

    meta = FamilyMeta(id="be.http.status_code.v1", version=1, specs=("backend",), topic="backend.http",
                      skills=("rest_api",), format="concept_mcq", a=1.0, b=-1.3, c=1 / 8, time_limit_s=60)
    LABELS = ("201 Created", "204 No Content", "401 Unauthorized", "403 Forbidden", "404 Not Found",
              "409 Conflict", "422 Unprocessable Content", "429 Too Many Requests")
    SEMANTIC = ("tpl",)
    SCENARIOS = {
        "201 Created": ["Запрос `POST /api/{res}` успешно создал новую запись с id {id}; в ответе нужно "
                        "вернуть её и заголовок Location.",
                        "Запрос `POST /api/{res}/{id}/comments` добавил новый комментарий; клиенту нужно вернуть "
                        "появившийся объект и его адрес."],
        "204 No Content": ["Запрос `DELETE /api/{res}/{id}` успешно удалил запись; тело ответа не требуется.",
                           "Запрос `PUT /api/{res}/{id}/archive` выполнен успешно; тело ответа не требуется."],
        "401 Unauthorized": ["Запрос `GET /api/{res}` пришёл без заголовка Authorization: клиент не "
                             "аутентифицирован.",
                             "Запрос `GET /api/{res}/{id}` пришёл с токеном, срок действия которого истёк "
                             "{n} {n_minutes} назад."],
        "403 Forbidden": ["Пользователь вошёл в систему с ролью `{role}`, но этой роли запрещено изменять "
                          "`{res}`; он отправил `PATCH /api/{res}/{id}`.",
                          "Аутентифицированный пользователь отправил `DELETE /api/{res}/{id}`, но удалять запись "
                          "разрешено только её владельцу, а он им не является."],
        "404 Not Found": ["Запрос `GET /api/{res}/{id}`: записи с таким id в базе не существует.",
                          "Клиент обратился к `GET /api/{res}-export/{id}`, но такого маршрута в API нет."],
        "409 Conflict": ["Запрос `PUT /api/{res}/{id}` пришёл с version={v}, а в базе уже version={v2}: "
                         "запись успели изменить (оптимистичная блокировка).",
                         "Два менеджера одновременно редактировали `{res}/{id}`; второй прислал `PUT` с номером "
                         "ревизии {v} в теле, а актуальная ревизия в базе уже {v2}."],
        "422 Unprocessable Content": ["Тело запроса `POST /api/{res}` — корректный JSON, но поле `amount` "
                                      "= {neg}, а по правилам валидации оно должно быть больше нуля.",
                                      "Тело запроса `PATCH /api/{res}/{id}` разобрано без ошибок, но поле "
                                      "`deadline` содержит дату в прошлом, что запрещено бизнес-правилом."],
        "429 Too Many Requests": ["Клиент отправил {burst} {burst_requests} за минуту к `/api/{res}` при лимите "
                                  "{n} {n_requests} в минуту.",
                                  "Партнёрская интеграция исчерпала квоту: {burst} {burst_calls} к `/api/{res}` "
                                  "за час при лимите {n} в час."],
    }
    MARKERS = {  # oracle: phrases that appear only in that class's scenarios
        "201 Created": ("создал новую запись", "добавил новый комментарий"), "204 No Content": "тело ответа не требуется",
        "401 Unauthorized": ("без заголовка Authorization", "срок действия которого истёк"),
        "403 Forbidden": ("этой роли запрещено", "только её владельцу"),
        "404 Not Found": ("записи с таким id в базе не существует", "такого маршрута в API нет"),
        "409 Conflict": ("оптимистичная блокировка", "актуальная ревизия"),
        "422 Unprocessable Content": ("правилам валидации", "запрещено бизнес-правилом"),
        "429 Too Many Requests": ("при лимите", "исчерпала квоту"),
    }

    def draw(self, rng, label):
        n = rng.randint(5, 120)
        v = rng.randint(1, 40)
        return {"tpl": rng.randrange(len(self.SCENARIOS[label])), "res": rng.choice(RESOURCES),
                "id": rng.randint(1, 99999), "role": rng.choice(ROLES), "n": n, "burst": n + rng.randint(1, 300),
                "v": v, "v2": v + rng.randint(1, 5),
                "neg": -rng.randint(1, 5000), "ctx": rng.randrange(len(CONTEXTS)), "rid": rng.randint(1000, 99999)}

    def render(self, p):
        words = {"n_minutes": _plural(p["n"], ("минуту", "минуты", "минут")),
                 "n_requests": _plural(p["n"], ("запрос", "запроса", "запросов")),
                 "burst_requests": _plural(p["burst"], ("запрос", "запроса", "запросов")),
                 "burst_calls": _plural(p["burst"], ("вызов", "вызова", "вызовов"))}
        text = self.SCENARIOS[p["label"]][p["tpl"]].format(**p, **words)
        return f"{CONTEXTS[p['ctx']]} (запрос #{p['rid']}): {text} Какой код ответа должен вернуть сервер?", None

    def classify(self, inst: Instance):
        hits = [label for label, m in self.MARKERS.items()
                if any(x in inst.stem_md for x in ((m,) if isinstance(m, str) else m))]
        return hits[0] if len(hits) == 1 else None


class Method(ClassificationFamily):
    """b = -1.6 (intern): the five methods and their meaning (GET reads, POST creates, PUT replaces
    the whole resource, PATCH changes part of it, DELETE removes it). Concept item (see StatusCode)."""

    meta = FamilyMeta(id="be.http.method.v1", version=1, specs=("backend",), topic="backend.http",
                      skills=("rest_api",), format="concept_mcq", a=0.9, b=-1.6, c=0.2, time_limit_s=45)
    LABELS = ("GET", "POST", "PUT", "PATCH", "DELETE")
    SEMANTIC = ("tpl",)
    SCENARIOS = {
        "GET": ["Получить список `{res}` с фильтром `status={st}` и пагинацией (страница {n}).",
                "Прочитать одну запись `{res}` с id {id}, ничего не меняя."],
        "POST": ["Создать новую запись в коллекции `{res}`; id назначит сервер.",
                 "Добавить новую запись `{res}` от имени пользователя {id}; id ещё неизвестен."],
        "PUT": ["Полностью заменить запись `{res}/{id}` новым представлением: все поля передаются целиком.",
                "Обновить ресурс `{res}/{id}` методом полной перезаписи состояния документа."],
        "PATCH": ["Изменить у записи `{res}/{id}` только одно поле `{field}`, остальные поля не трогать.",
                  "Применить частичное обновление к `{res}/{id}`, модифицируя только `{field}`."],
        "DELETE": ["Удалить запись `{res}/{id}` навсегда.",
                   "Безвозвратно стереть объект `{res}/{id}` из хранилища."],
    }
    MARKERS = {"GET": ("Получить список", "ничего не меняя"), "POST": ("Создать новую запись", "id ещё неизвестен"),
               "PUT": ("Полностью заменить", "полной перезаписи"),
               "PATCH": ("только одно поле", "частичное обновление"),
               "DELETE": ("Удалить запись", "Безвозвратно стереть")}

    def draw(self, rng, label):
        return {"tpl": rng.randrange(len(self.SCENARIOS[label])), "res": rng.choice(RESOURCES),
                "id": rng.randint(1, 999999), "n": rng.randint(2, 5000),
                "st": rng.choice(("open", "closed", "draft", "paid", "new", "archived")),
                "field": rng.choice(("title", "status", "priority", "email", "comment", "deadline")),
                "ctx": rng.randrange(len(CONTEXTS)), "rid": rng.randint(100000, 999999999)}

    def render(self, p):
        text = self.SCENARIOS[p["label"]][p["tpl"]].format(**p)
        return (f"{CONTEXTS[p['ctx']]} (задача #{p['rid']}): {text} Какой HTTP-метод соответствует этой "
                "операции в REST API?", None)

    def classify(self, inst: Instance):
        hits = [label for label, m in self.MARKERS.items()
                if any(x in inst.stem_md for x in ((m,) if isinstance(m, str) else m))]
        return hits[0] if len(hits) == 1 else None


class VulnClass(ClassificationFamily):
    """b = 0.0 (junior/middle boundary): each handler has exactly one textbook vulnerability;
    naming it requires recognising where user input reaches a dangerous sink. Concept item: two
    handler templates per class (12 questions); names and preambles are decoration."""

    meta = FamilyMeta(id="be.sec.vuln_class.v1", version=1, specs=("backend",), topic="backend.security",
                      skills=("security",), format="find_bug", a=1.2, b=0.0, c=1 / 6, time_limit_s=90)
    LABELS = ("SQL-инъекция", "XSS", "Path traversal", "Command injection", "SSRF", "IDOR")
    SEMANTIC = ("tpl",)
    TEMPLATES = {
        "SQL-инъекция": ["def {fn}(request):\n    {v} = request.GET['{param}']\n    rows = db.execute(\n"
                         "        f\"SELECT * FROM {table} WHERE {col} = '{{{v}}}'\"\n    ).fetchall()\n"
                         "    return JsonResponse({{'items': rows}})",
                         "def {fn}(request):\n    {v} = request.POST['{param}']\n    with connection.cursor() as cur:\n"
                         "        cur.execute(\"DELETE FROM {table} WHERE {col} = '\" + {v} + \"'\")\n"
                         "    return JsonResponse({{'ok': True}})"],
        "XSS": ["def {fn}(request):\n    {v} = request.GET['{param}']\n"
                "    return HttpResponse(f\"<h1>Результаты для {{{v}}}</h1>\")",
                "def {fn}(request):\n    {v} = request.GET['{param}']\n"
                "    return render(request, 'page.html', {{'banner': mark_safe({v})}})"],
        "Path traversal": ["def {fn}(request):\n    {v} = request.GET['{param}']\n"
                           "    path = os.path.join('/srv/{table}', {v})\n"
                           "    with open(path, 'rb') as fh:\n        return HttpResponse(fh.read())",
                           "def {fn}(request):\n    {v} = request.GET['{param}']\n"
                           "    return FileResponse(open(f'/var/data/{table}/{{{v}}}', 'rb'))"],
        "Command injection": ["def {fn}(request):\n    {v} = request.GET['{param}']\n"
                              "    out = subprocess.run(f\"convert {{{v}}} out.png\", shell=True, capture_output=True)\n"
                              "    return HttpResponse(out.stdout)",
                              "def {fn}(request):\n    {v} = request.GET['{param}']\n"
                              "    code = os.system('ping -c 1 ' + {v})\n"
                              "    return JsonResponse({{'exit': code}})"],
        "SSRF": ["def {fn}(request):\n    {v} = request.GET['{param}']\n    resp = requests.get({v}, timeout=5)\n"
                 "    return HttpResponse(resp.content)",
                 "def {fn}(request):\n    {v} = request.POST['{param}']\n"
                 "    with urllib.request.urlopen({v}) as remote:\n        return HttpResponse(remote.read())"],
        "IDOR": ["@login_required\ndef {fn}(request, {col}_id):\n    obj = get_object_or_404({model}, pk={col}_id)\n"
                 "    return JsonResponse(model_to_dict(obj))",
                 "@login_required\ndef {fn}(request):\n    obj = get_object_or_404({model}, pk=request.GET['{param}'])\n"
                 "    obj.delete()\n    return JsonResponse({{'deleted': True}})"],
    }
    DETECTORS = {  # oracle: the dangerous sink the user value reaches, recognised on the code
        "SQL-инъекция": r"execute\(\s*f\"SELECT|execute\(\"DELETE FROM \w+ WHERE \w+ = '\" \+",
        "XSS": r"HttpResponse\(f\"<|mark_safe\(\w+\)",
        "Path traversal": r"os\.path\.join\(.*\)\n\s+with open|FileResponse\(open\(f'/var/data/",
        "Command injection": r"shell=True|os\.system\('ping",
        "SSRF": r"requests\.get\(\w+,|urlopen\(\w+\)",
        "IDOR": r"get_object_or_404\(\w+, pk=(\w+_id|request\.GET\[)",
    }

    PREAMBLES = ("    # {ticket}", "    logger.info('request from %s', request.user)", "    metrics.incr('{fn}')",
                 "    started = time.monotonic()", "    # TODO: cache the response", "    audit(request, '{fn}')",
                 "    check_feature_flag('{fn}')", "    request.session['last_view'] = '{fn}'")

    def draw(self, rng, label):
        return {"fn": rng.choice(("search", "show", "download", "preview", "export", "fetch", "render", "detail",
                                  "lookup", "report", "open_doc", "thumbnail", "proxy", "view_item", "find", "load")),
                "v": rng.choice(("q", "name", "value", "term", "target", "src", "path_", "arg", "raw", "key",
                                 "query", "item")),
                "param": rng.choice(("q", "name", "file", "url", "term", "id", "src", "ref", "doc", "page",
                                     "image", "target")),
                "table": rng.choice(RESOURCES), "col": rng.choice(("owner", "title", "code", "invoice", "order")),
                "model": rng.choice(("Invoice", "Order", "Report", "Ticket", "Payment", "Contract")),
                "pre": rng.randrange(len(self.PREAMBLES)), "tpl": rng.randrange(len(self.TEMPLATES[label])),
                "ticket": f"{rng.choice(('SEC', 'BUG', 'API', 'WEB'))}-{rng.randint(100, 9999)}"}

    def render(self, p):
        code = self.TEMPLATES[p["label"]][p["tpl"]].format(**p)
        pre = self.PREAMBLES[p["pre"]].format(**p)
        head, _, rest = code.partition("\n    ")
        lines = [head, f"    # {p['ticket']}: {p['fn']}"] + ([pre] if pre.strip() and "{ticket}" not in
                                                             self.PREAMBLES[p["pre"]] else [])
        code = "\n".join(lines) + f"\n    {rest}"
        return ("В обработчике Django ниже ровно одна уязвимость. Какая?",
                {"lang": "python", "text": code})

    def classify(self, inst: Instance):
        hits = [label for label, pat in self.DETECTORS.items() if re.search(pat, inst.code["text"])]
        return hits[0] if len(hits) == 1 else None


FAMILIES = [StatusCode(), Method(), VulnClass()]
