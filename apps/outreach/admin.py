from django.contrib import admin

from outreach.models import ContactGrant, Offer, OfferEvent


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ('id', 'company', 'position', 'candidate', 'status', 'salary_min', 'salary_max', 'salary_type', 'version', 'created_at')
    list_filter = ('status', 'salary_type')
    search_fields = ('candidate__email', 'position__title', 'company__name')
    ordering = ('-created_at',)


@admin.register(OfferEvent)
class OfferEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'offer', 'from_status', 'to_status', 'actor', 'created_at')
    list_filter = ('from_status', 'to_status')
    readonly_fields = ('id', 'offer', 'from_status', 'to_status', 'actor', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ContactGrant)
class ContactGrantAdmin(admin.ModelAdmin):
    list_display = ('id', 'company', 'candidate', 'source', 'source_id', 'granted_at', 'revoked_at')
    list_filter = ('source',)
    search_fields = ('candidate__email', 'company__name')
    readonly_fields = ('id', 'company', 'candidate', 'source', 'source_id', 'granted_at', 'revoked_at')
    ordering = ('-granted_at',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
