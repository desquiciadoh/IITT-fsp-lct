"""Assessment serializers.

INVARIANT: ItemViewSerializer NEVER includes the `key` field or any derivative of it.
The answer key stays strictly server-side in assessment_items.key.
"""
from rest_framework import serializers
from assessment.models import AssessmentSession, AssessmentItem, LeagueMembership, ItemFamily


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

    class Meta:
        model = AssessmentItem
        fields = [
            'item_id',
            'seq',
            'stem_md',
            'code',
            'options',
            'input_type',
            'time_limit_s',
            'deadline_at',
            'served_at',
        ]
        # Notice: 'key' is NOT in fields!


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


class AssessmentResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentSession
        fields = [
            'id',
            'specialization',
            'claimed_grade',
            'kind',
            'mode',
            'status',
            'theta',
            'se',
            'rating',
            'result_grade',
            'decision',
            'promotion_unlocked',
            'counts_as_attempt',
            'started_at',
            'finished_at',
        ]


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
