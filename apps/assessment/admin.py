from django.contrib import admin

from assessment.models import AssessmentItem, AssessmentSession, ItemFamily, LeagueMembership


@admin.register(ItemFamily)
class ItemFamilyAdmin(admin.ModelAdmin):
    list_display = ('id', 'topic', 'format', 'a', 'b', 'c')
    list_filter = ('format',)
    search_fields = ('id', 'topic')


@admin.register(AssessmentSession)
class AssessmentSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate', 'specialization', 'claimed_grade', 'status', 'started_at', 'finished_at')
    list_filter = ('specialization', 'claimed_grade', 'status')
    search_fields = ('candidate__email',)
    ordering = ('-started_at',)


@admin.register(AssessmentItem)
class AssessmentItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'assessment', 'seq', 'family', 'correct')
    readonly_fields = ('id', 'assessment', 'seq', 'family', 'seed', 'view', 'key', 'fingerprint', 'answer', 'correct')


@admin.register(LeagueMembership)
class LeagueMembershipAdmin(admin.ModelAdmin):
    list_display = ('id', 'candidate', 'specialization', 'grade', 'status', 'strength', 'base_strength', 'fsp_boost', 'confirmed_at')
    list_filter = ('specialization', 'grade', 'status')
    search_fields = ('candidate__email',)
    ordering = ('-confirmed_at',)
