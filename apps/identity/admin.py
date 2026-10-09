from django.contrib import admin

from identity.models import AuditLog, Consent, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'role', 'is_staff', 'is_active', 'is_demo', 'created_at')
    list_filter = ('role', 'is_staff', 'is_active', 'is_demo')
    search_fields = ('email',)
    ordering = ('-created_at',)


@admin.register(Consent)
class ConsentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'type', 'granted', 'version', 'created_at')
    list_filter = ('type', 'granted')
    search_fields = ('user__email',)
    ordering = ('-created_at',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'actor', 'action', 'target_type', 'target_id', 'created_at')
    list_filter = ('action', 'target_type')
    search_fields = ('actor__email', 'target_id')
    readonly_fields = ('id', 'actor', 'action', 'target_type', 'target_id', 'meta', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
