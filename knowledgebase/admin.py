from django.contrib import admin
from nested_admin.nested import NestedTabularInline

from knowledgebase.models import Recipe, RecipeIngredient, RecipeStep, RecipeTag


class RecipeIngredientInLine(NestedTabularInline):
    model = RecipeIngredient
    extra = 1


class RecipeStepInLine(NestedTabularInline):
    model = RecipeStep
    extra = 1

# Register your models here.
@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    model = Recipe
    search_fields = ['title','owner__name']
    list_display = ['title','owner']
    inlines = [
        RecipeIngredientInLine,
        RecipeStepInLine,
    ]

@admin.register(RecipeTag)
class RecipeTagAdmin(admin.ModelAdmin):
    model = RecipeTag
    search_fields = ['title']