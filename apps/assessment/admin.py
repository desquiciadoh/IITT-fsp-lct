from django.contrib import admin

from assessment.models import AssessmentItem, AssessmentSession, ItemFamily, LeagueMembership


@admin.register(ItemFamily)
class ItemFamilyAdmin(admin.ModelAdmin):
    list_display = ("id", "topic", "format", "a", "b", "c")
    list_filter = ("format",)
    search_fields = ("id", "topic")


@admin.register(AssessmentSession)
class AssessmentSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "candidate",
        "specialization",
        "claimed_grade",
        "status",
        "started_at",
        "finished_at",
    )
    list_filter = ("specialization", "claimed_grade", "status")
    search_fields = ("candidate__email",)
    ordering = ("-started_at",)
    readonly_fields = (
        "id",
        "candidate",
        "specialization",
        "claimed_grade",
        "status",
        "started_at",
        "finished_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AssessmentItem)
class AssessmentItemAdmin(admin.ModelAdmin):
    list_display = ("id", "assessment", "seq", "family", "correct")
    exclude = ("key", "fingerprint", "seed")
    readonly_fields = ("id", "assessment", "seq", "family", "view", "answer", "correct")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LeagueMembership)
class LeagueMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "candidate",
        "specialization",
        "grade",
        "status",
        "strength",
        "base_strength",
        "fsp_boost",
        "confirmed_at",
    )
    list_filter = ("specialization", "grade", "status")
    search_fields = ("candidate__email",)
    ordering = ("-confirmed_at",)
    readonly_fields = (
        "id",
        "candidate",
        "specialization",
        "grade",
        "status",
        "strength",
        "base_strength",
        "fsp_boost",
        "confirmed_at",
        "next_attempt_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
