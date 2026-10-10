from django.contrib import admin

from profiles.models import CandidateProfile, CandidateSkill, Skill


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "public_id",
        "full_name",
        "specialization",
        "claimed_grade",
        "open_to_offers",
        "updated_at",
    )
    list_filter = ("specialization", "claimed_grade", "open_to_offers")
    search_fields = ("full_name", "public_id", "user__email")
    ordering = ("-updated_at",)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "topic")
    list_filter = ("topic",)
    search_fields = ("id", "name", "topic")


@admin.register(CandidateSkill)
class CandidateSkillAdmin(admin.ModelAdmin):
    list_display = ("id", "candidate", "skill", "source", "level", "updated_at")
    list_filter = ("source",)
    search_fields = ("candidate__user__email", "skill__name")
