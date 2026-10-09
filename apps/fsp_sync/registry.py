"""FSP Registry adapter.

In production this calls the real FSP OIDC-protected API.
Currently returns data from a mock registry for development.
"""
from core.enums import Discipline, PlacementTier, SportsRank

MOCK_REGISTRY = {
    'FSP-000123': {
        'sports_rank': SportsRank.KMS,
        'results': [
            {
                'event_id': 'CHAMP-2025',
                'event_name': 'Чемпионат России по спортивному программированию 2025',
                'discipline': Discipline.ALGORITHMIC,
                'date': '2025-11-20',
                'stage': 'Финал',
                'format': 'individual',
                'placement': 2,
                'tier': PlacementTier.PRIZE_WINNER,
                'participants_total': 180,
            },
            {
                'event_id': 'CUP-2025',
                'event_name': 'Кубок Федерации 2025 (Продуктовое программирование)',
                'discipline': Discipline.PRODUCT,
                'date': '2025-06-15',
                'stage': 'Финал',
                'format': 'team',
                'team_size': 4,
                'placement': 1,
                'tier': PlacementTier.WINNER,
                'participants_total': 64,
            }
        ]
    },
    'FSP-000456': {
        'sports_rank': SportsRank.CAT1,
        'results': [
            {
                'event_id': 'MOSCOW-2025',
                'event_name': 'Первенство Москвы 2025',
                'discipline': Discipline.INFOSEC,
                'date': '2025-09-10',
                'stage': 'Финал',
                'format': 'individual',
                'placement': 3,
                'tier': PlacementTier.PRIZE_WINNER,
                'participants_total': 120,
            }
        ]
    },
    'FSP-000789': {
        'sports_rank': SportsRank.CAT2,
        'results': [
            {
                'event_id': 'SIBERIA-2025',
                'event_name': 'Региональный кубок Сибири по СП',
                'discipline': Discipline.ALGORITHMIC,
                'date': '2025-05-12',
                'stage': 'Финал',
                'format': 'individual',
                'placement': 5,
                'tier': PlacementTier.FINALIST,
                'participants_total': 60,
            }
        ]
    },
    'FSP-000321': {
        'sports_rank': SportsRank.CAT3,
        'results': [
            {
                'event_id': 'HACKATHON-2025',
                'event_name': 'Студенческий хакатон ФСП',
                'discipline': Discipline.PRODUCT,
                'date': '2025-04-18',
                'stage': 'Финал',
                'format': 'team',
                'team_size': 3,
                'placement': 3,
                'tier': PlacementTier.PRIZE_WINNER,
                'participants_total': 45,
            }
        ]
    }
}


def get_registry_data(participant_id: str) -> dict:
    """Fetch participant data from the FSP registry.

    TODO: Replace with real OIDC-authenticated API call.
    """
    return MOCK_REGISTRY.get(participant_id, {})
