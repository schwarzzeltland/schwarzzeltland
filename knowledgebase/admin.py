from django.contrib import admin
from nested_admin.nested import NestedTabularInline

from knowledgebase.models import Recipe, RecipeIngredient, RecipeStep


class RecipeIngredientInLine(NestedTabularInline):
    model = RecipeIngredient
    extra = 1


class RecipeStepInLine(NestedTabularInline):
    model = RecipeStep
    extra = 1

# Register your models here.
@admin.register(Recipe)
class LocationAdmin(admin.ModelAdmin):
    model = Recipe
    search_fields = ['title']
    inlines = [
        RecipeIngredientInLine,
        RecipeStepInLine,
    ]

