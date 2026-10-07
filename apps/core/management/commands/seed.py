"""Seed database command for FSP Draft.

Generates:
- 6+ candidates (including FSP prize-winners, standard candidates, confirmed and unconfirmed)
- 2 companies with company members
- 3+ positions with mandatory salary ranges and stack requirements
- 4 FSP achievement profiles with verified results
"""
import uuid
from datetime import date
from django.core.management.base import BaseCommand
from django.utils import timezone

from identity.models import User, Consent
from profiles.models import CandidateProfile, CandidateContact, Skill, CandidateSkill
from assessment.models import LeagueMembership
from matching.models import Company, CompanyMember, Position
from fsp_sync.models import FSPLink, FSPResult
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


class Command(BaseCommand):
    help = "Seed database with initial test dataset (mode=mini or mode=full)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--mode',
            type=str,
            default='mini',
            choices=['mini', 'full'],
            help='Seed mode: mini (stand showcase) or full',
        )

    def handle(self, *args, **options):
        mode = options['mode']
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
                id=skill_id,
                defaults={'name': name, 'aliases': aliases, 'topic': 'general'}
            )
            skills_map[skill_id] = skill

        # --- 2. Companies & Employers ---
        # Company 1: Yandex Mock
        comp1, _ = Company.objects.get_or_create(
            name="Yandex Tech",
            defaults={
                'inn': "7704340310",
                'website': "https://yandex.ru",
                'email_domain': "yandex-mock.ru",
                'business_domain': "BigTech / FinTech",
                'description': "Разработка высоконагруженных сервисов и инфраструктуры поиска.",
                'contact_email': "hr@yandex-mock.ru",
                'trust_level': TrustLevel.VERIFIED,
            }
        )
        emp1, _ = User.objects.get_or_create(
            email="techlead@yandex-mock.ru",
            defaults={'role': UserRole.EMPLOYER, 'is_demo': True, 'email_verified_at': timezone.now()}
        )
        emp1.set_password("demopassword")
        emp1.save()
        CompanyMember.objects.get_or_create(company=comp1, user=emp1)

        # Company 2: Sber Platform
        comp2, _ = Company.objects.get_or_create(
            name="СберТехнологии",
            defaults={
                'inn': "7707083893",
                'website': "https://sbertech.ru",
                'email_domain': "sbertech-mock.ru",
                'business_domain': "Banking & Cloud",
                'description': "Создание национальной облачной платформы и AI-решений.",
                'contact_email': "talent@sbertech-mock.ru",
                'trust_level': TrustLevel.DOMAIN,
            }
        )
        emp2, _ = User.objects.get_or_create(
            email="recruiter@sbertech-mock.ru",
            defaults={'role': UserRole.EMPLOYER, 'is_demo': True, 'email_verified_at': timezone.now()}
        )
        emp2.set_password("demopassword")
        emp2.save()
        CompanyMember.objects.get_or_create(company=comp2, user=emp2)

        # --- 3. Positions (Vacancies) ---
        # Position 1: Senior Python Backend
        pos1, _ = Position.objects.get_or_create(
            company=comp1,
            title="Senior Python / Django Архитектор",
            defaults={
                'specialization': Specialization.BACKEND,
                'grades': [Grade.SENIOR, Grade.MIDDLE],
                'must_skills': ["Python", "PostgreSQL", "Docker"],
                'nice_skills': ["Algorithms & Data Structures", "Django"],
                'work_formats': [WorkFormat.REMOTE, WorkFormat.HYBRID],
                'location': "Москва",
                'salary_min': 280000,
                'salary_max': 420000,
                'salary_type': SalaryType.NET,
                'team_context': "Команда платформы рекрутинга FSP Draft.",
                'description': "Проектирование распределенных бэкенд-сервисов, оптимизация PostgreSQL.",
                'is_public': True,
                'status': 'open',
            }
        )

        # Position 2: Middle Backend Developer
        pos2, _ = Position.objects.get_or_create(
            company=comp1,
            title="Middle Python Backend Инженер",
            defaults={
                'specialization': Specialization.BACKEND,
                'grades': [Grade.MIDDLE],
                'must_skills': ["Python", "SQL"],
                'nice_skills': ["PostgreSQL", "Docker"],
                'work_formats': [WorkFormat.REMOTE],
                'location': "Любой город",
                'salary_min': 180000,
                'salary_max': 250000,
                'salary_type': SalaryType.GROSS,
                'team_context': "Core Services продуктовая команда.",
                'description': "Разработка API, интеграция с внешними реестрами и очередями Celery.",
                'is_public': True,
                'status': 'open',
            }
        )

        # Position 3: Senior Frontend React/TS
        pos3, _ = Position.objects.get_or_create(
            company=comp2,
            title="Frontend Разработчик (React/TypeScript)",
            defaults={
                'specialization': Specialization.FRONTEND,
                'grades': [Grade.SENIOR, Grade.MIDDLE],
                'must_skills': ["React", "TypeScript"],
                'nice_skills': ["Docker"],
                'work_formats': [WorkFormat.HYBRID, WorkFormat.OFFICE],
                'location': "Санкт-Петербург",
                'salary_min': 220000,
                'salary_max': 320000,
                'salary_type': SalaryType.NET,
                'team_context': "Дизайн-система и клиентские порталы.",
                'description': "Разработка интерактивных дэшбордов кандидатов и работодателей.",
                'is_public': True,
                'status': 'open',
            }
        )

        # --- 4. Candidates (6 Candidates, 4 with FSP) ---
        candidates_raw = [
            # 1. Anna - FSP Champion, Senior, Confirmed
            {
                'email': 'anna.fsp@example.com',
                'name': 'Анна Воронова',
                'city': 'Москва',
                'public_id': 'C-7F3A2B',
                'spec': Specialization.BACKEND,
                'grade': Grade.SENIOR,
                'league_status': LeagueStatus.CONFIRMED,
                'rating': 1250,
                'strength': 95.0,
                'salary_min': 290000,
                'salary_max': 380000,
                'fsp_id': 'FSP-000123',
                'fsp_rank': SportsRank.KMS,
                'skills': [('python', EvidenceSource.TEST), ('postgresql', EvidenceSource.TEST), ('algorithms', EvidenceSource.FSP)],
                'results': [
                    ("Чемпионат России по СП 2025", Discipline.ALGORITHMIC, 1, PlacementTier.WINNER, 200),
                    ("Кубок Федерации СП (Продукт)", Discipline.PRODUCT, 2, PlacementTier.PRIZE_WINNER, 80),
                ]
            },
            # 2. Mikhail - FSP Prize-Winner, Middle, Confirmed
            {
                'email': 'mikhail.sp@example.com',
                'name': 'Михаил Соколов',
                'city': 'Казань',
                'public_id': 'C-4B9E1A',
                'spec': Specialization.BACKEND,
                'grade': Grade.MIDDLE,
                'league_status': LeagueStatus.CONFIRMED,
                'rating': 1120,
                'strength': 84.0,
                'salary_min': 190000,
                'salary_max': 240000,
                'fsp_id': 'FSP-000456',
                'fsp_rank': SportsRank.CAT1,
                'skills': [('python', EvidenceSource.TEST), ('docker', EvidenceSource.TEST), ('algorithms', EvidenceSource.FSP)],
                'results': [
                    ("Первенство Москвы по СП 2025", Discipline.INFOSEC, 3, PlacementTier.PRIZE_WINNER, 120),
                ]
            },
            # 3. Dmitry - FSP Participant, Junior, Confirmed
            {
                'email': 'dmitry.algo@example.com',
                'name': 'Дмитрий Кузнецов',
                'city': 'Новосибирск',
                'public_id': 'C-1A8D7C',
                'spec': Specialization.BACKEND,
                'grade': Grade.JUNIOR,
                'league_status': LeagueStatus.CONFIRMED,
                'rating': 1040,
                'strength': 72.0,
                'salary_min': 100000,
                'salary_max': 140000,
                'fsp_id': 'FSP-000789',
                'fsp_rank': SportsRank.CAT2,
                'skills': [('python', EvidenceSource.TEST), ('sql', EvidenceSource.DECLARED)],
                'results': [
                    ("Региональный кубок Сибири по СП", Discipline.ALGORITHMIC, 5, PlacementTier.FINALIST, 60),
                ]
            },
            # 4. Elena - FSP Participant, Frontend, Confirmed
            {
                'email': 'elena.fe@example.com',
                'name': 'Елена Морозова',
                'city': 'Санкт-Петербург',
                'public_id': 'C-9E2F4D',
                'spec': Specialization.FRONTEND,
                'grade': Grade.MIDDLE,
                'league_status': LeagueStatus.CONFIRMED,
                'rating': 1100,
                'strength': 80.0,
                'salary_min': 200000,
                'salary_max': 260000,
                'fsp_id': 'FSP-000321',
                'fsp_rank': SportsRank.CAT3,
                'skills': [('react', EvidenceSource.TEST), ('typescript', EvidenceSource.TEST)],
                'results': [
                    ("Студенческий хакатон ФСП", Discipline.PRODUCT, 3, PlacementTier.PRIZE_WINNER, 45),
                ]
            },
            # 5. Alex - Non-FSP, Middle, Confirmed (Shows fair chance for standard engineers!)
            {
                'email': 'alex.dev@example.com',
                'name': 'Алексей Смирнов',
                'city': 'Екатеринбург',
                'public_id': 'C-3D5A8B',
                'spec': Specialization.BACKEND,
                'grade': Grade.MIDDLE,
                'league_status': LeagueStatus.CONFIRMED,
                'rating': 1080,
                'strength': 75.0,
                'salary_min': 180000,
                'salary_max': 220000,
                'fsp_id': None,
                'fsp_rank': None,
                'skills': [('python', EvidenceSource.TEST), ('django', EvidenceSource.DECLARED), ('docker', EvidenceSource.DECLARED)],
                'results': []
            },
            # 6. Ivan - Non-FSP, Claimed Senior, UNCONFIRMED (Shows unconfirmed profile policy: NOT hidden, but deranked)
            {
                'email': 'ivan.unconfirmed@example.com',
                'name': 'Иван Петров',
                'city': 'Самара',
                'public_id': 'C-8C6B2E',
                'spec': Specialization.BACKEND,
                'grade': Grade.SENIOR,
                'league_status': LeagueStatus.UNCONFIRMED,
                'rating': 920,
                'strength': 45.0,
                'salary_min': 250000,
                'salary_max': 350000,
                'fsp_id': None,
                'fsp_rank': None,
                'skills': [('python', EvidenceSource.DECLARED)],
                'results': []
            },
        ]

        for cand in candidates_raw:
            user, _ = User.objects.get_or_create(
                email=cand['email'],
                defaults={
                    'role': UserRole.CANDIDATE,
                    'is_demo': True,
                    'email_verified_at': timezone.now(),
                }
            )
            user.set_password("demopassword")
            user.save()

            # Consents
            Consent.objects.get_or_create(
                user=user,
                type=ConsentType.PROCESSING,
                defaults={'granted': True, 'version': '1.0'}
            )
            Consent.objects.get_or_create(
                user=user,
                type=ConsentType.PUBLICATION,
                defaults={'granted': True, 'version': '1.0'}
            )
            if cand['fsp_id']:
                Consent.objects.get_or_create(
                    user=user,
                    type=ConsentType.FSP_SYNC,
                    defaults={'granted': True, 'version': '1.0'}
                )

            # Profile
            profile, _ = CandidateProfile.objects.get_or_create(
                user=user,
                defaults={
                    'public_id': cand['public_id'],
                    'full_name': cand['name'],
                    'city': cand['city'],
                    'specialization': cand['spec'],
                    'claimed_grade': cand['grade'],
                    'salary_min': cand['salary_min'],
                    'salary_max': cand['salary_max'],
                    'salary_type': SalaryType.NET,
                    'open_to_offers': True,
                    'work_formats': [WorkFormat.REMOTE, WorkFormat.HYBRID],
                    'about': f"Опытный разработчик в направлении {cand['spec']}. Участник проектов на Python.",
                    'completeness': 90,
                }
            )

            # Contacts (Stored securely in separate table)
            CandidateContact.objects.get_or_create(
                user=user,
                defaults={
                    'email': cand['email'],
                    'phone': '+7 (999) 123-45-67',
                    'telegram': f"@{cand['email'].split('@')[0]}",
                }
            )

            # Skills
            for skill_id, source in cand['skills']:
                skill_obj = skills_map.get(skill_id)
                if skill_obj:
                    CandidateSkill.objects.get_or_create(
                        candidate=profile,
                        skill=skill_obj,
                        source=source,
                        defaults={'level': 0.8 if source == EvidenceSource.TEST else 0.5}
                    )

            # League Membership
            LeagueMembership.objects.get_or_create(
                candidate=user,
                specialization=cand['spec'],
                defaults={
                    'grade': cand['grade'],
                    'status': cand['league_status'],
                    'rating': cand['rating'],
                    'strength': cand['strength'],
                    'confirmed_at': timezone.now() if cand['league_status'] == LeagueStatus.CONFIRMED else None,
                }
            )

            # FSP Link & Results
            if cand['fsp_id']:
                fsp_link, _ = FSPLink.objects.get_or_create(
                    candidate=user,
                    defaults={
                        'participant_id': cand['fsp_id'],
                        'sports_rank': cand['fsp_rank'] or '',
                        'sync_status': SyncStatus.OK,
                        'last_sync_at': timezone.now(),
                    }
                )
                for event_name, discipline, place, tier, total_part in cand['results']:
                    FSPResult.objects.get_or_create(
                        candidate=user,
                        event_id=f"EVT-{abs(hash(event_name)) % 10000}",
                        defaults={
                            'event_name': event_name,
                            'discipline': discipline,
                            'date': date(2025, 6, 1),
                            'placement': place,
                            'tier': tier,
                            'participants_total': total_part,
                        }
                    )

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded database: {len(candidates_raw)} candidates, 2 companies, 3 positions, 4 FSP profiles."
        ))
