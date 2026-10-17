from django.contrib import admin

from .models import (
    CalculationEducationSession,
    CalculationIncomeLine,
    CalculationLine,
    EventCalculation,
    SubsidyProfile,
)


class CalculationLineInline(admin.TabularInline):
    model = CalculationLine
    extra = 0
    fields = ("category", "description", "calculation_mode", "planned_amount", "actual_amount", "eligible")


class CalculationEducationSessionInline(admin.TabularInline):
    model = CalculationEducationSession
    extra = 0
    fields = ("topic", "hours")


@admin.register(SubsidyProfile)
class SubsidyProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "active", "minimum_eligible_participants", "minimum_event_days", "maximum_cost_share")
    list_filter = ("active", "organization")
    search_fields = ("name", "organization__name")


@admin.register(EventCalculation)
class EventCalculationAdmin(admin.ModelAdmin):
    list_display = ("trip", "profile", "eligible_participants", "total_participants", "event_days", "is_education_or_qs")
    list_filter = ("profile", "is_education_or_qs", "trip__owner")
    search_fields = ("trip__name", "trip__owner__name", "profile__name")
    raw_id_fields = ("trip", "profile")
    inlines = (CalculationLineInline, CalculationEducationSessionInline)


@admin.register(CalculationLine)
class CalculationLineAdmin(admin.ModelAdmin):
    list_display = ("calculation", "category", "description", "calculation_mode", "planned_amount", "actual_amount", "eligible")
    list_filter = ("calculation_mode", "eligible", "calculation__trip__owner")
    search_fields = ("category", "description", "calculation__trip__name")


@admin.register(CalculationIncomeLine)
class CalculationIncomeLineAdmin(admin.ModelAdmin):
    list_display = ("category", "description", "calculation", "planned_amount")
    list_filter = ("calculation__trip__owner",)
    search_fields = ("category", "description", "calculation__trip__name")


@admin.register(CalculationEducationSession)
class CalculationEducationSessionAdmin(admin.ModelAdmin):
    list_display = ("topic", "hours", "calculation")
    search_fields = ("topic", "calculation__trip__name")

