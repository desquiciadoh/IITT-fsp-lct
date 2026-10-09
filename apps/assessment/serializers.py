"""Assessment serializers.

INVARIANT: ItemViewSerializer NEVER includes the `key` field or any derivative of it.
The answer key stays strictly server-side in assessment_items.key.
"""
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from assessment.models import AssessmentSession, AssessmentItem, LeagueMembership, ItemFamily
from core.enums import Specialization, Grade


class StartAssessmentSerializer(serializers.Serializer):
    specialization = serializers.ChoiceField(choices=Specialization.choices, default=Specialization.BACKEND)
    claimed_grade = serializers.ChoiceField(choices=Grade.choices, default=Grade.MIDDLE)
    mode = serializers.ChoiceField(choices=['full', 'trial'], default='full')


class ItemViewSerializer(serializers.ModelSerializer):
    """Client-facing representation of an assessment question.

    SECURITY INVARIANT: The 'key' field MUST NEVER be included in this serializer!
    """
    item_id = serializers.UUIDField(source='id', read_only=True)
    stem_md = serializers.CharField(source='view.stem_md', read_only=True)
    code = serializers.JSONField(source='view.code', read_only=True)
    options = serializers.JSONField(source='view.options', read_only=True)
    input_type = serializers.CharField(source='view.input_type', read_only=True)
    time_limit_s = serializers.IntegerField(source='view.time_limit_s', read_only=True)
    max_items = serializers.SerializerMethodField()
    level = serializers.SerializerMethodField()
    format = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentItem
        fields = [
            'item_id',
            'seq',
            'max_items',
            'level',
            'format',
            'stem_md',
            'code',
            'options',
            'input_type',
            'time_limit_s',
            'deadline_at',
            'served_at',
        ]
        # Notice: 'key' is NOT in fields!

    @extend_schema_field(serializers.IntegerField())
    def get_max_items(self, obj):
        return obj.assessment.items.count()

    @extend_schema_field(serializers.CharField())
    def get_level(self, obj):
        return obj.assessment.claimed_grade

    @extend_schema_field(serializers.CharField())
    def get_format(self, obj):
        return getattr(obj.family, 'format', 'concept_mcq') if obj.family else 'concept_mcq'


class AssessmentSessionSerializer(serializers.ModelSerializer):
    current = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentSession
        fields = [
            'id',
            'specialization',
            'claimed_grade',
            'kind',
            'mode',
            'status',
            'current',
            'theta',
            'se',
            'rating',
            'result_grade',
            'decision',
            'promotion_unlocked',
            'started_at',
            'finished_at',
        ]

    @extend_schema_field(ItemViewSerializer)
    def get_current(self, obj):
        # Current unanswered item
        item = obj.items.filter(answered_at__isnull=True).order_by('seq').first()
        if item:
            return ItemViewSerializer(item).data
        return None


class AnswerRequestSerializer(serializers.Serializer):
    item_id = serializers.UUIDField()
    option_id = serializers.CharField(required=False, allow_blank=True)
    value = serializers.CharField(required=False, allow_blank=True)
    integrity = serializers.JSONField(required=False)


class AssessmentTopicSerializer(serializers.Serializer):
    topic = serializers.CharField()
    level = serializers.CharField()


class AssessmentEvidenceSerializer(serializers.Serializer):
    seq = serializers.IntegerField()
    level = serializers.CharField()
    correct = serializers.BooleanField()


class AssessmentFallbackSerializer(serializers.Serializer):
    grade = serializers.CharField()
    mode = serializers.CharField()


