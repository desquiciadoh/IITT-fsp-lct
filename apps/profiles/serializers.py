"""Profiles app serializers."""

import uuid

from core.enums import ConsentType
from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from matching.models import Company
from rest_framework import serializers

from profiles.models import CandidateContact, CandidateProfile, CandidateSkill, Skill


class CandidateContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = CandidateContact
        fields = ["email", "phone", "telegram"]


class CandidateSkillSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="skill.id", read_only=True)
    name = serializers.CharField(source="skill.name", read_only=True)

    class Meta:
        model = CandidateSkill
        fields = ["id", "name", "source", "level"]


class CandidateLeagueSerializer(serializers.Serializer):
    specialization = serializers.CharField()
    grade = serializers.CharField()
    status = serializers.CharField()
    rating = serializers.IntegerField()
    percentile = serializers.FloatField(allow_null=True)
    strength = serializers.IntegerField(allow_null=True)


class FSPResultSerializer(serializers.Serializer):
    event_id = serializers.CharField()
    event_name = serializers.CharField()
    discipline = serializers.CharField()
    date = serializers.CharField()
    placement = serializers.IntegerField()
    tier = serializers.CharField()
    participants_total = serializers.IntegerField()


class CandidateFSPSerializer(serializers.Serializer):
    participant_id = serializers.CharField()
    sports_rank = serializers.CharField(allow_null=True)
    sync_status = serializers.CharField()
    results = FSPResultSerializer(many=True)


class ConsentsResponseSerializer(serializers.Serializer):
    processing = serializers.BooleanField()
    publication = serializers.BooleanField()
    fsp_sync = serializers.BooleanField()


