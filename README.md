# FSP Draft — Платформа обратного IT-рекрутинга

> **Трек Федерации спортивного программирования (ФСП) на «Лидерах цифровой трансформации 2026»**  
> Серверная часть (Backend MVP P0) на **Python 3.12+ / Django 5.x / Django REST Framework / PostgreSQL 17 + pgvector**.

---

## 1. Концепция и ключевые правила

«FSP Draft» реализует модель **обратного найма**: работодатели исследуют ранжированные **Лиги** специалистов и направляют адресные **Драфт-офферы с обязательной зарплатной вилкой**. Контакты соискателей скрыты и раскрываются **только после явного согласия кандидата**.

### 6 строгих бизнес-инвариантов

1. **Зарплатная прозрачность (Salary Transparency):**
   * В вакансиях (`positions`) и офферах (`offers`) поля `salary_min` и `salary_max` обязательны.
   * `salary_min > 0` и `salary_max >= salary_min` гарантируются на уровне базы данных (`CheckConstraint`) и валидаторов DRF.
   * Обязательно указание типа налога (`salary_type`: `gross` или `net`).

2. **Гейтинг контактов (Zero Contact Leaks):**
   * Персональные контакты (email, телефон, telegram) хранятся в изолированной таблице `candidate_contacts`.
   * Доступ для работодателя возможен **исключительно** через объект `ContactGrant`, который создается автоматически только при переходе оффера в статус `accepted`.
   * Любые попытки несанкционированного чтения блокируются с кодом `403 ContactNotGranted` и фиксируются в таблице аудита `audit_log`.

3. **Грейды определяются только тестированием (CAT):**
   * Грейд кандидата (`Junior`, `Middle`, `Senior`) присваивается исключительно вступительным адаптивным тестированием.
   * Спортивные достижения ФСП (разряды, победы в турнирах) увеличивают рейтинг силы (`strength` и перцентиль внутри Лиги), но **никогда не повышают грейд напрямую**.

4. **Неподтверждённый грейд (Unconfirmed Policy):**
   * Если кандидат не подтвердил заявленный грейд на тесте, профиль **не скрывается** из базы, а получает статус `unconfirmed` и пессимизируется при ранжировании, сохраняя возможность получать офферы.

5. **Детерминированное оценивание без LLM:**
   * LLM **никогда** не выставляет оценку и грейд!
   * Вопросы генерируются параметрическими шаблонами (`ItemFamily`) со случайными seed-значениями, а правильность ответа проверяет детерминированный оракул на Python.
   * Оценка рассчитывается по 3PL-модели Item Response Theory (IRT EAP, шкала $1000 + 200\theta$).
   * Секретный ключ (`key`) хранится строго на сервере и **никогда** не передается клиенту в `ItemViewSerializer`.

6. **Кулдауны и Time-Travel:**
   * Повторная пересдача теста блокируется кулдауном на 30 дней.
   * В режиме `DEMO_MODE=True` доступен эндпоинт `POST /api/demo/time-travel`, позволяющий жюри сдвигать системное время (`clock_offset_days`) для мгновенной проверки пересдач.

---

## 2. Архитектура приложений (`apps/`)

Проект построен как модульный монолит:

| Приложение | Назначение и ключевые компоненты |
|---|---|
| **`apps.identity`** | Кастомный `User` (email как username, роли `candidate`/`employer`/`admin`), сессии в HttpOnly cookies, Argon2, версионированные согласия 152-ФЗ (`Consent`), журнал аудита (`AuditLog`), демо-персоны и time-travel. |
| **`apps.profiles`** | `CandidateProfile` с публичным ID `C-XXXXXX`, изолированная таблица контактов `CandidateContact`, таксономия навыков `Skill`, генерация защищенного PDF «Карточка игрока» (WeasyPrint) с QR-кодом верификации (`/api/verify/<public_id>`), эвристический парсинг PDF-резюме. |
| **`apps.assessment`** | Сессии адаптивного тестирования `AssessmentSession`, тестовые вопросы `AssessmentItem`, parametric item families (`engine.py`), расчет IRT-метрик ($\theta$, SE, rating), членство в Лигах `LeagueMembership`, кулдауны пересдач. |
| **`apps.matching`** | Профили компаний `Company`, вакансии и потребности `Position`, шортлисты `Shortlist`. Прозрачный взвешенный скоринг с карточками причин `ReasonChips` (`verified_by_test`, `verified_by_fsp`, `declared`). Поиск талантов без утечки внутренних PK. |
| **`apps.outreach`** | Жизненный цикл драфт-офферов `Offer` (`sent` $\to$ `viewed` $\to$ `accepted` / `declined` / `withdrawn`), оптимистичные блокировки через версионирование (`version int`, 409 при конфликтах), сервис гейтинга контактов `ContactAccessService` (`services.py`), автоматическая выдача `ContactGrant`, SSE-стриминг событий (`/api/events`). |
| **`apps.fsp_sync`** | Модели связки `FSPLink` и верифицированных турниров `FSPResult`, защита от повторной привязки чужого FSP ID, фоновые задачи Celery для синхронизации с реестром ФСП. |
| **`apps.core`** | Единые перечисления (`enums.py`), обработчик ошибок RFC 7807 problem+json (`errors.py`), пагинация (`pagination.py`), команда загрузки стенда `seed` (сервис `core.services` является deprecated shim для `apps.outreach.services`). |

