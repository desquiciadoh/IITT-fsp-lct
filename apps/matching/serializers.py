"""Matching app serializers."""

from core.enums import ApplicationStatus
from core.pagination import PaginationQuerySerializer
from drf_spectacular.utils import extend_schema_field
from profiles.models import CandidateProfile
from rest_framework import serializers

from matching.antifraud import compute_company_trust_level, validate_inn
from matching.models import (
    Application,
    Company,
    MicroTask,
    MicroTaskDrop,
    Position,
)


class CompanySearchQuerySerializer(PaginationQuerySerializer):
    search = serializers.CharField(min_length=2, required=True, trim_whitespace=True)


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "inn",
            "website",
            "email_domain",
            "business_domain",
            "description",
            "contact_email",
            "trust_level",
            "created_at",
        ]
        read_only_fields = ["id", "trust_level", "created_at"]

    def validate_inn(self, value):
        if value:
            clean_inn = value.strip()
            if not validate_inn(clean_inn):
                raise serializers.ValidationError("Invalid Russian INN checksum (must be valid 10 or 12 digits).")
            return clean_inn
        return value

    def create(self, validated_data):
        inn = validated_data.get("inn", "")
        email_domain = validated_data.get("email_domain", "") or validated_data.get("contact_email", "")
        validated_data["trust_level"] = compute_company_trust_level(inn, email_domain)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        inn = validated_data.get("inn", instance.inn)
        email_domain = (
            validated_data.get("email_domain")
            or validated_data.get("contact_email")
            or instance.email_domain
            or instance.contact_email
        )
        validated_data["trust_level"] = compute_company_trust_level(inn, email_domain)
        return super().update(instance, validated_data)


class CompanyMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name"]


class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = [
            "id",
            "company",
            "title",
            "specialization",
            "grades",
            "must_skills",
            "nice_skills",
            "work_formats",
            "location",
            "salary_min",
            "salary_max",
            "salary_type",
            "team_context",
            "description",
            "allow_adjacent",
            "is_public",
            "status",
            "created_at",
        ]
        # company comes from the caller's membership, never from input (B9)
        read_only_fields = ["id", "company", "created_at"]

    def validate(self, attrs):
        salary_min = (
            attrs["salary_min"]
            if "salary_min" in attrs
            else (self.instance.salary_min if self.instance else None)
        )
        salary_max = (
            attrs["salary_max"]
            if "salary_max" in attrs
            else (self.instance.salary_max if self.instance else None)
        )

        if salary_min is not None and salary_min <= 0:
            raise serializers.ValidationError({"salary_min": "salary_min must be greater than 0."})
        if salary_min is not None and salary_max is not None and salary_max < salary_min:
            raise serializers.ValidationError(
                {"salary_max": "salary_max must be greater than or equal to salary_min."}
            )
        if salary_min is not None and salary_max is not None and salary_max > 2 * salary_min:
            raise serializers.ValidationError(
                {"salary_max": "salary_max / salary_min ratio cannot exceed 2.0."}
            )
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
            "public_id",
            "display_name",
            "city",
            "work_formats",
            "salary_min",
            "salary_max",
            "salary_type",
            "league",
            "fsp",
            "skills",
            "verified_topics",
            "last_active_at",
        ]

    @extend_schema_field(serializers.CharField())
    def get_display_name(self, obj):
        if obj.blind_mode:
            return f"Кандидат {obj.public_id}"
        return obj.full_name or f"Кандидат {obj.public_id}"

    @extend_schema_field(TalentLeagueSerializer)
    def get_league(self, obj):
        user = obj.user
        if (
            hasattr(user, "_prefetched_objects_cache")
            and "league_memberships" in user._prefetched_objects_cache
        ):
            memberships = list(user.league_memberships.all())
            if obj.specialization:
                matching = [lm for lm in memberships if lm.specialization == obj.specialization]
                lm = matching[0] if matching else (memberships[0] if memberships else None)
            else:
                lm = memberships[0] if memberships else None
        else:
            qs = user.league_memberships.all()
            if obj.specialization:
                qs = qs.filter(specialization=obj.specialization)
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

    @extend_schema_field(TalentFSPSerializer)
    def get_fsp(self, obj):
        user = obj.user
        fsp_link = getattr(user, "fsp_link", None)
        has_link = fsp_link is not None
        if (
            hasattr(user, "_prefetched_objects_cache")
            and "fsp_results" in user._prefetched_objects_cache
        ):
            results_count = len(user.fsp_results.all())
        else:
            results_count = user.fsp_results.count()

        return {
            "linked": has_link,
            "results_count": results_count,
            "sports_rank": fsp_link.sports_rank if has_link and fsp_link else None,
        }

    @extend_schema_field(TalentSkillSerializer(many=True))
    def get_skills(self, obj):
        if (
            hasattr(obj, "_prefetched_objects_cache")
            and "skills" in obj._prefetched_objects_cache
        ):
            skills_qs = obj.skills.all()
        else:
            skills_qs = obj.skills.select_related("skill").all()

        return [
            {"id": cs.skill_id, "name": cs.skill.name, "source": cs.source}
            for cs in skills_qs[:8]
        ]

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_verified_topics(self, obj):
        if getattr(obj, "_verified_topics", None) is not None:
            return obj._verified_topics

        from assessment.models import AssessmentItem
        from core.enums import AssessmentStatus

        topics = list(
            AssessmentItem.objects.filter(
                assessment__candidate=obj.user,
                assessment__status=AssessmentStatus.FINISHED,
                correct=True,
            )
            .values_list("family__topic", flat=True)
            .distinct()
        )
        return [t for t in topics if t]


