---
docType: standard
project_name: ulog-python
version: 1.0
date: 2026-05-10
author: jojo8356
status: stable
applies_to: ["ulog-python", "Cycloth (FastAPI equivalent rules)"]
inspired_by: ["HackSoft Django Styleguide", "Two Scoops of Django", "PEP 20"]
---

# Django clean-code standard — ULog & friends

> One-stop reference for clean Django code conventions to apply on ulog
> and any future Django app in this org. Distilled from HackSoft's
> styleguide + Two Scoops + the four-clean-code-principles trail. Each
> rule has the **why**, the **how**, the **anti-pattern**, and the
> **scope** (always-apply vs. apply-when-codebase-grows).

---

## 0. The 30-second pitch

Django gives you a lot of rope. By default everyone puts everything
everywhere — logic in views, queries in models, magic in
`signals.py`, validation in serializers. After 6 months it's
unmaintainable.

This standard locks in **7 architectural rules + 5 hygiene rules** that
keep a Django codebase grokable at 5K, 50K, and 500K LOC. The rules are
opinionated by design: pick once, never relitigate.

---

## 1. Vision

### 1.1 Why this exists

Django is the most popular Python web framework precisely because it's
batteries-included and forgiving. That same forgiveness is the enemy of
mid-stage scaling: a startup that ships fast in months 0-12 finds
itself in a `models.py` file with 2K lines and `views.py` with 800
lines of business logic by month 18. Refactoring at that point is a
multi-quarter project.

This document codifies the patterns that **prevent** that fate. Apply
from day 1 on new code; refactor toward them gradually on legacy.

### 1.2 What this standard is NOT

- A Django tutorial. Reader is expected to know views/models/admin/ORM.
- A REST API standard. (For that, see HackSoft DRF guide separately.)
- A CSS / templating guide.
- A deployment / DevOps doc.
- A dogma. The "scope" tag on each rule indicates when to enforce.

### 1.3 Target users

- **Solo dev shipping a v1** (Johan, ulog) — apply all `always` rules,
  defer `at-scale` rules until the codebase passes ~10K LOC or 3
  contributors.
- **Small team scaling to mid-stage** (Cycloth in 6 months) — apply
  every rule from day 1.
- **Reviewers in PR cycles** — point at specific rules by anchor
  (e.g., `[Rule 3.1 — services]`) instead of repeating yourself.

### 1.4 Success criteria

| SC | Description |
|---|---|
| SC1 | A new contributor can add a feature without reading more than 1 file beyond the one they edit. |
| SC2 | `views.py` for any app stays under 200 LOC; `models.py` stays under 300 LOC. |
| SC3 | Every business mutation is traceable to a single function in `services.py`. |
| SC4 | Test files mirror source layout 1:1 (`tests/test_services.py` for `services.py`, etc.). |

---

## 2. Scope (what this standard governs)

### 2.1 In scope

- File / module layout per Django app.
- Boundaries between views, services, selectors, models, tasks.
- Settings module organization across environments.
- Test layout and factory conventions.
- Naming conventions for the above.

### 2.2 Out of scope

- Specific 3rd-party packages (DRF, Celery, channels) — apply rules to
  whatever you use.
- CI / deploy pipelines.
- Frontend (Tailwind / templates remain free-form).
- DB schema design (covered by separate Storage standard if/when needed).

---

## 3. Architectural rules (FR-style)

### FR-CC-1 — Views are orchestrators, NOT business logic

| Field | Value |
|---|---|
| **Scope** | Always |
| **Source** | HackSoft "Services" pattern; Django docs Class-Based Views |
| **Anti-pattern** | A view that imports `EmailMessage`, computes totals, validates 5 fields, writes 2 models. |

**The rule.** A view does exactly four things, in order:

1. **Parse** the request (extract input from form / JSON / query params).
2. **Authorize** (permission check; can be a decorator).
3. **Delegate** to a service (write) or selector (read).
4. **Render** the response (template / JSON).

Any business logic — calculations, branching on domain state, multi-model
writes, side effects (email, push, webhook) — lives in `services.py`.

**How to apply:**

```python
# WRONG — view doing everything
def checkout_view(request):
    cart = Cart.objects.get(user=request.user)
    total = sum(line.unit_price * line.qty for line in cart.lines.all())
    if total > 1000:
        total *= 0.9  # 10% bulk discount
    Order.objects.create(user=request.user, total=total)
    send_mail("Thanks!", ..., [request.user.email])
    return JsonResponse({"ok": True})

# RIGHT — view orchestrates, service does the work
def checkout_view(request):
    order = checkout_services.place_order(user=request.user)
    return JsonResponse({"id": order.id, "total": order.total})
```

