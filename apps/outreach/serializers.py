"""Outreach app serializers."""
from core.enums import ContactChannel, DeclineReason, SalaryType
from core.errors import ContactNotGranted
from drf_spectacular.utils import extend_schema_field
from matching.serializers import CompanySerializer, TalentShortSerializer
from rest_framework import serializers

from outreach.models import Offer
from outreach.services import ContactAccessService


class OfferDeclineSerializer(serializers.Serializer):
    reason = serializers.CharField()
    comment = serializers.CharField(allow_blank=True)


class CandidateContactsDisplaySerializer(serializers.Serializer):
    full_name = serializers.CharField(required=False)
    email = serializers.EmailField()
    phone = serializers.CharField(required=False, allow_blank=True)
    telegram = serializers.CharField(required=False, allow_blank=True)


class OfferSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    candidate_public_id = serializers.CharField(write_only=True, required=False)
    candidate_contacts = serializers.SerializerMethodField()
    why_you = serializers.JSONField(read_only=True)
    talent = serializers.SerializerMethodField()
    decline = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        fields = [
            'id',
            'company',
            'position',
            'candidate_public_id',
            'talent',
            'title',
            'description',
            'salary_min',
            'salary_max',
            'salary_type',
            'currency',
            'contact_channel',
            'contact_value',
            'status',
            'decline_reason',
            'decline_comment',
            'decline',
            'why_you',
            'version',
            'candidate_contacts',
            'expires_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'status', 'version', 'expires_at', 'created_at', 'updated_at']

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

    @extend_schema_field(TalentShortSerializer)
    def get_talent(self, obj):
        try:
            profile = obj.candidate.candidate_profile
            return TalentShortSerializer(profile, context=self.context).data
        except Exception:
            return None

    @extend_schema_field(OfferDeclineSerializer)
    def get_decline(self, obj):
        if obj.decline_reason or obj.decline_comment:
            return {
                'reason': obj.decline_reason,
                'comment': obj.decline_comment,
            }
        return None

    @extend_schema_field(CandidateContactsDisplaySerializer)
    def get_candidate_contacts(self, obj):
        # Contacts are returned ONLY if user has active grant
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None

        # If candidate is viewing their own offer, show contacts
        if request.user.id == obj.candidate_id:
            try:
                c = obj.candidate.candidate_contacts
                return {'email': c.email, 'phone': c.phone, 'telegram': c.telegram}
            except Exception:
                return {'email': obj.candidate.email}

        # If employer is viewing: check if contact grant exists (independent of offer status)
        try:
            contacts = ContactAccessService.get_contacts(
                company_id=obj.company_id,
                candidate_id=obj.candidate_id,
                actor_id=request.user.id,
            )
            return {
                'full_name': contacts.full_name,
                'email': contacts.email,
                'phone': contacts.phone,
                'telegram': contacts.telegram,
            }
        except ContactNotGranted:
            return None


class CreateOfferSerializer(serializers.Serializer):
    candidate_public_id = serializers.CharField(required=True)
    position = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(max_length=255, required=False, default='Draft Offer')
    description = serializers.CharField(required=False, allow_blank=True, default='')
    salary_min = serializers.IntegerField(min_value=1, required=True)
    salary_max = serializers.IntegerField(min_value=1, required=True)
    salary_type = serializers.ChoiceField(choices=SalaryType.choices, required=True)
    contact_channel = serializers.ChoiceField(choices=ContactChannel.choices, required=True)
    contact_value = serializers.CharField(max_length=255, required=True)

    def validate(self, attrs):
        if attrs['salary_min'] <= 0:
            raise serializers.ValidationError({'salary_min': 'salary_min must be greater than 0.'})
        if attrs['salary_max'] < attrs['salary_min']:
            raise serializers.ValidationError({'salary_max': 'salary_max must be greater than or equal to salary_min.'})
        return attrs


class OfferActionSerializer(serializers.Serializer):
    version = serializers.IntegerField(required=True)
    reason = serializers.ChoiceField(choices=DeclineReason.choices, required=False, allow_blank=True)
    comment = serializers.CharField(required=False, allow_blank=True, default='')

