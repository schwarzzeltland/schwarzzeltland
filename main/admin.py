from django.contrib import admin
from nested_admin.nested import NestedTabularInline, NestedModelAdmin

from buildings.models import StockMaterial, Construction
from main.models import Organization, Membership


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
    inlines = [MembershipInline,MaterialInline,ConstructionInLine]
    def get_queryset(self, request):
        return Organization.objects.filter(membership__user=request.user)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    pass