---

## 3. Быстрый старт

### Требования
* Python 3.12+ (или утилита `uv`)
* PostgreSQL 17 + Docker (или локальный сервер PostgreSQL)

### Шаг 1: Запуск базы данных
```bash
docker run -d --name fsp-postgres -p 5432:5432 \
  -e POSTGRES_DB=fsp_draft \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  postgres:17
```

### Шаг 2: Создание виртуального окружения и установка зависимостей
```bash
# Через uv (рекомендуется):
uv venv .venv --python 3.12
uv pip install -r requirements.txt

# Или через стандартный venv:
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Шаг 3: Применение миграций
```bash
python manage.py migrate
```

### Шаг 4: Загрузка демонстрационного стенда (Seed)
```bash
python manage.py seed --mode=mini
```
*Команда создаст: 6 реалистичных кандидатов (чемпионы ФСП, разработчики со стандартным опытом, неподтвержденный грейд), 2 компании (`Yandex Tech`, `СберТехнологии`), 3 вакансии с обязательными зарплатными вилками, 4 верифицированных профиля турниров ФСП.*

### Шаг 5: Запуск сервера разработки
```bash
python manage.py runserver
```
* API доступно по адресу: `http://localhost:8000/api/`
* Интерактивная документация Swagger UI: `http://localhost:8000/api/docs/`
* OpenAPI 3.0 схема: `http://localhost:8000/api/schema/` (также сохранена в `docs/openapi.json`)

---

## 4. Запуск тестов (TDD Invariants)

Набор тестов (`pytest-django`) валидирует все ключевые требования ТЗ:
```bash
pytest -v
```

### Проверяемые сценарии:
* **`tests/test_contact_gating.py`**:
  * Запрет чтения контактов без оффера (0 утечек).
  * Контакты скрыты в статусах `sent`, `viewed`, `declined`.
  * Контакты открываются **только** после перехода в `accepted`.
  * Все несанкционированные попытки доступа логируются в `AuditLog`.
* **`tests/test_offer_state_machine.py`**:
  * Корректные переходы: `sent` $\to$ `viewed` $\to$ `accepted`.
  * Запрет некорректных переходов (409 Conflict).
  * Оптимистичная блокировка версий (`VersionConflict` 409).
  * Проверка `CheckConstraint` базы данных на зарплаты (`min > 0`, `max >= min`).
* **`tests/test_assessment_security.py`**:
  * Секретный ключ `key` отсутствует в `ItemViewSerializer` и в API сессии.
* **`tests/test_grade_immutability.py`**:
  * Победы в чемпионатах и звания (МС/КМС) повышают `strength`, но не меняют подтвержденный грейд.
  * Неподтвержденный грейд (`unconfirmed`) не становится подтвержденным из-за медалей ФСП.

---

## 5. Демо-режим для Жюри (Jury Mode)

В режиме `DEMO_MODE=True` доступны следующие возможности:

### 1. Мгновенный вход под персонами
`POST /api/demo/persona`
```json
{
  "persona": "candidate_fsp"    // anna.fsp@example.com (Чемпион ФСП, Senior)
  // "candidate_plain"          // alex.dev@example.com (Разработчик без ФСП, Middle)
  // "employer"                 // techlead@yandex-mock.ru (Работодатель Yandex Tech)
}
```

### 2. Time-Travel (сдвиг системного времени)
`POST /api/demo/time-travel`
```json
{
  "days": 30
}
```
*Сдвигает часы текущего пользователя на 30 дней вперед, снимая кулдаун на повторное прохождение тестирования.*

---

## 6. Каталог ошибок (RFC 7807)

Все ошибки API возвращаются в стандартизированном формате `Content-Type: application/problem+json`:
```json
{
  "type": "https://fsp-draft.local/problems/contact_not_granted",
  "title": "Contact access not granted",
  "status": 403,
  "code": "contact_not_granted",
  "detail": "Candidate contacts are not available without an accepted offer.",
  "errors": [
    {
      "field": "offer_id",
      "msg": "Offer must be in accepted status."
    }
  ]
}
```

Ключевые коды ошибок:
* `validation_failed` (422) — ошибки валидации входящих полей структуры данных.
* `salary_invalid` (422) — некорректная вилка зарплаты (`salary_min <= 0` или `salary_max < salary_min`).
* `contact_not_granted` (403) — попытка чтения скрытых контактов без гранта.
* `company_required` (403) — действие доступно только представителю зарегистрированной компании.
* `version_conflict` (409) — конфликт оптимистичной блокировки при параллельном обновлении оффера.
* `invalid_transition` (409) — недопустимый переход статуса в машине состояний оффера.
* `invalid_role` (400) — попытка зарегистрировать пользователя с недопустимой ролью (например, `admin`).
* `forbidden` (403) — доступ запрещен (включая попытку переключения демо-персоны обычным пользователем).
* `not_found` (404) — запрашиваемый ресурс не найден (включая попытку просмотра скрытой карточки кандидата с фиксацией в `AuditLog`).
* `report_unreadable` (500) — файл отчета о тестировании поврежден или не читается.
* `cooldown_active` (429) — активен кулдаун на повторное прохождение тестирования.
* `item_not_current` (409) — ответ на устаревший или уже отправленный вопрос тестирования.
* `fsp_id_already_linked` (409) — FSP ID уже привязан к другой учетной записи платформы.

