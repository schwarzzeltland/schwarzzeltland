from django.contrib import admin
from nested_admin.nested import NestedTabularInline, NestedModelAdmin

from buildings.models import StockMaterial, Construction
from events.models import EventPlanningChecklistItem
from main.models import Organization, Membership, Message


class MembershipInline(NestedTabularInline):
    model = Membership
    extra = 1
    # autocomplete_fields = ('user',)


class MaterialInline(NestedTabularInline):
    model = StockMaterial
    extra = 1

class ConstructionInLine(NestedTabularInline):
    model = Construction
    extra = 1

@admin.register(Organization)
class OrganizationAdmin(NestedModelAdmin):
    inlines = [MembershipInline]
    search_fields = ['name']


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    search_fields = ['user__username', 'user__first_name', 'user__last_name']
    list_display = ["user", "organization", "admin", "material_manager", "event_manager"]

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    search_fields = ['recipient__name','sender__name','subject','text','created','is_read']
    list_display = ['recipient','sender','subject','text','created','is_read']

@admin.register(EventPlanningChecklistItem)
class EventPlanningChecklistAdmin(admin.ModelAdmin):
    search_fields = ['title','trip__name','organization__name']
    list_display = ['title','trip','organization']