**Acceptance test for code review:**
- [ ] No `import` of email / SMS / webhook / external SDK at the top of `views.py`.
- [ ] No `.objects.create(...)` / `.save()` / `.delete()` calls in a view.
- [ ] Each view body is ≤ 15 lines.

---

### FR-CC-2 — Models are persisted dataclasses, NOT logic containers

| Field | Value |
|---|---|
| **Scope** | Always |
| **Source** | HackSoft "Models" + "Avoid magic" |
| **Anti-pattern** | A model with `def calculate_balance(self)`, `def send_welcome_email(self)`, `@property def is_premium(self)` reaching across 3 tables. |

**The rule.** Models hold:

1. **Fields** (the schema).
2. **DB constraints** (uniqueness, NOT NULL, check constraints, indexes).
3. **`__str__`** for admin / debug.
4. Optional: a `clean()` for cross-field validation that doesn't fit a DB constraint.

That's it. **No `def calculate_*`, no `def send_*`, no `def trigger_*`,
no domain logic that crosses tables.**

**Why this matters.** The model is the persistence boundary. Putting
domain logic on it means you can't write that logic without spinning
up a DB. Tests get slower, mocking gets harder, and the same logic
gets duplicated in API serializers / admin actions / management
commands because the model is too tightly coupled.

**How to apply:**

```python
# WRONG — model carrying domain knowledge
class User(models.Model):
    email = models.EmailField()
    plan = models.CharField(max_length=20)

    @property
    def is_premium(self):
        return self.plan in ("pro", "enterprise")  # encodes business rule

    def upgrade_to_pro(self):
        self.plan = "pro"
        self.save()
        send_mail(...)  # SIDE EFFECT in a model!

# RIGHT — model = data + constraints; logic in services
class User(models.Model):
    email = models.EmailField(unique=True)
    plan = models.CharField(max_length=20, choices=Plan.choices)

    class Meta:
        constraints = [
            CheckConstraint(check=Q(plan__in=["free", "pro", "enterprise"]),
                            name="plan_must_be_known"),
        ]

# users/services.py
PREMIUM_PLANS = frozenset({"pro", "enterprise"})

def is_premium(user: User) -> bool:
    return user.plan in PREMIUM_PLANS

def upgrade_to_pro(*, user: User) -> User:
    user.plan = "pro"
    user.save(update_fields=["plan"])
    notification_services.send_upgrade_confirmation(user=user)
    return user
```

**Exception:** `__str__`, `get_absolute_url()`, and `Meta.ordering` are
still OK on models — they're presentation helpers, not domain logic.

---

### FR-CC-3 — `services.py` for writes, `selectors.py` for reads

| Field | Value |
|---|---|
| **Scope** | Always |
| **Source** | HackSoft (the headline pattern) |
| **Anti-pattern** | A "manager" or "controller" file mixing reads and writes; or read queries scattered across views. |

**The rule.** Every Django app has two business-logic modules:

- **`services.py`** — every function that **mutates** state (creates,
  updates, deletes, side-effects external systems).
- **`selectors.py`** — every function that **reads** state and returns
  models / dicts / QuerySets.

**Why split.** Writes have side effects, complex transactional
boundaries, and external dependencies (email, queues). Reads are pure,
cacheable, parallelizable. Mixing them obscures both. With the split:

- `selectors.py` is trivially testable (no DB writes needed for
  read-tests with seeded data).
- `services.py` reviews focus on transaction safety + side-effect order.
- A new dev grep'ing for "where do orders get created?" finds it in 1
  spot: `orders/services.py`.

**Function signature conventions:**

```python
# services.py — mutations
def create_order(*, user: User, line_items: list[LineItemInput]) -> Order:
    """Mutations use kwargs (explicit), return the created entity."""
    ...

def cancel_order(*, order: Order, reason: str) -> Order:
    """Updates take the entity + the diff, return the updated entity."""
    ...

# selectors.py — queries
def get_active_orders_for_user(*, user: User) -> QuerySet[Order]:
    """Returns a QuerySet (lazy) for view-level pagination."""
    return Order.objects.filter(user=user, status="active")

def get_order_detail(*, order_id: int) -> Order | None:
    """Returns one entity or None — never raises Http404 (caller decides)."""
    return Order.objects.filter(id=order_id).first()
```

