from django.contrib import admin

from matching.models import Company, CompanyMember, Position, Shortlist


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "inn", "trust_level", "created_at")
    list_filter = ("trust_level",)
    search_fields = ("name", "inn", "email_domain")
    ordering = ("-created_at",)


@admin.register(CompanyMember)
class CompanyMemberAdmin(admin.ModelAdmin):
    list_display = ("company", "user")
    search_fields = ("company__name", "user__email")


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "company",
        "title",
        "specialization",
        "salary_min",
        "salary_max",
        "salary_type",
        "status",
        "created_at",
    )
    list_filter = ("specialization", "salary_type", "status", "is_public")
    search_fields = ("title", "company__name")
    ordering = ("-created_at",)


@admin.register(Shortlist)
class ShortlistAdmin(admin.ModelAdmin):
    list_display = ("id", "position", "candidate", "added_at")
    search_fields = ("position__title", "candidate__email")
    ordering = ("-added_at",)
