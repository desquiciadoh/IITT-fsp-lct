"""Matching app serializers."""
from drf_spectacular.utils import extend_schema_field
from profiles.models import CandidateProfile
from rest_framework import serializers

from matching.models import Company, Position


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


class CompanyMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'name']


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
        salary_min = attrs['salary_min'] if 'salary_min' in attrs else (
            self.instance.salary_min if self.instance else None
        )
        salary_max = attrs['salary_max'] if 'salary_max' in attrs else (
            self.instance.salary_max if self.instance else None
        )

        if salary_min is not None and salary_min <= 0:
            raise serializers.ValidationError({'salary_min': 'salary_min must be greater than 0.'})
        if salary_min is not None and salary_max is not None and salary_max < salary_min:
            raise serializers.ValidationError({'salary_max': 'salary_max must be greater than or equal to salary_min.'})
        return attrs


class TalentLeagueSerializer(serializers.Serializer):
    specialization = serializers.CharField()
    grade = serializers.CharField()
    status = serializers.CharField()
    rating = serializers.IntegerField()
    percentile = serializers.FloatField(allow_null=True)
    strength = serializers.IntegerField(allow_null=True)


class TalentFSPSerializer(serializers.Serializer):
    linked = serializers.BooleanField()
    results_count = serializers.IntegerField()
    sports_rank = serializers.CharField(allow_null=True)


class TalentSkillSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    source = serializers.CharField()


class TalentShortSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    league = serializers.SerializerMethodField()
    fsp = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    verified_topics = serializers.SerializerMethodField()

    class Meta:
        model = CandidateProfile
        fields = [
            'public_id',
            'display_name',
            'city',
            'work_formats',
            'salary_min',
            'salary_max',
            'salary_type',
            'league',
            'fsp',
            'skills',
            'verified_topics',
            'last_active_at',
        ]

    @extend_schema_field(serializers.CharField())
    def get_display_name(self, obj):
        if obj.blind_mode:
            return f'Кандидат {obj.public_id}'
        return obj.full_name or f'Кандидат {obj.public_id}'

    @extend_schema_field(TalentLeagueSerializer)
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

    @extend_schema_field(TalentFSPSerializer)
    def get_fsp(self, obj):
        has_link = hasattr(obj.user, 'fsp_link')
        results_count = obj.user.fsp_results.count()
        return {
            'linked': has_link,
            'results_count': results_count,
            'sports_rank': obj.user.fsp_link.sports_rank if has_link else None,
        }

    @extend_schema_field(TalentSkillSerializer(many=True))
    def get_skills(self, obj):
        return [
            {'id': cs.skill_id, 'name': cs.skill.name, 'source': cs.source}
            for cs in obj.skills.select_related('skill').all()[:8]
        ]

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_verified_topics(self, obj):
        from assessment.models import AssessmentItem
        from core.enums import AssessmentStatus
        topics = list(AssessmentItem.objects.filter(
            assessment__candidate=obj.user,
            assessment__status=AssessmentStatus.FINISHED,
            correct=True,
        ).values_list('family__topic', flat=True).distinct())
        return [t for t in topics if t]


class JdParseRequestSerializer(serializers.Serializer):
    text = serializers.CharField(min_length=10, required=False)
    raw_text = serializers.CharField(min_length=10, required=False)

    def validate(self, attrs):
        text = attrs.get('text') or attrs.get('raw_text')
        if not text:
            raise serializers.ValidationError({'text': 'This field is required.'})
        attrs['text'] = text
        return attrs


class JdDraftSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True, default='')
    specialization = serializers.CharField(required=False, allow_blank=True, default='backend')
    grades = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    must_skills = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    nice_skills = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    work_formats = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    location = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    salary_min = serializers.IntegerField(required=False, allow_null=True, default=None)
    salary_max = serializers.IntegerField(required=False, allow_null=True, default=None)
    salary_type = serializers.CharField(required=False, allow_blank=True, default='gross')
    team_context = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True, default='')


class JdParseBlueprintItemSerializer(serializers.Serializer):
    topic = serializers.CharField()
    weight = serializers.FloatField()


class JdParseResultSerializer(serializers.Serializer):
    draft = JdDraftSerializer()
    unknown_terms = serializers.ListField(child=serializers.CharField(), default=list)
    blueprint = JdParseBlueprintItemSerializer(many=True, default=list)
    source = serializers.CharField(default='rules')

