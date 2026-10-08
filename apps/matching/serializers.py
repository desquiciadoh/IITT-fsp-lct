"""Matching app serializers."""
from rest_framework import serializers
from matching.models import Company, Position, Shortlist
from profiles.models import CandidateProfile
from core.enums import SalaryType, WorkFormat, Grade, Specialization


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            'id',
            'name',
            'inn',
            'website',
            'email_domain',
            'business_domain',
            'description',
            'contact_email',
            'trust_level',
            'created_at',
        ]
        read_only_fields = ['id', 'trust_level', 'created_at']


class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = [
            'id',
            'company',
            'title',
            'specialization',
            'grades',
            'must_skills',
            'nice_skills',
            'work_formats',
            'location',
            'salary_min',
            'salary_max',
            'salary_type',
            'team_context',
            'description',
            'allow_adjacent',
            'is_public',
            'status',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        salary_min = attrs.get('salary_min') or (self.instance.salary_min if self.instance else None)
        salary_max = attrs.get('salary_max') or (self.instance.salary_max if self.instance else None)

        if salary_min is not None and salary_min <= 0:
            raise serializers.ValidationError({'salary_min': 'salary_min must be greater than 0.'})
        if salary_min is not None and salary_max is not None and salary_max < salary_min:
            raise serializers.ValidationError({'salary_max': 'salary_max must be greater than or equal to salary_min.'})
        return attrs


class TalentShortSerializer(serializers.ModelSerializer):
    league = serializers.SerializerMethodField()
    fsp = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()

    class Meta:
        model = CandidateProfile
        fields = [
            'public_id',
            'city',
            'work_formats',
            'salary_min',
            'salary_max',
            'salary_type',
            'league',
            'fsp',
            'skills',
            'last_active_at',
        ]

    def get_league(self, obj):
        lm = obj.user.league_memberships.first()
        if lm:
            return {
                'specialization': lm.specialization,
                'grade': lm.grade,
                'status': lm.status,
                'rating': lm.rating,
                'percentile': lm.percentile,
                'strength': lm.strength,
            }
        return None

    def get_fsp(self, obj):
        has_link = hasattr(obj.user, 'fsp_link')
        results_count = obj.user.fsp_results.count()
        return {
            'linked': has_link,
            'results_count': results_count,
            'sports_rank': obj.user.fsp_link.sports_rank if has_link else None,
        }

    def get_skills(self, obj):
        return [
            {'id': cs.skill_id, 'name': cs.skill.name, 'source': cs.source}
            for cs in obj.skills.select_related('skill').all()[:8]
        ]