**Acceptance test for code review:**
- [ ] No mutations (`.save()`, `.create()`, `.delete()`, `.update()`) in `selectors.py`.
- [ ] No read-only queries returned from `services.py` (it should always return the mutated entity).
- [ ] Function args use `*` (keyword-only) — prevents positional-arg bugs in growing signatures.

---

### FR-CC-4 — Settings split per environment

| Field | Value |
|---|---|
| **Scope** | At-scale (>1 environment) |
| **Source** | Two Scoops Ch.5 + HackSoft |
| **Anti-pattern** | One `settings.py` with `if DEBUG: ... elif PROD: ...` blocks. |

**The rule.** Split `settings.py` into a package:

```
config/
├── __init__.py
├── settings/
│   ├── __init__.py
│   ├── base.py        # shared defaults
│   ├── dev.py         # local dev (DEBUG=True, console email, etc.)
│   ├── test.py        # CI / pytest (in-memory DB, eager Celery)
│   └── prod.py        # production (DEBUG=False, real services)
```

Pick the env via `DJANGO_SETTINGS_MODULE=config.settings.dev`.

**Variable conventions:**

- Env vars for prod overrides: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`.
- Use `django-environ` or stdlib `os.environ` — not `python-dotenv` in
  prod (load via systemd / Docker env instead).
- Booleans: prefix with `USE_` (e.g., `USE_S3_STORAGE`, `USE_OTEL`).
- Integration-specific blocks gated by `if USE_X: ...` so the prod
  config can run without the integration's deps installed.

**For ulog specifically:** ulog is a 1-environment app (the user runs
the viewer locally). Skip this rule. `settings.py` mono-file is fine.

---

### FR-CC-5 — One `urls.py` per app (no fat root urls)

| Field | Value |
|---|---|
| **Scope** | Always |
| **Source** | Django docs + Two Scoops |
| **Anti-pattern** | A root `urls.py` with 80 entries enumerating every endpoint. |

**The rule.** The root `urls.py` should ONLY:

1. Include each app's URL module.
2. Add framework-level routes (admin, static media in dev).

Each app owns its own `urls.py` under its directory.

```python
# config/urls.py — root
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/users/", include("users.urls")),
    path("api/orders/", include("orders.urls")),
    path("", include("dashboard.urls")),
]

# orders/urls.py — app-level
urlpatterns = [
    path("", views.list_view, name="orders-list"),
    path("<int:order_id>/", views.detail_view, name="orders-detail"),
    path("<int:order_id>/cancel/", views.cancel_view, name="orders-cancel"),
]
```

**For ulog specifically:** ulog has 1 app (`viewer`) with ~7 routes —
the current single `urls.py` is fine. Apply this rule when adding a
2nd app.

---

### FR-CC-6 — Tests mirror source layout, use factories

| Field | Value |
|---|---|
| **Scope** | Always |
| **Source** | HackSoft + factory-boy docs |
| **Anti-pattern** | All tests in one `tests.py` file; using fixture JSON files for test data. |

**The rule.** For each module `app/x.py`, tests live in
`app/tests/test_x.py`. Tests use **factories** (`factory_boy`) to
generate model instances — never JSON fixtures, never raw `.create()`
inside test bodies.

```
orders/
├── services.py
├── selectors.py
├── models.py
└── tests/
    ├── __init__.py
    ├── factories.py           # OrderFactory, LineItemFactory, ...
    ├── test_services.py
    └── test_selectors.py
```

**Why factories.** They scale. JSON fixtures rot the moment you add a
field. Factories let you write `OrderFactory(status="cancelled")` and
get a complete, valid object back. Composable, readable.

```python
# factories.py
import factory

class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    plan = "free"

class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order
    user = factory.SubFactory(UserFactory)
    status = "active"

# test_services.py
def test_cancel_order_marks_status():
    order = OrderFactory()
    cancel_order(order=order, reason="test")
    order.refresh_from_db()
    assert order.status == "cancelled"
