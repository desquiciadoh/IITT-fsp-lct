"""Seed database command for FSP Draft.

Generates:
- 6+ candidates (including FSP prize-winners, standard candidates, confirmed and unconfirmed)
- 2 companies with company members
- 3+ positions with mandatory salary ranges and stack requirements
- 4 FSP achievement profiles with verified results
"""

import json
import uuid
from pathlib import Path

from assessment.models import LeagueMembership
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from fsp_sync.models import FSPLink, FSPResult
from identity.models import Consent, User
from matching.models import Company, CompanyMember, Position
from profiles.management.commands.sync_taxonomy import sync_taxonomy_to_db
from profiles.models import CandidateContact, CandidateProfile, CandidateSkill, Skill

from core.demo_data import SEEDED_CANDIDATES
from core.enums import (
    ConsentType,
    Discipline,
    EvidenceSource,
    Grade,
    LeagueStatus,
    PlacementTier,
    SalaryType,
    Specialization,
    SportsRank,
    SyncStatus,
    TrustLevel,
    UserRole,
    WorkFormat,
)

DISCIPLINE_MAP = {
    "Программирование алгоритмическое": Discipline.ALGORITHMIC,
    "algorithmic": Discipline.ALGORITHMIC,
    "Продуктовое программирование": Discipline.PRODUCT,
    "product": Discipline.PRODUCT,
    "Информационная безопасность": Discipline.INFOSEC,
    "infosec": Discipline.INFOSEC,
    "Робототехника": Discipline.ROBOTICS,
    "robotics": Discipline.ROBOTICS,
    "БАС": Discipline.UAS,
    "uas": Discipline.UAS,
}

SPORTS_RANK_MAP = {
    "КМС": SportsRank.KMS,
    "kms": SportsRank.KMS,
    "МС": SportsRank.MS,
    "ms": SportsRank.MS,
    "1": SportsRank.CAT1,
    "1 разряд": SportsRank.CAT1,
    "cat1": SportsRank.CAT1,
    "2": SportsRank.CAT2,
    "2 разряд": SportsRank.CAT2,
    "cat2": SportsRank.CAT2,
    "3": SportsRank.CAT3,
    "3 разряд": SportsRank.CAT3,
    "cat3": SportsRank.CAT3,
}

TIER_MAP = {
    "winner": PlacementTier.WINNER,
    "prize_winner": PlacementTier.PRIZE_WINNER,
    "finalist": PlacementTier.FINALIST,
    "participant": PlacementTier.PARTICIPANT,
}


def parse_synthetic_uuid(val: str) -> uuid.UUID:
    """Parse synthetic or hex uuid, mapping leading non-hex chars deterministically."""
    try:
        return uuid.UUID(val)
    except ValueError:
        if val.startswith("p"):
            return uuid.UUID("b" + val[1:])
        return uuid.uuid5(uuid.NAMESPACE_DNS, val)


