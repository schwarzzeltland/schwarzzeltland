from django import forms
from decimal import Decimal

from events.models import Trip
from cashbook.models import CashBook, CashBookEntry, ReimbursementRequest
from main.models import Membership


class CashBookForm(forms.ModelForm):
    class Meta:
        model = CashBook
        fields = ["name", "description", "currency", "opening_balance", "responsible", "account_holder", "iban", "bic", "active"]
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

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)
        self.fields["responsible"].required = True
        self.fields["iban"].help_text = "Erforderlich für den SEPA-Export."
        if organization:
            self.fields["responsible"].queryset = Membership.objects.filter(organization=organization, cashier_manager=True).select_related("user")
        else:
            self.fields["responsible"].queryset = Membership.objects.none()


class ReimbursementRequestForm(forms.ModelForm):
    class Meta:
        model = ReimbursementRequest
        fields = ["cashbook", "title", "expense_date", "amount", "description", "attachment", "recipient_name", "recipient_iban", "recipient_bic"]
        widgets = {"expense_date": forms.DateInput(attrs={"type": "date"}), "description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization", None)
        self.requester = kwargs.pop("requester", None)
        super().__init__(*args, **kwargs)
        self.fields["cashbook"].queryset = CashBook.objects.filter(organization=organization, active=True).select_related("responsible") if organization else CashBook.objects.none()
        self.fields["recipient_name"].required = False
        self.fields["recipient_iban"].required = False
        self.fields["recipient_bic"].required = False

    def clean(self):
        cleaned_data = super().clean()
        cashbook = cleaned_data.get("cashbook")
        iban = "".join((cleaned_data.get("recipient_iban") or "").split()).upper()
        bic = "".join((cleaned_data.get("recipient_bic") or "").split()).upper()
        recipient_name = (cleaned_data.get("recipient_name") or "").strip()
        if cashbook and cashbook.iban:
            if not recipient_name:
                self.add_error("recipient_name", "Der Kontoinhaber ist für dieses Kassenbuch erforderlich.")
            if not iban:
                self.add_error("recipient_iban", "Die IBAN ist für dieses Kassenbuch erforderlich.")
            elif not iban.isalnum() or not 15 <= len(iban) <= 34:
                self.add_error("recipient_iban", "Bitte eine gültige IBAN eingeben.")
            if not bic:
                self.add_error("recipient_bic", "Die BIC ist für dieses Kassenbuch erforderlich.")
            elif not bic.isalnum() or len(bic) not in (8, 11):
                self.add_error("recipient_bic", "Bitte eine gültige BIC mit 8 oder 11 Zeichen eingeben.")
        elif not recipient_name and self.requester:
            recipient_name = self.requester.username
        cleaned_data["recipient_name"] = recipient_name
        cleaned_data["recipient_iban"] = iban
        cleaned_data["recipient_bic"] = bic
        return cleaned_data


class ReimbursementReviewForm(forms.Form):
    decision = forms.ChoiceField(label="Prüfergebnis",choices=(("approve", "Genehmigen"), ("reject", "Ablehnen")), widget=forms.RadioSelect)
    review_note = forms.CharField(required=False, label="Prüfvermerk", widget=forms.Textarea(attrs={"rows": 3}))


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


class CashBookCsvUploadForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV-Datei",
        help_text="Die IBAN des Auftragskontos muss mit der IBAN des Kassenbuchs übereinstimmen.",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}),
    )

    def clean_csv_file(self):
        csv_file = self.cleaned_data["csv_file"]
        if csv_file.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Die CSV-Datei darf höchstens 5 MB groß sein.")
        return csv_file


class CashBookCsvRowForm(forms.Form):
    include = forms.BooleanField(required=False, initial=True, label="Importieren")
    booking_date = forms.DateField(
        label="Buchungstag",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    value_date = forms.DateField(
        required=False,
        label="Valutadatum",
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    entry_type = forms.ChoiceField(label="Art", choices=CashBookEntry.TYPE_CHOICES)
    amount = forms.DecimalField(label="Betrag", min_value=Decimal("0.01"), max_digits=12, decimal_places=2)
    title = forms.CharField(label="Buchungstext / Titel", max_length=255)
    counterparty = forms.CharField(required=False, label="Zahlungsbeteiligter", max_length=255)
    purpose = forms.CharField(required=False, label="Verwendungszweck", widget=forms.Textarea(attrs={"rows": 2}))
    balance_after = forms.DecimalField(required=False, label="Saldo nach Buchung", max_digits=14, decimal_places=2)
    creditor_id = forms.CharField(required=False, label="Gläubiger-ID", max_length=255)
    mandate_reference = forms.CharField(required=False, label="Mandatsreferenz", max_length=255)
    trip = forms.ModelChoiceField(
        required=False,
        label="Veranstaltung",
        queryset=Trip.objects.none(),
        empty_label="Keine Veranstaltung",
    )

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)
        if organization:
            self.fields["trip"].queryset = Trip.objects.filter(owner=organization).order_by("-start_date", "name")
