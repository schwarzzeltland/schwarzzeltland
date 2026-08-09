from django.contrib import admin
from nested_admin.nested import NestedTabularInline

from buildings.models import Material, Construction, ConstructionMaterial, StockMaterial, MaterialContainer


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    save_as = True
    search_fields = ['name']
    pass


class ConstructionMaterialInline(NestedTabularInline):
    model = ConstructionMaterial
    extra = 5


@admin.register(Construction)
class ConstructionAdmin(admin.ModelAdmin):
    inlines = [ConstructionMaterialInline]
    search_fields = ['name','owner__name']

@admin.register(StockMaterial)
class StockMaterialAdmin(admin.ModelAdmin):
    search_fields = ['material__name','organization__name']


@admin.register(MaterialContainer)
class MaterialContainerAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "storage_place", "scan_code"]
    search_fields = ["name", "organization__name", "storage_place"]
