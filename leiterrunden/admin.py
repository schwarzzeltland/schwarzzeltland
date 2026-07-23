from django.contrib import admin

from leiterrunden.models import MeetingMinutes, MeetingMinutesAcceptance, MeetingMinutesItem


class MeetingMinutesItemInline(admin.TabularInline):
    model = MeetingMinutesItem
    extra = 0


@admin.register(MeetingMinutes)
class MeetingMinutesAdmin(admin.ModelAdmin):
    list_display = ["title", "organization", "meeting_date", "published", "created_by", "updated_at"]
    list_filter = ["organization", "published"]
    search_fields = ["title", "introduction", "organization__name"]
    inlines = [MeetingMinutesItemInline]


admin.site.register(MeetingMinutesAcceptance)
