---
name: django-drf
description: Patterns for writing Django/DRF code in FSP Draft - services layer, transactions and locking, optimistic versioning, RFC 7807 errors, permissions, serializers with explicit fields, query efficiency, migrations, Celery tasks, contact gating. Use when adding or changing models, serializers, views, services, URLs, migrations or Celery tasks under apps/.
---

# Django/DRF in this repo

Read the neighbouring code first and match it. The rules below are what reviewers (`django-reviewer`) will check.

## Where code goes

- **Models** (`models.py`): fields, constraints, `__str__`. DB-level invariants as `CheckConstraint`/`UniqueConstraint` (salary: `salary_min > 0`, `salary_max >= salary_min`).
- **Services** (`services.py`): business rules and multi-step writes. Views and serializers call services; they don't contain rules. Existing: `core/services.py` (`ContactAccessService`), `outreach/services.py` (`OfferService.transition`, `create_offer`).
- **Serializers:** shape and field validation only. Explicit `fields = [...]`, `read_only_fields` for server-set values (`id`, `status`, `version`, timestamps, `public_id`). No `__all__`, no `exclude`.
- **Views:** auth, permissions, call a service, serialize. Explicit `permission_classes` (`core/permissions.py`, e.g. `IsCandidate`). `@extend_schema` for drf-spectacular so `docs/openapi.json` stays right.
- **Pure engines** (ML/AI) take DTOs and return DTOs; views/services load ORM data into DTOs in a batch.
- Imports are top-level module names (`from outreach.models import Offer`) because `apps/` is on `sys.path`.

## Writes and concurrency

```python
from django.db import transaction

@transaction.atomic
def accept_offer(offer_id: int, user, expected_version: int) -> Offer:
    offer = Offer.objects.select_for_update().get(pk=offer_id)
    if offer.version != expected_version:
        raise VersionConflict()                   # → 409 problem+json
    ...                                           # validate the transition
    offer.status, offer.version = OfferStatus.ACCEPTED, offer.version + 1
    offer.save(update_fields=["status", "version", "updated_at"])
    ContactAccessService.create_grant(...)        # same transaction
    transaction.on_commit(lambda: notify.delay(offer.id))   # side effects after commit
    return offer
```

- Multi-step writes go in `transaction.atomic()`; read-modify-write uses `select_for_update()` or a version check.
- Side effects (Celery, SSE, email) go in `transaction.on_commit`.
- `save(update_fields=[...])` on rows written concurrently.

## Errors

Raise the typed exceptions from `core/errors.py` (`SalaryInvalid`, `CooldownActive`, `VersionConflict`, `ContactNotGranted`, `ItemNotCurrent`, `InvalidTransition`, ...). The handler `fsp_exception_handler` renders RFC 7807 problem+json. Add a new subclass for a new error code instead of returning ad-hoc `Response({"error": ...})`. Never put keys, contacts or stack traces in `detail`.

## Security and invariants

- Contacts: only `ContactAccessService.get_contacts(...)`. Never `candidate.candidate_contacts` in employer-facing serializers, search or exports.
- Assessment items: serializers never include `key`/`fingerprint`; serve one item at a time; check `ItemNotCurrent`.
- Time: cooldowns and deadlines use `get_current_time_for_user(user)` (demo time travel).
- Expose public ids (`C-XXXXXX`), not PKs, in talent search.
- Role checks come from `request.user.role` on the server, never from request data. Object ownership is checked per object.

## Queries

- `select_related` for FKs and `prefetch_related` for reverse/M2M wherever a serializer touches relations. Verify with `django_assert_max_num_queries` in a test.
- Paginate list endpoints (`core/pagination.py`). Use `.exists()`, `.count()`, `values_list(..., flat=True)` instead of loading objects.
- Index fields used in filters and ordering (`Meta.indexes`).

## Migrations

- Every model change ships with its migration: `makemigrations <app>`, read the generated file, then `makemigrations --check --dry-run` is clean.
- Never edit an applied migration; add a new one. `RunPython` needs `reverse_code` (use `migrations.RunPython.noop` if nothing to undo).
- Column removal and renames happen in two steps (nullable/add first, drop later). pgvector: `VectorExtension()` in a migration before any `VectorField`.

## Celery

Tasks take ids, not ORM objects; they are idempotent (safe to retry); use `bind=True`, `autoretry_for`/`self.retry` with backoff for transient errors, and a timeout on every external call. Mark the domain object's status on final failure instead of swallowing it.

## More

ECC references, generic and long; read only the section you need:
- `references/ecc-django-patterns.md`
- `references/ecc-api-design.md`
- `references/ecc-postgres-patterns.md`
- `references/ecc-database-migrations.md`
- `references/ecc-django-celery.md`
