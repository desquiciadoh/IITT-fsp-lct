"""Profiles app serializers."""
from rest_framework import serializers
from profiles.models import CandidateProfile, CandidateContact, Skill, CandidateSkill
from identity.models import Consent
from core.enums import Specialization, Grade, WorkFormat, SalaryType, ConsentType


class CandidateContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateContact
        fields = ['email', 'phone', 'telegram']


class CandidateSkillSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='skill.id', read_only=True)
    name = serializers.CharField(source='skill.name', read_only=True)

    class Meta:
        model = CandidateSkill
        fields = ['id', 'name', 'source', 'level']


class CandidateProfileSerializer(serializers.ModelSerializer):
    contacts = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    league = serializers.SerializerMethodField()
    fsp = serializers.SerializerMethodField()
    consents = serializers.SerializerMethodField()

    class Meta:
        model = CandidateProfile
        fields = [
            'public_id',
            'full_name',
            'city',
            'timezone',
            'specialization',
            'claimed_grade',
            'years_experience',
            'roles',
            'work_formats',
            'salary_min',
            'salary_max',
            'salary_type',
            'salary_floor',
            'open_to_offers',
            'blind_mode',
            'blocked_company_ids',
            'about',
            'experience_text',
            'completeness',
            'contacts',
            'skills',
            'league',
            'fsp',
            'consents',
        ]
        read_only_fields = ['public_id', 'completeness']

    def get_contacts(self, obj):
        # Candidate viewing own profile sees contacts; employers NEVER get this field here
        request = self.context.get('request')
        if request and request.user.is_authenticated and request.user.id == obj.user_id:
            try:
                c = obj.user.candidate_contacts
                return {'email': c.email, 'phone': c.phone, 'telegram': c.telegram}
            except CandidateContact.DoesNotExist:
                return {'email': obj.user.email, 'phone': '', 'telegram': ''}
        return None

    def get_skills(self, obj):
        qs = obj.skills.select_related('skill').all()
        return [
            {
                'id': cs.skill.id,
                'name': cs.skill.name,
                'source': cs.source,
                'level': cs.level,
            }
            for cs in qs
        ]

    def get_league(self, obj):
        # Latest confirmed or unconfirmed league membership
        lm = obj.user.league_memberships.filter(status__in=['confirmed', 'unconfirmed']).first()
        if not lm:
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
        if hasattr(obj.user, 'fsp_link'):
            link = obj.user.fsp_link
            results = [
                {
                    'event_id': r.event_id,
                    'event_name': r.event_name,
                    'discipline': r.discipline,
                    'date': str(r.date),
                    'placement': r.placement,
                    'tier': r.tier,
                    'participants_total': r.participants_total,
                }
                for r in obj.user.fsp_results.all()
            ]
            return {
                'participant_id': link.participant_id,
                'sports_rank': link.sports_rank,
                'sync_status': link.sync_status,
                'results': results,
            }
        return None

    def get_consents(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated and request.user.id == obj.user_id:
            consents = {}
            for ct in ConsentType.values:
                latest = obj.user.consents.filter(type=ct).order_by('-created_at').first()
                consents[ct] = latest.granted if latest else False
            return consents
        return None


class CandidateProfileUpdateSerializer(serializers.ModelSerializer):
    contacts = CandidateContactSerializer(required=False)
    skills = serializers.ListField(child=serializers.CharField(), required=False)

    class Meta:
        model = CandidateProfile
        fields = [
            'full_name',
            'city',
            'timezone',
            'specialization',
            'claimed_grade',
            'years_experience',
            'roles',
            'work_formats',
            'salary_min',
            'salary_max',
            'salary_type',
            'salary_floor',
            'open_to_offers',
            'blind_mode',
            'blocked_company_ids',
            'about',
            'experience_text',
            'contacts',
            'skills',
        ]

    def update(self, instance, validated_data):
        contacts_data = validated_data.pop('contacts', None)
        skills_data = validated_data.pop('skills', None)

        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()

        if contacts_data:
            contact, _ = CandidateContact.objects.get_or_create(user=instance.user)
            for k, v in contacts_data.items():
                setattr(contact, k, v)
            contact.save()

        if skills_data is not None:
            # Sync declared skills
            from core.enums import EvidenceSource
            instance.skills.filter(source=EvidenceSource.DECLARED).delete()
            for skill_name in skills_data:
                skill_id = skill_name.lower().replace(' ', '_').replace('.', '_')
                skill_obj, _ = Skill.objects.get_or_create(id=skill_id, defaults={'name': skill_name})
                CandidateSkill.objects.create(
                    candidate=instance,
                    skill=skill_obj,
                    source=EvidenceSource.DECLARED,
                    level=0.5
                )

        return instance
