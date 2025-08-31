from django.contrib import admin
from nested_admin.nested import NestedTabularInline

from events.models import Trip, TripConstruction, Location, ShoppingListItem, TripMaterial, TripGroup


class TripConstructionInline(NestedTabularInline):
    model = TripConstruction
    extra = 1
class TripMaterialInLine(NestedTabularInline):
    model= TripMaterial
    extra = 1

class TripGroupInLine(NestedTabularInline):
    model= TripGroup
    extra = 1

class TripShoppinglistInLine(NestedTabularInline):
    model= ShoppingListItem
    extra = 1

@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    model = Trip
    search_fields = ['name']
    inlines = [
        TripConstructionInline,
        TripGroupInLine,
        TripMaterialInLine,
        TripShoppinglistInLine
    ]


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    model = Location
    search_fields = ['name']
