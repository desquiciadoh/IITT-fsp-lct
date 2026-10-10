# Seed Data Schema (`seed_data/full/`)

This directory contains synthetic dataset files in JSON Lines (`.jsonl`) format used by `python manage.py seed --mode=full`.

## Files and Schemas

### 1. `companies.jsonl`
One JSON object per line:
```json
{
  "id": "c1000000-0000-0000-0000-000000000001",
  "name": "Ozon FinTech",
  "inn": "7704217370",
  "website": "https://ozon.ru",
  "email_domain": "ozon-mock.ru",
  "business_domain": "E-commerce & FinTech",
  "description": "High-load banking and e-commerce services.",
  "contact_email": "hr@ozon-mock.ru",
  "trust_level": "verified",
  "members": [
    {
      "email": "lead@ozon-mock.ru"
    }
  ]
}
```

### 2. `positions.jsonl`
One JSON object per line:
```json
{
  "id": "p1000000-0000-0000-0000-000000000001",
  "company_id": "c1000000-0000-0000-0000-000000000001",
  "title": "Senior Go / Python Backend Developer",
  "specialization": "backend",
  "grades": ["senior", "middle"],
  "must_skills": ["Python", "PostgreSQL", "Docker"],
  "nice_skills": ["Go", "Kubernetes"],
  "work_formats": ["remote", "hybrid"],
  "location": "Москва",
  "salary_min": 250000,
  "salary_max": 380000,
  "salary_type": "gross",
  "team_context": "Payment processing core team",
  "description": "Developing payment platform with 99.99% uptime.",
  "is_public": true,
  "status": "open"
}
```

### 3. `candidates.jsonl`
One JSON object per line:
```json
{
  "id": "a1000000-0000-0000-0000-000000000001",
  "email": "candidate1@example.com",
  "public_id": "C-A1000001",
  "full_name": "Иван Смирнов",
  "city": "Москва",
  "timezone": "Europe/Moscow",
  "specialization": "backend",
  "claimed_grade": "senior",
  "years_experience": 6.5,
  "roles": ["Backend Developer", "Tech Lead"],
  "work_formats": ["remote", "hybrid"],
  "salary_min": 280000,
  "salary_max": 400000,
  "salary_type": "net",
  "salary_floor": 250000,
  "open_to_offers": true,
  "blind_mode": false,
  "blocked_company_ids": [],
  "about": "Backend architect with deep experience in Python, async, and distributed databases.",
  "completeness": 95,
  "contacts": {
    "email": "candidate1@example.com",
    "phone": "+7 (999) 000-00-01",
    "telegram": "@candidate1"
  },
  "consents": [
    {"type": "processing", "granted": true, "version": "1.0"},
    {"type": "publication", "granted": true, "version": "1.0"},
    {"type": "fsp_sync", "granted": true, "version": "1.0"}
  ],
  "skills": [
    {"skill_id": "python", "source": "test", "level": 0.9},
    {"skill_id": "postgresql", "source": "test", "level": 0.85},
    {"skill_id": "docker", "source": "declared", "level": 0.7}
  ],
  "league": {
    "specialization": "backend",
    "grade": "senior",
    "status": "confirmed",
    "rating": 1380,
    "strength": 88.0,
    "base_strength": 80.0,
    "fsp_boost": 8.0,
    "confirmed": true
  },
  "fsp": {
    "participant_id": "FSP-1001",
    "sports_rank": "КМС",
    "results": [
      {
        "event_id": "champ-2025",
        "event_name": "Чемпионат России по спортивному программированию 2025",
        "discipline": "Программирование алгоритмическое",
        "date": "2025-05-15",
        "placement": 2,
        "tier": "national",
        "participants_total": 240
      }
    ]
  }
}
```