class AssessmentResultSerializer(serializers.ModelSerializer):
    rating_ci = serializers.SerializerMethodField()
    topics = serializers.SerializerMethodField()
    evidence = serializers.SerializerMethodField()
    next_attempt_at = serializers.SerializerMethodField()
    fallback = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentSession
        fields = [
            'id',
            'kind',
            'specialization',
            'claimed_grade',
            'mode',
            'status',
            'theta',
            'se',
            'rating',
            'rating_ci',
            'result_grade',
            'decision',
            'promotion_unlocked',
            'counts_as_attempt',
            'fallback',
            'topics',
            'evidence',
            'next_attempt_at',
            'started_at',
            'finished_at',
        ]

    @extend_schema_field(serializers.IntegerField())
    def get_rating_ci(self, obj):
        if obj.se is not None:
            return int(round(obj.se * 200))
        return 40

    @extend_schema_field(AssessmentTopicSerializer(many=True))
    def get_topics(self, obj):
        topics_map = {}
        for it in obj.items.select_related('family').all():
            topic_name = it.family.topic if it.family else 'general'
            if topic_name not in topics_map:
                topics_map[topic_name] = []
            topics_map[topic_name].append(bool(it.correct))

        result = []
        for topic, results in topics_map.items():
            acc = sum(results) / len(results) if results else 0
            lvl = 'strong' if acc >= 0.7 else ('moderate' if acc >= 0.4 else 'limited')
            result.append({'topic': topic, 'level': lvl})
        return result

    @extend_schema_field(AssessmentEvidenceSerializer(many=True))
    def get_evidence(self, obj):
        return [
            {
                'seq': it.seq,
                'level': obj.claimed_grade,
                'correct': bool(it.correct),
            }
            for it in obj.items.order_by('seq')
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_next_attempt_at(self, obj):
        from assessment.models import LeagueMembership
        lm = LeagueMembership.objects.filter(candidate=obj.candidate, specialization=obj.specialization).first()
        if lm and lm.next_attempt_at:
            return lm.next_attempt_at.isoformat()
        return None

    @extend_schema_field(AssessmentFallbackSerializer(allow_null=True))
    def get_fallback(self, obj):
        if obj.decision == 'unconfirmed':
            from core.enums import Grade
            lower_grades = {
                Grade.SENIOR: Grade.MIDDLE,
                Grade.MIDDLE: Grade.JUNIOR,
                Grade.JUNIOR: Grade.INTERN,
            }
            lower = lower_grades.get(obj.claimed_grade)
            if lower:
                return {'grade': lower, 'mode': 'instant'}
        return None


class FallbackRequestSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=['instant', 'short_test'], default='instant')


class LeagueShelfSerializer(serializers.Serializer):
    specialization = serializers.CharField()
    grade = serializers.CharField()
    confirmed = serializers.IntegerField()
    unconfirmed = serializers.IntegerField()
    median_expectation = serializers.IntegerField(allow_null=True, required=False)


class ValidationTifSerializer(serializers.Serializer):
    theta = serializers.ListField(child=serializers.FloatField())
    info = serializers.ListField(child=serializers.FloatField())


class ValidationLeakAttackSerializer(serializers.Serializer):
    leak_share = serializers.FloatField()
    static_dtheta = serializers.FloatField()
    parametric_dtheta = serializers.FloatField()


class ValidationAssessmentMetricsSerializer(serializers.Serializer):
    simulees = serializers.IntegerField()
    exact_acc = serializers.FloatField()
    adjacent_acc = serializers.FloatField()
    qwk = serializers.FloatField()
    retest_same_grade = serializers.FloatField()
    retest_r = serializers.FloatField()
    median_len = serializers.FloatField()
    max_family_exposure = serializers.FloatField()
    collision_rate = serializers.FloatField()
    generator_errors = serializers.IntegerField()
    confusion = serializers.ListField(child=serializers.ListField(child=serializers.IntegerField()))
    tif = ValidationTifSerializer()
    leak_attack = ValidationLeakAttackSerializer(many=True)


class ValidationMatchingSystemSerializer(serializers.Serializer):
    name = serializers.CharField()
    ndcg10 = serializers.FloatField()
    p10 = serializers.FloatField()
    r50 = serializers.FloatField()
    mrr = serializers.FloatField()


class ValidationMatchingMetricsSerializer(serializers.Serializer):
    candidates = serializers.IntegerField()
    needs = serializers.IntegerField()
    non_fsp_parity = serializers.FloatField()
    pool_p95_ms = serializers.FloatField()
    systems = ValidationMatchingSystemSerializer(many=True)


class ValidationReportSerializer(serializers.Serializer):
    generated_at = serializers.CharField()
    git_sha = serializers.CharField()
    synthetic_fixture = serializers.BooleanField()
    assessment = ValidationAssessmentMetricsSerializer()
    matching = ValidationMatchingMetricsSerializer()


class LeagueMembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeagueMembership
        fields = [
            'specialization',
            'grade',
            'status',
            'theta',
            'se',
            'rating',
            'percentile',
            'strength',
            'confirmed_at',
            'next_attempt_at',
            'next_promotion_at',
        ]
