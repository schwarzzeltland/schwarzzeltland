from django.contrib import admin
from nested_admin.nested import NestedTabularInline

from events.models import Trip, TripConstruction, Location


class TripConstructionInline(NestedTabularInline):
    model = TripConstruction
    extra = 1

@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    model = Trip
    search_fields = ['name']
    inlines = [TripConstructionInline]
    extra = 1

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    model = Location
    search_fields = ['name']