class JdParseRequestSerializer(serializers.Serializer):
    text = serializers.CharField(min_length=10, required=False)
    raw_text = serializers.CharField(min_length=10, required=False)

    def validate(self, attrs):
        text = attrs.get("text") or attrs.get("raw_text")
        if not text:
            raise serializers.ValidationError({"text": "This field is required."})
        attrs["text"] = text
        return attrs


class JdDraftSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True, default="")
    specialization = serializers.CharField(required=False, allow_blank=True, default="backend")
    grades = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    must_skills = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    nice_skills = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    work_formats = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    location = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="")
    salary_min = serializers.IntegerField(required=False, allow_null=True, default=None)
    salary_max = serializers.IntegerField(required=False, allow_null=True, default=None)
    salary_type = serializers.CharField(required=False, allow_blank=True, default="gross")
    team_context = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=""
    )
    description = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=""
    )


class JdParseBlueprintItemSerializer(serializers.Serializer):
    topic = serializers.CharField()
    weight = serializers.FloatField()


class JdParseResultSerializer(serializers.Serializer):
    draft = JdDraftSerializer()
    unknown_terms = serializers.ListField(child=serializers.CharField(), default=list)
    blueprint = JdParseBlueprintItemSerializer(many=True, default=list)
    source = serializers.CharField(default="rules")


class CompanyPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "trust_level", "website", "description"]


class VacancySerializer(serializers.ModelSerializer):
    company = CompanyPublicSerializer(read_only=True)
    salary = serializers.SerializerMethodField()

    class Meta:
        model = Position
        fields = [
            "id",
            "title",
            "company",
            "specialization",
            "grades",
            "must_skills",
            "nice_skills",
            "work_formats",
            "location",
            "salary_min",
            "salary_max",
            "salary_type",
            "salary",
            "team_context",
            "description",
            "created_at",
        ]

    @extend_schema_field(serializers.DictField())
    def get_salary(self, obj):
        return {
            "min": obj.salary_min,
            "max": obj.salary_max,
            "type": obj.salary_type,
            "currency": "RUB",
        }


class ApplicationCreateSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class ApplicationCandidateSerializer(serializers.ModelSerializer):
    position = VacancySerializer(read_only=True)

    class Meta:
        model = Application
        fields = ["id", "position", "status", "note", "created_at", "updated_at"]


class ApplicationEmployerSerializer(serializers.ModelSerializer):
    candidate = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = ["id", "candidate", "status", "note", "created_at", "updated_at"]

    @extend_schema_field(TalentShortSerializer)
    def get_candidate(self, obj):
        profile = getattr(obj.candidate, "candidate_profile", None)
        if profile:
            return TalentShortSerializer(profile).data
        return None


class ApplicationStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ApplicationStatus.choices)


# ---------------------------------------------------------------------------
# Task BE-18: Micro-Tasks Serializers
# ---------------------------------------------------------------------------


class MicroTaskSerializer(serializers.ModelSerializer):
    company = CompanyPublicSerializer(read_only=True)

    class Meta:
        model = MicroTask
        fields = [
            "id",
            "company",
            "title",
            "specialization",
            "grades",
            "format",
            "family_id",
            "prompt_md",
            "deadline",
            "created_at",
        ]


class MicroTaskCreateSerializer(serializers.ModelSerializer):
    key = serializers.JSONField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Server-side secret grading key. Never returned in responses.",
    )

    class Meta:
        model = MicroTask
        fields = [
            "id",
            "title",
            "specialization",
            "grades",
            "format",
            "family_id",
            "prompt_md",
            "key",
            "deadline",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class MicroTaskDropCandidateSerializer(serializers.ModelSerializer):
    task = MicroTaskSerializer(read_only=True)

    class Meta:
        model = MicroTaskDrop
        fields = [
            "id",
            "task",
            "dropped_at",
            "answer",
            "score",
            "employer_rating",
            "submitted_at",
        ]


class MicroTaskSubmitSerializer(serializers.Serializer):
    answer = serializers.JSONField(help_text="Candidate solution or approach")


class MicroTaskRateSerializer(serializers.Serializer):
    employer_rating = serializers.IntegerField(min_value=1, max_value=5)


class MicroTaskSubmissionEmployerSerializer(serializers.ModelSerializer):
    candidate = serializers.SerializerMethodField()

    class Meta:
        model = MicroTaskDrop
        fields = [
            "id",
            "task_id",
            "candidate",
            "dropped_at",
            "answer",
            "score",
            "employer_rating",
            "submitted_at",
        ]

    @extend_schema_field(TalentShortSerializer)
    def get_candidate(self, obj):
        profile = getattr(obj.candidate, "candidate_profile", None)
        if profile:
            return TalentShortSerializer(profile).data
        return None