```

**For ulog specifically:** ulog tests are ALREADY mirror-layout
(`tests/test_handlers.py`, `tests/test_setup.py`, etc.) — you're
applying this rule by accident. Factories aren't needed because ulog
tests don't write to its models (it's a logging library, not a CRUD
app). Keep it simple; don't add `factory_boy` for the sake of it.

---

### FR-CC-7 — Use kwargs-only for service / selector signatures

| Field | Value |
|---|---|
| **Scope** | Always |
| **Source** | HackSoft (the most-cited rule) |
| **Anti-pattern** | `def create_user(email, password, name, plan="free", referral=None, ...)` — adding 1 arg breaks every caller. |

**The rule.** Every function in `services.py` / `selectors.py` uses
the Python `*` keyword-only marker:

```python
def create_user(*, email: str, password: str, plan: str = "free") -> User:
    ...
```

**Why.** Three reasons:

1. **Refactor-safe.** Adding a new arg can never break an existing
   call site (because the new arg can default to `None`, and old call
   sites continue to pass kwargs only — never positional).
2. **Self-documenting at call sites.** `create_user(email=..., password=..., plan="pro")`
   is more readable than `create_user("johan@x", "...", "pro")`.
3. **Catches typos at runtime.** `create_user(emial="...")` raises
   `TypeError`. Without `*`, a positional version of the wrong-kwarg
   call could slide through to the wrong arg slot.

---

## 4. Hygiene rules

### FR-HY-1 — Type hints everywhere, mypy-strict in CI

| Field | Value |
|---|---|
| **Scope** | Always |
| **Source** | PEP 484, Two Scoops Ch.6 |

Every function signature has type hints. `mypy --strict` must pass in
CI. Returning a `QuerySet` ? Type it `QuerySet[Order]`. Returning a
dict ? Type it `dict[str, Any]` (or define a TypedDict if it has
known structure).

For ulog: already enforced by the `mypy --strict` release gate
(architecture.md line 165).

### FR-HY-2 — `from __future__ import annotations` at the top of every Python file

Lazy-evaluated annotations means circular-import-friendly types and
`Order | None` syntax on Python 3.10+. One-liner, zero cost.

### FR-HY-3 — Imports sorted: stdlib / third-party / local, with blank lines between

Use `isort` (or ruff's I-rules) in pre-commit. Settings must match
PEP 8 + Black-compatibility profile.

### FR-HY-4 — Black + ruff in pre-commit (no exceptions)

`pre-commit install` after clone is mandatory. Reviewers should never
need to comment "please reformat".

For ulog: TODO — set up `.pre-commit-config.yaml`.

### FR-HY-5 — One verb per function name

Functions named `process_order` are red flags. What does "process"
mean? Use `validate_order`, `submit_order`, `confirm_order`,
`cancel_order` — each verb is a contract.

---

## 5. i18n — Django built-in is the standard

### FR-I18N-1 — Use Django's gettext infrastructure for any user-facing text

| Field | Value |
|---|---|
| **Scope** | When the app has > 1 language requirement |
| **Source** | Django docs `topics/i18n/` |

**The rule.** ANY user-facing string (template text, error message,
admin label) gets wrapped:

```python
from django.utils.translation import gettext_lazy as _

class Order(models.Model):
    status = models.CharField(_("Status"), max_length=20)

# views.py
from django.utils.translation import gettext as _

def view(request):
    return render(request, "x.html", {"title": _("Welcome back")})

