"""Outreach app serializers."""
from rest_framework import serializers
from outreach.models import Offer, ContactGrant
from profiles.models import CandidateProfile
from matching.serializers import CompanySerializer
from core.enums import ContactChannel, DeclineReason, OfferStatus, SalaryType
from core.services import ContactAccessService


class OfferSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    candidate_public_id = serializers.CharField(write_only=True, required=False)
    candidate_contacts = serializers.SerializerMethodField()
    why_you = serializers.JSONField(read_only=True)

    class Meta:
        model = Offer
        fields = [
            'id',
            'company',
            'position',
            'candidate_public_id',
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
            'why_you',
            'version',
            'candidate_contacts',
            'expires_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'status', 'version', 'expires_at', 'created_at', 'updated_at']

    def validate(self, attrs):
        salary_min = attrs.get('salary_min') or (self.instance.salary_min if self.instance else None)
        salary_max = attrs.get('salary_max') or (self.instance.salary_max if self.instance else None)

        if salary_min is not None and salary_min <= 0:
            raise serializers.ValidationError({'salary_min': 'salary_min must be greater than 0.'})
        if salary_min is not None and salary_max is not None and salary_max < salary_min:
            raise serializers.ValidationError({'salary_max': 'salary_max must be greater than or equal to salary_min.'})
        return attrs

    def get_candidate_contacts(self, obj):
        # Contacts are returned ONLY if offer is accepted and user has grant
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

        # If employer is viewing: check if contact grant exists
        if obj.status == OfferStatus.ACCEPTED:
            try:
                contacts = ContactAccessService.get_contacts(
                    company_id=obj.company_id,
                    candidate_id=obj.candidate_id,
                    actor_id=request.user.id
                )
                return {
                    'full_name': contacts.full_name,
                    'email': contacts.email,
                    'phone': contacts.phone,
                    'telegram': contacts.telegram,
                }
            except Exception:
                return None
        return None
