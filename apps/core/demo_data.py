"""Shared demo personas data and reset logic (R17)."""

from datetime import date

from django.utils import timezone

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
    UserRole,
    WorkFormat,
)

SEEDED_CANDIDATES = [
    {
        "email": "anna.fsp@example.com",
        "name": "Анна Воронова",
        "city": "Москва",
        "public_id": "C-7F3A2B",
        "spec": Specialization.BACKEND,
        "grade": Grade.SENIOR,
        "league_status": LeagueStatus.CONFIRMED,
        "rating": 1250,
        "strength": 95.0,
        "base_strength": 85.0,
        "fsp_boost": 10.0,
        "salary_min": 290000,
        "salary_max": 380000,
        "fsp_id": "FSP-000123",
        "fsp_rank": SportsRank.KMS,
        "skills": [
            ("python", EvidenceSource.TEST),
            ("postgresql", EvidenceSource.TEST),
            ("algorithms", EvidenceSource.FSP),
        ],
        "results": [
            (
                "CHAMP-2025",
                "Чемпионат России по спортивному программированию 2025",
                Discipline.ALGORITHMIC,
                date(2025, 11, 20),
                2,
                PlacementTier.PRIZE_WINNER,
                180,
            ),
            (
                "CUP-2025",
                "Кубок Федерации 2025 (Продуктовое программирование)",
                Discipline.PRODUCT,
                date(2025, 6, 15),
                1,
                PlacementTier.WINNER,
                64,
            ),
        ],
    },
    {
        "email": "mikhail.sp@example.com",
        "name": "Михаил Соколов",
        "city": "Казань",
        "public_id": "C-4B9E1A",
        "spec": Specialization.BACKEND,
        "grade": Grade.MIDDLE,
        "league_status": LeagueStatus.CONFIRMED,
        "rating": 1120,
        "strength": 84.0,
        "base_strength": 79.0,
        "fsp_boost": 5.0,
        "salary_min": 190000,
        "salary_max": 240000,
        "fsp_id": "FSP-000456",
        "fsp_rank": SportsRank.CAT1,
        "skills": [
            ("python", EvidenceSource.TEST),
            ("docker", EvidenceSource.TEST),
            ("algorithms", EvidenceSource.FSP),
        ],
        "results": [
            (
                "MOSCOW-2025",
                "Первенство Москвы 2025",
                Discipline.INFOSEC,
                date(2025, 9, 10),
                3,
                PlacementTier.PRIZE_WINNER,
                120,
            ),
        ],
    },
    {
        "email": "dmitry.algo@example.com",
        "name": "Дмитрий Кузнецов",
        "city": "Новосибирск",
        "public_id": "C-1A8D7C",
        "spec": Specialization.BACKEND,
        "grade": Grade.JUNIOR,
        "league_status": LeagueStatus.CONFIRMED,
        "rating": 1040,
        "strength": 72.0,
        "base_strength": 67.0,
        "fsp_boost": 5.0,
        "salary_min": 100000,
        "salary_max": 140000,
        "fsp_id": "FSP-000789",
        "fsp_rank": SportsRank.CAT2,
        "skills": [("python", EvidenceSource.TEST), ("sql", EvidenceSource.DECLARED)],
        "results": [
            (
                "SIBERIA-2025",
                "Региональный кубок Сибири по СП",
                Discipline.ALGORITHMIC,
                date(2025, 5, 12),
                5,
                PlacementTier.FINALIST,
                60,
            ),
        ],
    },
    {
        "email": "elena.fe@example.com",
        "name": "Елена Морозова",
        "city": "Санкт-Петербург",
        "public_id": "C-9E2F4D",
        "spec": Specialization.FRONTEND,
        "grade": Grade.MIDDLE,
        "league_status": LeagueStatus.CONFIRMED,
        "rating": 1100,
        "strength": 80.0,
        "base_strength": 75.0,
        "fsp_boost": 5.0,
        "salary_min": 200000,
        "salary_max": 260000,
        "fsp_id": "FSP-000321",
        "fsp_rank": SportsRank.CAT3,
        "skills": [("react", EvidenceSource.TEST), ("typescript", EvidenceSource.TEST)],
        "results": [
            (
                "HACKATHON-2025",
                "Студенческий хакатон ФСП",
                Discipline.PRODUCT,
                date(2025, 4, 18),
                3,
                PlacementTier.PRIZE_WINNER,
                45,
            ),
        ],
    },
    {
        "email": "alex.dev@example.com",
        "name": "Алексей Смирнов",
        "city": "Екатеринбург",
        "public_id": "C-3D5A8B",
        "spec": Specialization.BACKEND,
        "grade": Grade.MIDDLE,
        "league_status": LeagueStatus.CONFIRMED,
        "rating": 1080,
        "strength": 75.0,
        "base_strength": 75.0,
        "fsp_boost": 0.0,
        "salary_min": 180000,
        "salary_max": 220000,
        "fsp_id": None,
        "fsp_rank": None,
        "skills": [
            ("python", EvidenceSource.TEST),
            ("django", EvidenceSource.DECLARED),
            ("docker", EvidenceSource.DECLARED),
        ],
        "results": [],
    },
    {
        "email": "ivan.unconfirmed@example.com",
        "name": "Иван Петров",
        "city": "Самара",
        "public_id": "C-8C6B2E",
        "spec": Specialization.BACKEND,
        "grade": Grade.SENIOR,
        "league_status": LeagueStatus.UNCONFIRMED,
        "rating": 920,
        "strength": 45.0,
        "base_strength": 45.0,
        "fsp_boost": 0.0,
        "salary_min": 250000,
        "salary_max": 350000,
        "fsp_id": None,
        "fsp_rank": None,
        "skills": [("python", EvidenceSource.DECLARED)],
        "results": [],
    },
]

