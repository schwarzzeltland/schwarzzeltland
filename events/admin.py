from django.contrib import admin
from nested_admin.nested import NestedTabularInline

from events.models import Trip, TripConstruction


class TripConstructionInline(NestedTabularInline):
    model = TripConstruction
    extra = 1

@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    model = Trip
    inlines = [TripConstructionInline]
    extra = 1