# templates
{% load i18n %}
<h1>{% trans "Records" %}</h1>
```

Then : `django-admin makemessages -l fr` → edit
`locale/fr/LC_MESSAGES/django.po` → `django-admin compilemessages`.

**Don't roll your own** custom JSON / database-backed translation
system unless you have specific needs (live editor, CMS-managed
content). For static UI strings, gettext is battle-tested.

**For ulog specifically:** the viewer is anglais-only by Python
community convention. The `/_qa/` page uses a custom JSON for FR/EN
toggle because it's a dev-tool with a switch-without-reload UX
requirement — the only valid exception in the codebase. **Do not
extend this pattern to other pages.**

### FR-I18N-2 — `django-rosetta` for non-dev translators

When non-developers (PM, marketing) need to edit translations, install
`django-rosetta` for an admin UI to edit `.po` files in the browser.
No source-code rebuild needed.

---

## 6. Anti-patterns to NEVER ship

| # | Anti-pattern | Why it's bad |
|---|---|---|
| 1 | Logic in `signals.py` | Signals are invisible from a grep. Use service-level explicit calls instead. |
| 2 | `Manager` classes adding business methods (`Order.objects.cancel_all_pending()`) | Same as logic-in-models — couples persistence and behavior. Use `services.cancel_pending_orders()` instead. |
| 3 | Multiple inheritance on Class-Based Views (`UpdateView, FormMixin, LoginRequiredMixin, ...`) | MRO chaos. Prefer function views or single-inheritance CBVs. |
| 4 | `request.POST["foo"]` access in views | KeyError-prone. Use a Form or DRF Serializer for input validation. |
| 5 | `try: ... except: pass` (bare except) | Hides bugs. Always catch the specific exception you mean to handle. |
| 6 | `print()` for debugging in committed code | Use `logger.debug(...)` instead. (Yes, even in tests — `caplog` exists.) |
| 7 | `models.JSONField` for "we'll figure out the schema later" | Tech debt that compounds. Define the shape in a TypedDict / dataclass and serialize at the boundary. |
| 8 | Migrations that mix schema + data changes | Split into 2 migrations: one schema, one data. Easier to roll back. |
| 9 | Reading from / writing to `os.environ` outside `settings.py` | Hides config. All env vars should be parsed once in settings, then accessed via `django.conf.settings`. |
| 10 | `@cached_property` on a model | Caches across requests if the model instance is shared. Use `functools.lru_cache` on a function in `selectors.py` instead. |

---

## 7. Application checklists

### 7.1 ULog (this project)

- [x] **FR-CC-1** Views are orchestrators — `viewer/views.py` only does parse → query adapter → render.
- [x] **FR-CC-2** Models = data only — N/A (ulog doesn't use Django models; uses SQLAlchemy Core for persistence).
- [x] **FR-CC-3** Reads vs writes split — N/A (read-only viewer; the SQL handler in `ulog/handlers/sql.py` is a write boundary, separate from the read adapters).
- [ ] **FR-CC-4** Settings split — skip (1-environment app).
- [x] **FR-CC-5** App-level urls.py — current `ulog/web/urls.py` covers all routes; no second app exists.
- [x] **FR-CC-6** Tests mirror — already done.
- [x] **FR-CC-7** Kwargs-only — applies to `services.py` if/when added.
- [x] **FR-HY-1/2** Type hints + future annotations — already enforced.
- [x] **FR-I18N-1** Gettext for new pages — `/_qa/` is the documented exception.
- [ ] **FR-HY-4** Pre-commit hooks — TODO.

### 7.2 Cycloth (FastAPI equivalent — separate project)

The Django-specific names map as follows for a FastAPI app:

| Django | FastAPI equivalent |
|---|---|
| `views.py` | `routers/<area>.py` |
| `services.py` | `services/<area>.py` (same name) |
| `selectors.py` | `repositories/<area>.py` |
| `models.py` | `models/<area>.py` (SQLModel) |
| `urls.py` | `app.include_router(...)` in `main.py` |
| Form / Serializer | Pydantic models in `schemas/<area>.py` |

All 7 architectural rules + 5 hygiene rules apply identically. Only
the names change.

---

## 8. Definition of Done — for this standard

✅ Standard checked into `docs/standards/`
✅ Linked from `docs/index.md`
✅ Each rule has anti-pattern + acceptance test
✅ Application checklist for ulog filled
✅ Application checklist for Cycloth (mapping table) included

---

## 9. Sources

- [HackSoft Django Styleguide](https://github.com/HackSoftware/Django-Styleguide) — the headline reference; this doc is a distillation
- [Two Scoops of Django](https://www.feldroy.com/books/two-scoops-of-django-3-x) — book by Daniel & Audrey Roy Greenfeld
- [Django i18n docs](https://docs.djangoproject.com/en/6.0/topics/i18n/)
- [Django Translation guide](https://docs.djangoproject.com/en/6.0/topics/i18n/translation/)
- [Coding Style — Django Best Practices](https://django-best-practices.readthedocs.io/en/latest/code.html)
- [Clean Django Architecture without overengineering — Anas Issath](https://medium.com/@anas-issath/clean-django-architecture-without-overengineering-what-hacksoft-got-right-6af521e7918c)
- [4 Clean Code Principles in Django — Rico Tadjudin](https://betterprogramming.pub/clean-code-principles-in-django-b0563a4e12f5)
- [PEP 20 — The Zen of Python](https://peps.python.org/pep-0020/)
- [PEP 484 — Type Hints](https://peps.python.org/pep-0484/)

---

## 10. Change log

- **2026-05-10 v1.0** — Initial standard. 7 architectural + 5 hygiene + 2 i18n rules + 10 anti-patterns. Application checklists for ulog (now) + Cycloth (future) included.