SEEDED_CANDIDATES_BY_EMAIL = {c["email"]: c for c in SEEDED_CANDIDATES}


def reset_demo_persona(user):
    """Restores persona's seeded data, wipes assessment sessions, resets clock offset (R17)."""
    user.clock_offset_days = 0
    user.save(update_fields=["clock_offset_days"])

    from assessment.models import AssessmentSession, LeagueMembership
    from identity.models import Consent
    from matching.models import CompanyMember
    from outreach.models import ContactGrant, Offer
    from profiles.models import CandidateContact, CandidateProfile, CandidateSkill, Skill

    # Wipe assessment sessions created during demo
    AssessmentSession.objects.filter(candidate=user).delete()

    if user.role == UserRole.CANDIDATE:
        Offer.objects.filter(candidate=user).delete()
        ContactGrant.objects.filter(candidate=user).delete()

        cand_data = SEEDED_CANDIDATES_BY_EMAIL.get(user.email)
        if cand_data:
            profile, _ = CandidateProfile.objects.get_or_create(
                user=user,
                defaults={"public_id": cand_data["public_id"]},
            )
            profile.public_id = cand_data["public_id"]
            profile.full_name = cand_data["name"]
            profile.city = cand_data["city"]
            profile.specialization = cand_data["spec"]
            profile.claimed_grade = cand_data["grade"]
            profile.salary_min = cand_data["salary_min"]
            profile.salary_max = cand_data["salary_max"]
            profile.salary_type = SalaryType.NET
            profile.open_to_offers = True
            profile.work_formats = [WorkFormat.REMOTE, WorkFormat.HYBRID]
            profile.about = f"Опытный разработчик в направлении {cand_data['spec']}. Участник проектов на Python."
            profile.completeness = 90
            profile.blocked_companies = []
            profile.save()

            LeagueMembership.objects.filter(candidate=user).exclude(
                specialization=cand_data["spec"]
            ).delete()
            membership, _ = LeagueMembership.objects.get_or_create(
                candidate=user,
                specialization=cand_data["spec"],
                defaults={
                    "grade": cand_data["grade"],
                    "status": cand_data["league_status"],
                    "rating": cand_data["rating"],
                    "strength": cand_data["strength"],
                    "base_strength": cand_data.get("base_strength", cand_data["strength"]),
                    "fsp_boost": cand_data.get("fsp_boost", 0.0),
                },
            )
            membership.grade = cand_data["grade"]
            membership.status = cand_data["league_status"]
            membership.rating = cand_data["rating"]
            membership.strength = cand_data["strength"]
            membership.base_strength = cand_data.get("base_strength", cand_data["strength"])
            membership.fsp_boost = cand_data.get("fsp_boost", 0.0)
            membership.next_attempt_at = None
            membership.confirmed_at = (
                timezone.now() if cand_data["league_status"] == LeagueStatus.CONFIRMED else None
            )
            membership.save()

            profile.skills.all().delete()
            for skill_id, source in cand_data["skills"]:
                skill_obj, _ = Skill.objects.get_or_create(
                    id=skill_id,
                    defaults={"name": skill_id.capitalize(), "topic": "general"},
                )
                CandidateSkill.objects.create(
                    candidate=profile,
                    skill=skill_obj,
                    source=source,
                    level=0.8 if source == EvidenceSource.TEST else 0.5,
                )

            Consent.objects.update_or_create(
                user=user,
                type=ConsentType.PROCESSING,
                defaults={"granted": True, "version": "1.0"},
            )
            Consent.objects.update_or_create(
                user=user,
                type=ConsentType.PUBLICATION,
                defaults={"granted": True, "version": "1.0"},
            )
            if cand_data.get("fsp_id"):
                Consent.objects.update_or_create(
                    user=user,
                    type=ConsentType.FSP_SYNC,
                    defaults={"granted": True, "version": "1.0"},
                )

            CandidateContact.objects.update_or_create(
                user=user,
                defaults={
                    "email": cand_data["email"],
                    "phone": "+7 (999) 123-45-67",
                    "telegram": f"@{cand_data['email'].split('@')[0]}",
                },
            )
        else:
            LeagueMembership.objects.filter(candidate=user).update(next_attempt_at=None)
            if hasattr(user, "candidate_profile"):
                user.candidate_profile.open_to_offers = True
                user.candidate_profile.save(update_fields=["open_to_offers"])

    elif user.role == UserRole.EMPLOYER:
        member = CompanyMember.objects.filter(user=user).first()
        if member:
            Offer.objects.filter(company=member.company).delete()
