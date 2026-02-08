from datetime import timedelta
from time import timezone

from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from django.forms import ModelForm, IntegerField, inlineformset_factory, Form, ModelChoiceField
from django.utils import timezone

from buildings.models import Construction, Material
from events.models import Trip, TripConstruction, Location, TripGroup, TripMaterial, ShoppingListItem, TripVacancy, \
    EventPlanningChecklistItem, ProgrammItem
from knowledgebase.models import Recipe


class TripForm(ModelForm):
    recipient_org_name = forms.CharField(label="Empfänger", max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(TripForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization
        # Eigene Orte
        org_locations = Location.objects.filter(Q(owner=organization)).order_by('name')
        # Setze das Queryset für das `ModelChoiceField`
        self.fields['location'].queryset = org_locations
        self.fields['location'].empty_label = "---------"
        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Eigene Orte", [(c.id, c.name) for c in org_locations]),
        ]
        self.fields['location'].choices = choices
        # Falls Trip schon gespeichert ist → Owner aus der Instanz nehmen
        if not organization and self.instance and self.instance.owner_id:
            organization = self.instance.owner

        if organization:
            # Alle Eventmanager der Organisation + schon ausgewählte Planner
            qs = User.objects.filter(
                membership__organization=organization,
                membership__event_manager=True
            )
            if self.instance.pk:
                qs = (qs | self.instance.planners.all()).distinct()
            self.fields['planners'].queryset = qs
        else:
            self.fields['planners'].queryset = User.objects.none()

    class Meta:
        model = Trip
        fields = '__all__'
        exclude = ['owner']
        widgets = {
            'start_date': forms.DateTimeInput(format='%Y-%m-%dT%H:%M:%S', attrs={
                'type': 'datetime-local',  # HTML5-Attribut für DateTime-Picker
                'class': 'form-control',
            }),
            'end_date': forms.DateTimeInput(format='%Y-%m-%dT%H:%M:%S', attrs={
                'type': 'datetime-local',
                'class': 'form-control',
            }),
        }

    def clean_recipient_org_name(self):
        name = self.cleaned_data.get('recipient_org_name', '')
        name = name.strip()
        if not name:
            return None
        from main.models import Organization
        try:
            return Organization.objects.get(name__iexact=name)
        except Organization.DoesNotExist:
            raise forms.ValidationError("Organisation mit diesem Namen nicht gefunden.")

    def clean(self):
        cleaned_data = super().clean()
        trip_type = cleaned_data.get('type')
        recipient_name = cleaned_data.get('recipient_org_name')
        recipientcode = cleaned_data.get('recipientcode')

        if trip_type == Trip.TYPE_RENTAL:
            if not recipient_name:
                self.add_error('recipient_org_name', 'Empfänger ist bei Material-Verleih erforderlich.')
            if not recipientcode:
                self.add_error('recipientcode', 'Empfängercode ist bei Material-Verleih erforderlich.')

    def save(self, commit=True):
        trip = super().save(commit=False)
        trip_type = self.cleaned_data.get('type')

        # Nur bei Materialverleih (TYPE_RENTAL) das ForeignKey setzen
        if trip_type == Trip.TYPE_RENTAL:
            trip.recipient_org = self.cleaned_data.get('recipient_org_name')
        else:
            trip.recipient_org = None

        if commit:
            trip.save()
            self.save_m2m()
        return trip


class TripConstructionForm(ModelForm):
    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(TripConstructionForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization
        # Konstruktionen der eigenen Organisation
        org_constructions = Construction.objects.filter(owner=organization).order_by('name')
        # Externe Konstruktionen, entweder öffentlich oder ohne zugewiesenen Eigentümer
        external_constructions = Construction.objects.filter(
            Q(public=True) & ~Q(owner=organization) & Q(owner__isnull=False)).order_by('name')
        public_constructions = Construction.objects.filter(Q(owner__isnull=True)).order_by('name')
        # Kombiniere beide Gruppen von Konstruktionen und setze sie als Queryset für das Feld
        combined_queryset = org_constructions | public_constructions | external_constructions

        # Setze das Queryset für das `ModelChoiceField`
        self.fields['construction'].queryset = combined_queryset
        self.fields['construction'].empty_label = "---------"
        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Eigene Konstruktionen", [(c.id, c.name) for c in org_constructions]),
            ("Grundkonstruktionen", [(c.id, c.name) for c in public_constructions]),
            ("Öffentliche Konstruktionen anderer Organisationen",
             [(c.id, f"{c.name} ({c.owner.name})")  # Füge den Organisationsnamen hinzu
              for c in external_constructions]),
        ]
        self.fields['construction'].choices = choices

    class Meta:
        model = TripConstruction
        fields = '__all__'
        exclude = ['owner']


TripConstructionFormSet = inlineformset_factory(
    Trip, TripConstruction, form=TripConstructionForm,
    fields=("construction", "count", "description"),
    extra=1, can_delete=True
)


class LocationForm(ModelForm):
    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(LocationForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization

    class Meta:
        model = Location
        fields = '__all__'
        exclude = ['owner']


class ImportLocationForm(Form):
    location = ModelChoiceField(queryset=Location.objects.none())

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(ImportLocationForm, self).__init__(*args, **kwargs)
        self.organization = organization
        external_location = Location.objects.filter(
            Q(public=True) & ~Q(owner=organization) & Q(owner__isnull=False)).order_by('name')
        public_location = Location.objects.filter(Q(owner__isnull=True)).order_by('name')
        combined_queryset = public_location | external_location

        # Setze das Queryset für das `ModelChoiceField`
        self.fields['location'].queryset = combined_queryset
        self.fields['location'].empty_label = "---------"
        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Öffentliche Orte", [(c.id, c.name) for c in public_location]),
            ("Öffentliche Orte anderer Organisationen",
             [(c.id, f"{c.name} ({c.owner.name})")  # Füge den Organisationsnamen hinzu
              for c in external_location]),
        ]
        self.fields['location'].choices = choices


class TripGroupForm(ModelForm):
    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(TripGroupForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization

    class Meta:
        model = TripGroup
        fields = '__all__'
        exclude = ['owner']


TripGroupFormSet = inlineformset_factory(
    Trip, TripGroup, form=TripGroupForm,
    fields=("name", "count"),
    extra=1, can_delete=True
)


class TripMaterialForm(ModelForm):
    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(TripMaterialForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization
        # Konstruktionen der eigenen Organisation
        org_material = Material.objects.filter(owner=organization).order_by('name')

        # Externe Konstruktionen, entweder öffentlich oder ohne zugewiesenen Eigentümer
        external_material = Material.objects.filter(
            Q(public=True) & ~Q(owner=organization) & Q(owner__isnull=False)).order_by('name')
        public_material = Material.objects.filter(Q(owner__isnull=True)).order_by('name')
        # Kombiniere beide Gruppen von Konstruktionen und setze sie als Queryset für das Feld
        combined_queryset = org_material | public_material | external_material

        # Setze das Queryset für das `ModelChoiceField`
        self.fields['material'].queryset = combined_queryset
        self.fields['material'].empty_label = "---------"
        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Eigenes Material", [(c.id, c.name) for c in org_material]),
            ("Grundmaterial", [(c.id, c.name) for c in public_material]),
            ("Öffentliches Material anderer Organisationen",
             [(c.id, f"{c.name} ({c.owner.name})")  # Füge den Organisationsnamen hinzu
              for c in external_material]),
        ]
        self.fields['material'].choices = choices

    class Meta:
        model = TripMaterial
        fields = '__all__'
        exclude = ['owner', 'reduced_from_stock', 'previous_count']


TripMaterialFormSet = inlineformset_factory(
    Trip, TripMaterial, form=TripMaterialForm,
    fields=("material", "count", "description"),
    extra=1, can_delete=True
)


class ShoppingListItemForm(forms.ModelForm):
    class Meta:
        model = ShoppingListItem
        fields = ["name", "amount", "unit", "product_group"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Artikel"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Menge"}),
            "unit": forms.TextInput(attrs={"class": "form-control", "placeholder": "Einheit"}),
            "product_group": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product_group"].required = False


class TripVacancyForm(forms.ModelForm):
    class Meta:
        model = TripVacancy
        fields = ["name", "arrival", "departure"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Name"}),
            "arrival": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "departure": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
        }


class EventPlanningChecklistItemForm(forms.ModelForm):
    class Meta:
        model = EventPlanningChecklistItem
        fields = ["title", "due_date"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Neuen Punkt hinzufügen..."}),
            "due_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
        }


class ProgrammItemForm(forms.ModelForm):
    # Extra-Felder für Tage und Uhrzeiten
    days = forms.MultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        label="Tage auswählen",
        required=True,
        error_messages={
            'days': {'required': 'Bitte wähle mindestens einen Tag aus.'},
        }
    )

    start_time = forms.TimeField(
        required=True,
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
        label="Startzeit",

        error_messages={
            'start_time': {'required': 'Startzeit darf nicht leer sein.'},
        }
    )
    end_time = forms.TimeField(
        required=True,
        widget=forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
        label="Endzeit",
        error_messages={
            'end_time': {'required': 'Endzeit darf nicht leer sein.'},
        }
    )

    class Meta:
        model = ProgrammItem
        fields = ["name", "short_description", "description", "type","recipe", "visible_for_members"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "short_description": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "type": forms.Select(attrs={"class": "form-select"}),
            "recipe": forms.Select(attrs={"class": "form-select"}),
            "visible_for_members": forms.CheckboxInput(attrs={"class": "form-check-input"}
                                                       )
        }

    def __init__(self, *args, **kwargs):
        trip = kwargs.pop('trip', None)
        super().__init__(*args, **kwargs)
        if trip:
            day_choices = []
            current_day = trip.start_date
            while current_day <= trip.end_date:
                day_choices.append((current_day.isoformat(), current_day.strftime("%a, %d.%m.")))
                current_day += timedelta(days=1)
            self.fields['days'].choices = day_choices
            # Queryset nur auf Rezepte des Trip-Owners beschränken
            self.fields["recipe"].queryset = Recipe.objects.filter(owner=trip.owner)

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        if start_time and timezone.is_naive(start_time):
            cleaned_data["start_time"] = timezone.make_aware(start_time, timezone.get_current_timezone())
        if end_time and timezone.is_naive(end_time):
            cleaned_data["end_time"] = timezone.make_aware(end_time, timezone.get_current_timezone())

        if start_time and end_time and start_time >= end_time:
            self.add_error('start_time', "Die Startzeit muss vor der Endzeit liegen.")
            self.add_error('end_time', "Die Endzeit muss nach der Startzeit liegen.")
        return cleaned_data


