from django import forms

from events.models import Trip
from cashbook.models import CashBook, CashBookEntry


class CashBookForm(forms.ModelForm):
    class Meta:
        model = CashBook
        fields = ["name", "description", "currency", "opening_balance", "active"]
        labels = {
            "name": "Name",
            "description": "Beschreibung",
            "currency": "Währung",
            "opening_balance": "Startsaldo",
            "active": "Aktiv",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "currency": forms.TextInput(attrs={"maxlength": 3}),
        }


class CashBookEntryForm(forms.ModelForm):
    class Meta:
        model = CashBookEntry
        fields = [
            "entry_type",
            "booking_date",
            "receipt_date",
            "amount",
            "title",
            "category",
            "counterparty",
            "reference",
            "trip",
            "description",
            "attachment",
        ]
        labels = {
            "entry_type": "Art",
            "booking_date": "Buchungsdatum",
            "receipt_date": "Belegdatum",
            "amount": "Betrag",
            "title": "Titel",
            "category": "Kategorie",
            "counterparty": "Zahlungspartner",
            "reference": "Belegnummer / Referenz",
            "trip": "Veranstaltung",
            "description": "Beschreibung",
            "attachment": "Belegdatei",
        }
        widgets = {
            "booking_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "receipt_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "category": forms.TextInput(attrs={
                "class": "form-control",
                "id": "category-input",
                "autocomplete": "off",
                "placeholder": "Kategorie",
            }),
            "trip": forms.Select(attrs={"class": "form-select select2"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)
        self.fields["booking_date"].input_formats = ["%Y-%m-%d"]
        self.fields["receipt_date"].input_formats = ["%Y-%m-%d"]
        if organization:
            self.fields["trip"].queryset = Trip.objects.filter(owner=organization).order_by("-start_date", "name")
        else:
            self.fields["trip"].queryset = Trip.objects.none()
