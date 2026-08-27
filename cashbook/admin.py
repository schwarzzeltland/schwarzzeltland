from django.contrib import admin
from nested_admin.nested import NestedTabularInline

from cashbook.models import (
    AdvanceBudget, CashBook, CashBookAuditLog, CashBookEntry, EventExpense,
    ReimbursementRequest,
)


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
    list_display = ["title", "cashbook", "entry_type", "booking_date", "amount", "reconciliation_status", "source", "trip", "category", "created_by"]
    list_filter = ["reconciliation_status", "source", "entry_type", "booking_date", "cashbook__organization", "cashbook"]
    readonly_fields = ["bank_import_fingerprint", "bank_reconciled_at"]


@admin.register(ReimbursementRequest)
class ReimbursementRequestAdmin(admin.ModelAdmin):
    list_display = ["title", "cashbook", "requester", "amount", "status", "created_at", "reviewed_by"]
    list_filter = ["status", "cashbook__organization", "cashbook"]
    search_fields = ["title", "requester__username", "recipient_name", "recipient_iban"]


class EventExpenseInline(admin.TabularInline):
    model = EventExpense
    extra = 0
    fields = ["expense_date", "title", "category", "counterparty", "amount", "status", "attachment"]
    readonly_fields = ["created_by", "reviewed_by", "reviewed_at", "cashbook_entry", "created_at"]
    show_change_link = True


@admin.register(AdvanceBudget)
class AdvanceBudgetAdmin(admin.ModelAdmin):
    list_display = ["name", "trip", "cashbook", "assigned_to", "amount", "spent_amount", "remaining_amount", "settled_at"]
    list_filter = ["settled_at", "cashbook__organization", "cashbook", "trip"]
    search_fields = ["name", "trip__name", "cashbook__name", "assigned_to__user__username", "assigned_to__user__first_name", "assigned_to__user__last_name"]
    readonly_fields = ["created_at"]
    inlines = [EventExpenseInline]


@admin.register(EventExpense)
class EventExpenseAdmin(admin.ModelAdmin):
    list_display = ["title", "trip", "payment_source", "expense_date", "amount", "category", "counterparty", "status", "created_by"]
    list_filter = ["status", "expense_date", "trip__owner", "trip", "cashbook", "advance_budget"]
    search_fields = ["title", "category", "counterparty", "reference", "description", "trip__name", "created_by__username"]
    readonly_fields = ["created_at", "reviewed_at"]

    @admin.display(description="Zahlungsquelle")
    def payment_source(self, expense):
        return expense.cashbook or expense.advance_budget or "-"


@admin.register(CashBookAuditLog)
class CashBookAuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "organization", "actor", "action", "target_type", "label"]
    list_filter = ["action", "target_type", "organization", "created_at"]
    search_fields = ["label", "actor__username", "cashbook__name"]
    readonly_fields = ["organization", "cashbook", "entry", "actor", "target_type", "action", "label", "changes", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