class Command(BaseCommand):
    help = "Seed database with initial test dataset (mode=mini or mode=full)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            type=str,
            default="mini",
            choices=["mini", "full"],
            help="Seed mode: mini (stand showcase) or full",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        mode = options["mode"]
        if mode == "full":
            return self._seed_full()

        self.stdout.write(self.style.NOTICE(f"Seeding database in mode '{mode}'..."))

        # --- 1. Skills Taxonomy ---
        skills_data = [
            ("python", "Python", ["py"]),
            ("django", "Django", ["drf", "django rest"]),
            ("fastapi", "FastAPI", ["asgi"]),
            ("postgresql", "PostgreSQL", ["postgres", "pgvector"]),
            ("docker", "Docker", ["container"]),
            ("react", "React", ["reactjs"]),
            ("typescript", "TypeScript", ["ts"]),
            ("sql", "SQL", ["mysql", "sqlite"]),
            ("algorithms", "Algorithms & Data Structures", ["algo"]),
            ("pytorch", "PyTorch", ["torch"]),
        ]
        skills_map = {}
        for skill_id, name, aliases in skills_data:
            skill, _ = Skill.objects.get_or_create(
                id=skill_id, defaults={"name": name, "aliases": aliases, "topic": "general"}
            )
            skills_map[skill_id] = skill

        # --- 2. Companies & Employers ---
        # Company 1: Yandex Mock
        comp1, _ = Company.objects.get_or_create(
            name="Yandex Tech",
            defaults={
                "inn": "7704340310",
                "website": "https://yandex.ru",
                "email_domain": "yandex-mock.ru",
                "business_domain": "BigTech / FinTech",
                "description": "Разработка высоконагруженных сервисов и инфраструктуры поиска.",
                "contact_email": "hr@yandex-mock.ru",
                "trust_level": TrustLevel.VERIFIED,
            },
        )
        emp1, _ = User.objects.get_or_create(
            email="techlead@yandex-mock.ru",
            defaults={
                "role": UserRole.EMPLOYER,
                "is_demo": True,
                "email_verified_at": timezone.now(),
            },
        )
        emp1.set_unusable_password()
        emp1.save()
        CompanyMember.objects.get_or_create(company=comp1, user=emp1)

        # Company 2: Sber Platform
        comp2, _ = Company.objects.get_or_create(
            name="СберТехнологии",
            defaults={
                "inn": "7707083893",
                "website": "https://sbertech.ru",
                "email_domain": "sbertech-mock.ru",
                "business_domain": "Banking & Cloud",
                "description": "Создание национальной облачной платформы и AI-решений.",
                "contact_email": "talent@sbertech-mock.ru",
                "trust_level": TrustLevel.DOMAIN,
            },
        )
        emp2, _ = User.objects.get_or_create(
            email="recruiter@sbertech-mock.ru",
            defaults={
                "role": UserRole.EMPLOYER,
                "is_demo": True,
                "email_verified_at": timezone.now(),
            },
        )
        emp2.set_unusable_password()
        emp2.save()
        CompanyMember.objects.get_or_create(company=comp2, user=emp2)

        # --- 3. Positions (Vacancies) ---
        # Position 1: Senior Python Backend
        pos1, _ = Position.objects.get_or_create(
            company=comp1,
            title="Senior Python / Django Архитектор",
            defaults={
                "specialization": Specialization.BACKEND,
                "grades": [Grade.SENIOR, Grade.MIDDLE],
                "must_skills": ["Python", "PostgreSQL", "Docker"],
                "nice_skills": ["Algorithms & Data Structures", "Django"],
                "work_formats": [WorkFormat.REMOTE, WorkFormat.HYBRID],
                "location": "Москва",
                "salary_min": 280000,
                "salary_max": 420000,
                "salary_type": SalaryType.NET,
                "team_context": "Команда платформы рекрутинга FSP Draft.",
                "description": "Проектирование распределенных бэкенд-сервисов, оптимизация PostgreSQL.",
                "is_public": True,
                "status": "open",
            },
        )

        # Position 2: Middle Backend Developer
        pos2, _ = Position.objects.get_or_create(
            company=comp1,
            title="Middle Python Backend Инженер",
            defaults={
                "specialization": Specialization.BACKEND,
                "grades": [Grade.MIDDLE],
                "must_skills": ["Python", "SQL"],
                "nice_skills": ["PostgreSQL", "Docker"],
                "work_formats": [WorkFormat.REMOTE],
                "location": "Любой город",
                "salary_min": 180000,
                "salary_max": 250000,
                "salary_type": SalaryType.GROSS,
                "team_context": "Core Services продуктовая команда.",
                "description": "Разработка API, интеграция с внешними реестрами и очередями Celery.",
                "is_public": True,
                "status": "open",
            },
        )

        # Position 3: Senior Frontend React/TS
        pos3, _ = Position.objects.get_or_create(
            company=comp2,
            title="Frontend Разработчик (React/TypeScript)",
            defaults={
                "specialization": Specialization.FRONTEND,
                "grades": [Grade.SENIOR, Grade.MIDDLE],
                "must_skills": ["React", "TypeScript"],
                "nice_skills": ["Docker"],
                "work_formats": [WorkFormat.HYBRID, WorkFormat.OFFICE],
                "location": "Санкт-Петербург",
                "salary_min": 220000,
                "salary_max": 320000,
                "salary_type": SalaryType.NET,
                "team_context": "Дизайн-система и клиентские порталы.",
                "description": "Разработка интерактивных дэшбордов кандидатов и работодателей.",
                "is_public": True,
                "status": "open",
            },
        )

        # --- 4. Candidates (6 Candidates, 4 with FSP) ---
        candidates_raw = SEEDED_CANDIDATES

        for cand in candidates_raw:
            user, _ = User.objects.get_or_create(
                email=cand["email"],
                defaults={
                    "role": UserRole.CANDIDATE,
                    "is_demo": True,
                    "email_verified_at": timezone.now(),
                },
            )
            user.set_unusable_password()
            user.save()

            # Consents
            Consent.objects.get_or_create(
                user=user, type=ConsentType.PROCESSING, defaults={"granted": True, "version": "1.0"}
            )
            Consent.objects.get_or_create(
                user=user,
                type=ConsentType.PUBLICATION,
                defaults={"granted": True, "version": "1.0"},
            )
            if cand["fsp_id"]:
                Consent.objects.get_or_create(
                    user=user,
                    type=ConsentType.FSP_SYNC,
                    defaults={"granted": True, "version": "1.0"},
                )

            # Profile
            profile, _ = CandidateProfile.objects.get_or_create(
                user=user,
                defaults={
                    "public_id": cand["public_id"],
                    "full_name": cand["name"],
                    "city": cand["city"],
                    "specialization": cand["spec"],
                    "claimed_grade": cand["grade"],
                    "salary_min": cand["salary_min"],
                    "salary_max": cand["salary_max"],
                    "salary_type": SalaryType.NET,
                    "open_to_offers": True,
                    "work_formats": [WorkFormat.REMOTE, WorkFormat.HYBRID],
                    "about": f"Опытный разработчик в направлении {cand['spec']}. Участник проектов на Python.",
                    "completeness": 90,
                },
            )

            # Contacts (Stored securely in separate table)
            CandidateContact.objects.get_or_create(
                user=user,
                defaults={
                    "email": cand["email"],
                    "phone": "+7 (999) 123-45-67",
                    "telegram": f"@{cand['email'].split('@')[0]}",
                },
            )

            # Skills
            for skill_id, source in cand["skills"]:
                skill_obj = skills_map.get(skill_id)
                if skill_obj:
                    CandidateSkill.objects.get_or_create(
                        candidate=profile,
                        skill=skill_obj,
                        source=source,
                        defaults={"level": 0.8 if source == EvidenceSource.TEST else 0.5},
                    )

            # League Membership
            LeagueMembership.objects.get_or_create(
                candidate=user,
                specialization=cand["spec"],
                defaults={
                    "grade": cand["grade"],
                    "status": cand["league_status"],
                    "rating": cand["rating"],
                    "strength": cand["strength"],
                    "base_strength": cand.get("base_strength", cand["strength"]),
                    "fsp_boost": cand.get("fsp_boost", 0.0),
                    "confirmed_at": timezone.now()
                    if cand["league_status"] == LeagueStatus.CONFIRMED
                    else None,
                },
            )

            # FSP Link & Results
            if cand["fsp_id"]:
                fsp_link, _ = FSPLink.objects.get_or_create(
                    candidate=user,
                    defaults={
                        "participant_id": cand["fsp_id"],
                        "sports_rank": cand["fsp_rank"] or "",
                        "sync_status": SyncStatus.OK,
                        "last_sync_at": timezone.now(),
                    },
                )
                for event_id, event_name, discipline, event_date, place, tier, total_part in cand[
                    "results"
                ]:
                    FSPResult.objects.get_or_create(
                        candidate=user,
                        event_id=event_id,
                        defaults={
                            "event_name": event_name,
                            "discipline": discipline,
                            "date": event_date,
                            "placement": place,
                            "tier": tier,
                            "participants_total": total_part,
                        },
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully seeded database: {len(candidates_raw)} candidates, 2 companies, 3 positions, 4 FSP profiles."
            )
        )

    def _seed_full(self):
        self.stdout.write(
            self.style.NOTICE("Seeding database in mode 'full' from seed_data/full/...")
        )
        data_dir = Path(settings.BASE_DIR) / "seed_data" / "full"
        if not data_dir.exists():
            raise CommandError(f"Seed data directory not found: {data_dir}")

        companies_file = data_dir / "companies.jsonl"
        positions_file = data_dir / "positions.jsonl"
        candidates_file = data_dir / "candidates.jsonl"

        for file_path in [companies_file, positions_file, candidates_file]:
            if not file_path.exists():
                raise CommandError(f"Required seed file not found: {file_path}")

        # 1. Taxonomy
        sync_taxonomy_to_db()

        # 2. Companies & Employer Members
        company_count = 0
        with open(companies_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                c_data = json.loads(line)
                c_id = parse_synthetic_uuid(c_data["id"])
                comp, _ = Company.objects.update_or_create(
                    id=c_id,
                    defaults={
                        "name": c_data["name"],
                        "inn": c_data.get("inn", ""),
                        "website": c_data.get("website", ""),
                        "email_domain": c_data.get("email_domain", ""),
                        "business_domain": c_data.get("business_domain", ""),
                        "description": c_data.get("description", ""),
                        "contact_email": c_data.get("contact_email", ""),
                        "trust_level": c_data.get("trust_level", TrustLevel.NONE),
                    },
                )
                company_count += 1
                for member in c_data.get("members", []):
                    m_email = member["email"]
                    emp_user, _ = User.objects.get_or_create(
                        email=m_email,
                        defaults={
                            "role": UserRole.EMPLOYER,
                            "is_demo": True,
                            "email_verified_at": timezone.now(),
                        },
                    )
                    emp_user.set_unusable_password()
                    emp_user.save()
                    CompanyMember.objects.get_or_create(company=comp, user=emp_user)

        # 3. Positions
        pos_count = 0
        with open(positions_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                p_data = json.loads(line)
                p_id = parse_synthetic_uuid(p_data["id"])
                c_id = parse_synthetic_uuid(p_data["company_id"])
                Position.objects.update_or_create(
                    id=p_id,
                    defaults={
                        "company_id": c_id,
                        "title": p_data["title"],
                        "specialization": p_data["specialization"],
                        "grades": p_data["grades"],
                        "must_skills": p_data.get("must_skills", []),
                        "nice_skills": p_data.get("nice_skills", []),
                        "work_formats": p_data.get("work_formats", []),
                        "location": p_data.get("location", ""),
                        "salary_min": p_data["salary_min"],
                        "salary_max": p_data["salary_max"],
                        "salary_type": p_data["salary_type"],
                        "team_context": p_data.get("team_context", ""),
                        "description": p_data.get("description", ""),
                        "is_public": p_data.get("is_public", True),
                        "status": p_data.get("status", "open"),
                    },
                )
                pos_count += 1

        # 4. Candidates
        cand_count = 0
        with open(candidates_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                cand = json.loads(line)
                cand_id = parse_synthetic_uuid(cand["id"])
                email = cand["email"]

                user, _ = User.objects.get_or_create(
                    email=email,
                    defaults={
                        "id": cand_id,
                        "role": UserRole.CANDIDATE,
                        "is_demo": True,
                        "email_verified_at": timezone.now(),
                    },
                )
                user.set_unusable_password()
                user.save()

                for consent in cand.get("consents", []):
                    c_type = consent["type"]
                    if not Consent.objects.filter(user=user, type=c_type).exists():
                        Consent.objects.create(
                            user=user,
                            type=c_type,
                            granted=consent.get("granted", True),
                            version=consent.get("version", "1.0"),
                        )

                blocked = [
                    parse_synthetic_uuid(cid)
                    for cid in cand.get("blocked_company_ids", [])
                ]
                profile, _ = CandidateProfile.objects.update_or_create(
                    user=user,
                    defaults={
                        "public_id": cand["public_id"],
                        "full_name": cand.get("full_name", ""),
                        "city": cand.get("city", ""),
                        "timezone": cand.get("timezone", "Europe/Moscow"),
                        "specialization": cand.get("specialization", ""),
                        "claimed_grade": cand.get("claimed_grade", ""),
                        "years_experience": cand.get("years_experience"),
                        "roles": cand.get("roles", []),
                        "work_formats": cand.get("work_formats", []),
                        "salary_min": cand.get("salary_min"),
                        "salary_max": cand.get("salary_max"),
                        "salary_type": cand.get("salary_type", "net"),
                        "salary_floor": cand.get("salary_floor"),
                        "open_to_offers": cand.get("open_to_offers", True),
                        "blind_mode": cand.get("blind_mode", False),
                        "blocked_company_ids": blocked,
                        "about": cand.get("about", ""),
                        "completeness": cand.get("completeness", 0),
                    },
                )

                contacts = cand.get("contacts", {})
                CandidateContact.objects.update_or_create(
                    user=user,
                    defaults={
                        "email": contacts.get("email", user.email),
                        "phone": contacts.get("phone", ""),
                        "telegram": contacts.get("telegram", ""),
                    },
                )

                for s in cand.get("skills", []):
                    s_id = s["skill_id"]
                    skill_obj, _ = Skill.objects.get_or_create(
                        id=s_id,
                        defaults={"name": s_id.title(), "topic": "general"},
                    )
                    source = s.get("source", EvidenceSource.TEST)
                    level = s.get("level", 0.5)
                    CandidateSkill.objects.update_or_create(
                        candidate=profile,
                        skill=skill_obj,
                        source=source,
                        defaults={"level": level},
                    )

                l_data = cand.get("league")
                if l_data:
                    spec = l_data.get("specialization", profile.specialization)
                    status = l_data.get("status", LeagueStatus.CONFIRMED)
                    confirmed = l_data.get("confirmed", status == LeagueStatus.CONFIRMED)
                    LeagueMembership.objects.update_or_create(
                        candidate=user,
                        specialization=spec,
                        defaults={
                            "grade": l_data.get("grade", profile.claimed_grade),
                            "status": status,
                            "rating": l_data.get("rating", 1000),
                            "strength": l_data.get("strength", 50.0),
                            "base_strength": l_data.get(
                                "base_strength", l_data.get("strength", 50.0)
                            ),
                            "fsp_boost": l_data.get("fsp_boost", 0.0),
                            "confirmed_at": timezone.now() if confirmed else None,
                        },
                    )

                fsp_data = cand.get("fsp")
                if fsp_data:
                    sports_rank_raw = fsp_data.get("sports_rank", "")
                    sports_rank = SPORTS_RANK_MAP.get(sports_rank_raw, sports_rank_raw)
                    FSPLink.objects.update_or_create(
                        candidate=user,
                        defaults={
                            "participant_id": fsp_data["participant_id"],
                            "sports_rank": sports_rank,
                            "sync_status": SyncStatus.OK,
                            "last_sync_at": timezone.now(),
                        },
                    )
                    for res in fsp_data.get("results", []):
                        disc = DISCIPLINE_MAP.get(
                            res.get("discipline"), Discipline.ALGORITHMIC
                        )
                        raw_tier = res.get("tier", "")
                        tier = TIER_MAP.get(raw_tier)
                        if not tier:
                            place = res.get("placement", 999)
                            if place == 1:
                                tier = PlacementTier.WINNER
                            elif place <= 3:
                                tier = PlacementTier.PRIZE_WINNER
                            elif place <= 10:
                                tier = PlacementTier.FINALIST
                            else:
                                tier = PlacementTier.PARTICIPANT
                        FSPResult.objects.update_or_create(
                            candidate=user,
                            event_id=res["event_id"],
                            defaults={
                                "event_name": res["event_name"],
                                "discipline": disc,
                                "date": res["date"],
                                "placement": res["placement"],
                                "tier": tier,
                                "participants_total": res.get("participants_total", 100),
                            },
                        )

                cand_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully seeded database (full mode): {cand_count} candidates, "
                f"{company_count} companies, {pos_count} positions."
            )
        )