class ProgrammItemEditForm(forms.ModelForm):
    class Meta:
        model = ProgrammItem
        fields = [
            'name',
            'short_description',
            'description',
            'type',
            'recipe',
            'visible_for_members',
            'start_time',
            'end_time',
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "short_description": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "type": forms.Select(attrs={"class": "form-select"}),
            "recipe": forms.Select(attrs={"class": "form-select"}),
            "visible_for_members": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "start_time": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M"
            ),
            "end_time": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M"
            ),

        }

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")

        if start_time and timezone.is_naive(start_time):
            cleaned_data["start_time"] = timezone.make_aware(start_time, timezone.get_current_timezone())
        if end_time and timezone.is_naive(end_time):
            cleaned_data["end_time"] = timezone.make_aware(end_time, timezone.get_current_timezone())

        if start_time and end_time:
            if start_time >= end_time:
                self.add_error('start_time', "Die Startzeit muss vor der Endzeit liegen.")
                self.add_error('end_time', "Die Endzeit muss nach der Startzeit liegen.")

            # Prüfen, ob Start und Ende am selben Tag liegen
            if start_time.date() != end_time.date():
                self.add_error('start_time', "Start- und Endzeit müssen am selben Tag liegen.")
                self.add_error('end_time', "Start- und Endzeit müssen am selben Tag liegen.")
        return cleaned_data
    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            # Queryset nur auf Rezepte des Trip-Owners beschränken
            self.fields["recipe"].queryset = Recipe.objects.filter(owner=org)