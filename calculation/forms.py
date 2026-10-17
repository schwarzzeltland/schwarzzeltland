from decimal import Decimal

from django import forms
from django.db.models import Sum
from .models import CalculationEducationSession, CalculationIncomeLine, CalculationLine, EventCalculation, SubsidyProfile


class SubsidyProfileForm(forms.ModelForm):
    class Meta:
        model = SubsidyProfile
        exclude = ["organization"]
        widgets = {"registration_deadline": forms.DateInput(attrs={"type": "date"}), "notes": forms.Textarea(attrs={"rows": 3})}
        labels = {
            "name": "Bezeichnung",
            "active": "Aktiv",
            "registration_deadline": "Anmeldefrist",
            "full_rate_days": "Volle Einreichfrist (Tage)",
            "reduced_rate_days": "Zweite Einreichfrist (Tage)",
            "rate_per_person_day": "Zuschuss pro Tag und Person (EUR)",
            "rate_per_person_hour": "Zuschuss pro Bildungs-/QS-Stunde und Person (EUR)",
            "reduced_rate_factor": "Faktor bis zur zweiten Frist",
            "late_rate_factor": "Faktor nach der zweiten Frist",
            "maximum_cost_share": "Maximaler Anteil förderfähiger Kosten",
            "notes": "Hinweise / Grundlage",
        }
        help_texts = {
            "full_rate_days": "Frist ab Veranstaltungsende für den vollen Zuschuss.",
            "reduced_rate_days": "Bis zu dieser Frist wird der reduzierte Zuschuss angesetzt.",
            "reduced_rate_factor": "Beispiel: 0,625 entspricht 62,5 % des vollen Satzes.",
            "late_rate_factor": "Beispiel: 0,5 entspricht 50 % des vollen Satzes.",
            "maximum_cost_share": "Beispiel: 0,4 entspricht maximal 40 % der förderfähigen Kosten.",
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["minimum_eligible_participants"].label = "Mindestanzahl förderfähiger Personen"
        self.fields["minimum_eligible_participants"].help_text = "Bei Unterschreitung ist keine Förderung möglich."
        self.fields["minimum_event_days"].label = "Mindestdauer der Veranstaltung (Tage)"
        self.fields["minimum_event_days"].help_text = "Gilt nicht für Bildung-/QS-Veranstaltungen, wenn die Ausnahme aktiviert ist."
        self.fields["education_qs_exempt_from_minimum_days"].label = "Bildung/QS von Mindestdauer ausnehmen"


class EventCalculationForm(forms.ModelForm):
    class Meta:
        model = EventCalculation
        fields = ["profile", "total_participants", "eligible_participants", "guest_count", "guest_subsidy_per_person", "leader_count", "leader_discount_per_person", "event_days", "is_education_or_qs", "education_hours", "participant_fee", "other_subsidies", "documents_received_at", "actual_eligible_costs_override", "actual_income_manual"]
        widgets = {"documents_received_at": forms.DateInput(attrs={"type": "date"})}
        labels = {
            "profile": "Förderprofil",
            "eligible_participants": "Förderfähige Personen (Anzahl)",
            "total_participants": "Teilnehmende gesamt (Anzahl)",
            "leader_count": "Leiter (Anzahl)",
            "leader_discount_per_person": "Rabatt pro Leiter (EUR)",
            "event_days": "Veranstaltungstage (Tage)",
            "education_hours": "Bildungs-/QS-Stunden (Stunden)",
            "other_subsidies": "Weitere Zuschüsse (EUR)",
            "participant_fee": "Teilnehmerbeitrag förderfähige Person (EUR)",
            "documents_received_at": "Unterlagen eingereicht am",
            "actual_eligible_costs_override": "Förderfähige Ist-Kosten manuell (EUR)",
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["profile"].queryset = SubsidyProfile.objects.filter(organization=organization, active=True)
        self.fields["is_education_or_qs"].label = "Bildungs-/QS-Veranstaltung"
        self.fields["education_hours"].label = "Bildungs-/QS-Stunden (Stunden)"
        self.fields["guest_count"].label = "Gäste (Anzahl)"
        self.fields["guest_subsidy_per_person"].label = "Zuschuss pro Gast (EUR)"
        self.fields["actual_income_manual"].label = "Ist-Einnahmen manuell (EUR)"
        if organization and organization.pro5:
            self.fields.pop("actual_income_manual")
        self.manual_education_hours = Decimal("0")
        if self.instance and self.instance.pk:
            self.manual_education_hours = self.instance.education_sessions.aggregate(total=Sum("hours"))["total"] or Decimal("0")
            self.initial["education_hours"] = self.instance.education_hours + self.manual_education_hours

    def clean_education_hours(self):
        total_education_hours = self.cleaned_data["education_hours"]
        if total_education_hours < self.manual_education_hours:
            raise forms.ValidationError("Die Gesamtstunden dürfen nicht kleiner als die manuell ergänzten Bildungsstunden sein.")
        return total_education_hours - self.manual_education_hours


    


class CalculationLineForm(forms.ModelForm):
    class Meta:
        model = CalculationLine
        fields = ["category", "description", "calculation_mode", "planned_amount", "actual_amount", "eligible"]
        labels = {"category": "Kategorie", "description": "Beschreibung", "calculation_mode": "Berechnung", "planned_amount": "Planbetrag bzw. Satz (EUR)", "actual_amount": "Ist-Betrag bzw. Satz (EUR)", "eligible": "Förderfähig"}
        widgets = {"category": forms.TextInput(attrs={"class": "form-control", "id": "calculation-category-input", "autocomplete": "off"})}


class CalculationIncomeLineForm(forms.ModelForm):
    class Meta:
        model = CalculationIncomeLine
        fields = ["category", "description", "planned_amount", "actual_amount"]
        labels = {"category": "Kategorie", "description": "Beschreibung", "planned_amount": "Plan-Einnahme (EUR)", "actual_amount": "Ist-Einnahme manuell (EUR)"}
        help_texts = {"category": "Bei gleicher Kategorie werden gebuchte Einnahmen aus dem Kassenbuch automatisch als Ist-Wert zugeordnet."}
        widgets = {"category": forms.TextInput(attrs={"class": "form-control", "id": "calculation-income-category-input", "autocomplete": "off"})}


class CalculationEducationSessionForm(forms.ModelForm):
    class Meta:
        model = CalculationEducationSession
        fields = ["topic", "hours"]
        labels = {"topic": "Thema", "hours": "Bildungsstunden"}
