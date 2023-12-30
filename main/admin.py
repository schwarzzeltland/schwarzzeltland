from django.contrib import admin
from nested_admin.nested import NestedTabularInline, NestedModelAdmin

from main.models import Organization, Membership


class MembershipInline(NestedTabularInline):
    model = Membership
    extra = 1
    # autocomplete_fields = ('user',)


@admin.register(Organization)
class OrganizationAdmin(NestedModelAdmin):
    inlines = [MembershipInline]

    def get_queryset(self, request):
        return Organization.objects.filter(membership__user=request.user)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    pass