class CandidateProfileSerializer(serializers.ModelSerializer):
    contacts = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    league = serializers.SerializerMethodField()
    fsp = serializers.SerializerMethodField()
    consents = serializers.SerializerMethodField()

    class Meta:
        model = CandidateProfile
        fields = [
            "public_id",
            "full_name",
            "city",
            "timezone",
            "specialization",
            "claimed_grade",
            "years_experience",
            "roles",
            "work_formats",
            "salary_min",
            "salary_max",
            "salary_type",
            "salary_floor",
            "open_to_offers",
            "blind_mode",
            "blocked_company_ids",
            "about",
            "experience_text",
            "completeness",
            "contacts",
            "skills",
            "league",
            "fsp",
            "consents",
        ]
        read_only_fields = ["public_id", "completeness"]

    @extend_schema_field(CandidateContactSerializer)
    def get_contacts(self, obj):
        # Candidate viewing own profile sees contacts; employers NEVER get this field here
        request = self.context.get("request")
        if request and request.user.is_authenticated and request.user.id == obj.user_id:
            try:
                c = obj.user.candidate_contacts
                return {"email": c.email, "phone": c.phone, "telegram": c.telegram}
            except CandidateContact.DoesNotExist:
                return {"email": obj.user.email, "phone": "", "telegram": ""}
        return None

    @extend_schema_field(CandidateSkillSerializer(many=True))
    def get_skills(self, obj):
        qs = obj.skills.select_related("skill").all()
        return [
            {
                "id": cs.skill.id,
                "name": cs.skill.name,
                "source": cs.source,
                "level": cs.level,
            }
            for cs in qs
        ]

    @extend_schema_field(CandidateLeagueSerializer)
    def get_league(self, obj):
        # Filter by specialization if set, relying on Meta.ordering
        qs = obj.user.league_memberships.all()
        if obj.specialization:
            qs = qs.filter(specialization=obj.specialization)
        lm = qs.filter(status__in=["confirmed", "unconfirmed"]).first()
        if not lm:
            lm = qs.first()
        if lm:
            return {
                "specialization": lm.specialization,
                "grade": lm.grade,
                "status": lm.status,
                "rating": lm.rating,
                "percentile": lm.percentile,
                "strength": lm.strength,
            }
        return None

    @extend_schema_field(CandidateFSPSerializer)
    def get_fsp(self, obj):
        if hasattr(obj.user, "fsp_link"):
            link = obj.user.fsp_link
            results = [
                {
                    "event_id": r.event_id,
                    "event_name": r.event_name,
                    "discipline": r.discipline,
                    "date": str(r.date),
                    "placement": r.placement,
                    "tier": r.tier,
                    "participants_total": r.participants_total,
                }
                for r in obj.user.fsp_results.all()
            ]
            return {
                "participant_id": link.participant_id,
                "sports_rank": link.sports_rank,
                "sync_status": link.sync_status,
                "results": results,
            }
        return None

    @extend_schema_field(ConsentsResponseSerializer)
    def get_consents(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated and request.user.id == obj.user_id:
            consents = {}
            for ct in ConsentType.values:
                latest = obj.user.consents.filter(type=ct).order_by("-created_at").first()
                consents[ct] = latest.granted if latest else False
            return consents
        return None


class CandidateProfileUpdateSerializer(serializers.ModelSerializer):
    contacts = CandidateContactSerializer(required=False)
    skills = serializers.ListField(child=serializers.CharField(), required=False)

    class Meta:
        model = CandidateProfile
        fields = [
            "full_name",
            "city",
            "timezone",
            "specialization",
            "claimed_grade",
            "years_experience",
            "roles",
            "work_formats",
            "salary_min",
            "salary_max",
            "salary_type",
            "salary_floor",
            "open_to_offers",
            "blind_mode",
            "blocked_company_ids",
            "about",
            "experience_text",
            "contacts",
            "skills",
        ]

    def validate_blocked_company_ids(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("blocked_company_ids must be a list of company IDs.")
        valid_uuids = []
        for item in value:
            try:
                valid_uuids.append(uuid.UUID(str(item)))
            except (ValueError, AttributeError):
                raise serializers.ValidationError(f"Invalid company UUID: {item}")

        existing = set(Company.objects.filter(id__in=valid_uuids).values_list("id", flat=True))
        missing = [str(vid) for vid in valid_uuids if vid not in existing]
        if missing:
            raise serializers.ValidationError(f"Companies not found: {', '.join(missing)}")
        return [str(vid) for vid in valid_uuids]

    def validate(self, attrs):
        s_min = (
            attrs["salary_min"]
            if "salary_min" in attrs
            else getattr(self.instance, "salary_min", None)
        )
        s_max = (
            attrs["salary_max"]
            if "salary_max" in attrs
            else getattr(self.instance, "salary_max", None)
        )

        if s_min is not None and s_max is not None and s_min > s_max:
            raise serializers.ValidationError(
                {
                    "salary_min": "salary_min cannot be greater than salary_max",
                }
            )

        s_floor = (
            attrs["salary_floor"]
            if "salary_floor" in attrs
            else getattr(self.instance, "salary_floor", None)
        )
        if s_floor is not None and s_min is not None and s_floor > s_min:
            raise serializers.ValidationError(
                {
                    "salary_floor": "salary_floor cannot be greater than salary_min",
                }
            )

        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        contacts_data = validated_data.pop("contacts", None)
        skills_data = validated_data.pop("skills", None)

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
                skill_id = skill_name.lower().replace(" ", "_").replace(".", "_")
                skill_obj, _ = Skill.objects.get_or_create(
                    id=skill_id, defaults={"name": skill_name}
                )
                CandidateSkill.objects.create(
                    candidate=instance, skill=skill_obj, source=EvidenceSource.DECLARED, level=0.5
                )

        return instance


class ConsentUpdateSerializer(serializers.Serializer):
    processing = serializers.BooleanField(required=False)
    publication = serializers.BooleanField(required=False)
    fsp_sync = serializers.BooleanField(required=False)
    version = serializers.CharField(required=False, default="1.0")


class TaxonomySpecializationSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    topics = serializers.ListField(child=serializers.CharField())


class TaxonomyGradeSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    descriptor = serializers.CharField()
    rating_cut = serializers.IntegerField()


class TaxonomySkillSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    aliases = serializers.ListField(child=serializers.CharField())
    topic = serializers.CharField()


class TaxonomyDeclineReasonSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()


class TaxonomySerializer(serializers.Serializer):
    specializations = TaxonomySpecializationSerializer(many=True)
    grades = TaxonomyGradeSerializer(many=True)
    skills = TaxonomySkillSerializer(many=True)
    decline_reasons = TaxonomyDeclineReasonSerializer(many=True)