---

## 7. Чипы обоснования рекомендаций (ReasonChips)

Каждый кандидат в пуле вакансии снабжается массивом объясняющих факторов `ReasonChips` с указанием источника достоверности (`source`):

| Источник (`source`) | Назначение | Достоверность |
|---|---|---|
| `test` | Навык или грейд подтверждены результатами адаптивного вступительного тестирования платформы. | 100% (верифицировано тестом) |
| `fsp` | Спортивный разряд, статус призера или победа в соревнованиях подтверждены официальным реестром ФСП. | 100% (верифицировано Федерацией) |
| `declared` | Навык или опыт заявлены кандидатом самостоятельно в анкете/резюме. | Заявлено кандидатом |

Примеры чипов:
- `✓ Verified Python` (source: `test`)
- `🏆 Чемпион России по спортивному программированию` (source: `fsp`)
- `🎖️ Спортивный разряд: КМС` (source: `fsp`)
- `Match: 350 000 ₽ gross (в рамках вилки)` (source: `declared`)

---

## 8. Демонстрационный сид (Seed Claims)

Команда `python manage.py seed` формирует детерминированный набор данных для демонстрации жюри:

* **Кандидаты:**
  1. `anna.fsp@example.com` (Чемпионка РФ по спортивному программированию, Senior Backend, подтвержденный тест, 100 Strength).
  2. `alex.dev@example.com` (Опытный Middle Python разработчик без соревновательного бэкграунда).
  3. `elena.junior@example.com` (Junior Backend разработчица, подтвердила грейд на тестировании).
  4. `dmitry.unconfirmed@example.com` (Заявил Senior, но не сдал квалификационный тест — переведен в статус `unconfirmed`).
  5. `maksim.fsp@example.com` (КМС по спортивному программированию, Middle).
  6. `olga.fullstack@example.com` (Fullstack разработчик, закрыт для предложений `open_to_offers=False`).
* **Компании и вакансии:**
  * `Yandex Tech`: открытая вакансия «Senior Backend Developer» (350k–450k ₽ gross).
  * `СберТехнологии`: открытая вакансия «Middle Python Developer» (220k–300k ₽ net).
  * `VK`: открытая вакансия «Junior Go Developer» (120k–180k ₽ gross).

---

## 9. Таблица переменных окружения (`.env`)

| Переменная | Назначение | Значение по умолчанию |
|---|---|---|
| `DEBUG` | Режим отладки Django | `False` |
| `DEMO_MODE` | Включение эндпоинтов жюри (`/api/demo/*`, `/idp/*`) | `False` |
| `SECRET_KEY` | Криптографический ключ подписи сессий и токенов | Обязателен в production |
| `ALLOWED_HOSTS` | Разрешенные HTTP-хосты | `localhost,127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | Разрешенные источники для CSRF защиты | `http://localhost:5173,http://localhost:8000` |
| `POSTGRES_DB` | Имя базы данных PostgreSQL | `fsp_draft` |
| `POSTGRES_USER` | Пользователь PostgreSQL | `postgres` |
| `POSTGRES_PASSWORD` | Пароль пользователя PostgreSQL | `postgres` |
| `POSTGRES_HOST` | Хост СУБД PostgreSQL | `localhost` (или `db` в Docker) |
| `POSTGRES_PORT` | Порт СУБД PostgreSQL | `5432` |
| `CELERY_BROKER_URL` | Брокер сообщений Celery | `redis://localhost:6379/0` |
| `CELERY_RESULT_BACKEND` | Хранилище результатов Celery | `redis://localhost:6379/0` |
| `REDIS_URL` | URL Redis для шины доменных событий | `redis://localhost:6379/0` |
| `ITEM_SEED_SECRET` | HMAC-секрет генерации параметров тестовых заданий | Обязателен |
| `LLM_PROVIDER` | Провайдер LLM (`fake`, `gigachat`) | `fake` |
| `GRADE_RETRY_COOLDOWN_DAYS` | Длительность кулдауна пересдачи теста | `30` |

---

## 10. Запуск через Docker Compose

Для развертывания полного стека сервисов одной командой:
```bash
# Сборка и запуск контейнеров (db, redis, api, worker, worker-llm, beat)
make up
# или
docker compose up -d --build
```

Сервисы автоматически:
1. Дождутся готовности PostgreSQL с расширением `pgvector` и Redis.
2. Применят миграции Django.
3. Заполнят демонстрационные данные (`seed`).
4. Поднимут сервер API на `http://localhost:8000`.
5. Запустят фоновые воркеры Celery и планировщик Celery Beat.

