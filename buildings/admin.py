from django.contrib import admin
from nested_admin.nested import NestedTabularInline

from buildings.models import Material, Construction, ConstructionMaterial


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
    search_fields = ['name']
