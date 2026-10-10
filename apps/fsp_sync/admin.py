from django.contrib import admin

from fsp_sync.models import FSPLink, FSPResult


@admin.register(FSPLink)
class FSPLinkAdmin(admin.ModelAdmin):
    list_display = (
        "candidate",
        "participant_id",
        "sports_rank",
        "sync_status",
        "last_sync_at",
        "linked_at",
    )
    list_filter = ("sports_rank", "sync_status")
    search_fields = ("candidate__email", "participant_id")
    ordering = ("-linked_at",)


@admin.register(FSPResult)
class FSPResultAdmin(admin.ModelAdmin):
    list_display = ("id", "candidate", "event_name", "discipline", "placement", "tier", "date")
    list_filter = ("discipline", "tier")
    search_fields = ("candidate__email", "event_name")
    ordering = ("-date", "placement")
