from django.contrib import admin
from nested_admin.nested import NestedTabularInline

from cashbook.models import CashBook, CashBookEntry


class CashBookEntryInline(NestedTabularInline):
    model = CashBookEntry
    extra = 0
    fields = ("booking_date", "entry_type", "title", "amount", "trip", "category", "attachment")


@admin.register(CashBook)
class CashBookAdmin(admin.ModelAdmin):
    inlines = [CashBookEntryInline]
    search_fields = ["name", "organization__name", "description"]
    list_display = ["name", "organization", "currency", "opening_balance", "active", "created_at", "updated_at"]
    list_filter = ["active", "currency", "organization"]


@admin.register(CashBookEntry)
class CashBookEntryAdmin(admin.ModelAdmin):
    search_fields = ["title", "cashbook__name", "cashbook__organization__name", "category", "counterparty", "reference"]
    list_display = ["title", "cashbook", "entry_type", "booking_date", "amount", "trip", "category", "created_by"]
    list_filter = ["entry_type", "booking_date", "cashbook__organization", "cashbook"]
