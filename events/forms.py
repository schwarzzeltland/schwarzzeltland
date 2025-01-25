from time import timezone

from django import forms
from django.db.models import Q
from django.forms import ModelForm, IntegerField, inlineformset_factory, Form, ModelChoiceField

from buildings.models import Construction
from events.models import Trip, TripConstruction, Location


class TripForm(ModelForm):

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(TripForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization
        # Eigene Orte
        org_locations = Location.objects.filter(Q(owner=organization))
        # Setze das Queryset für das `ModelChoiceField`
        self.fields['location'].queryset = org_locations
        self.fields['location'].empty_label = "---------"
        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Eigene Orte", [(c.id, c.name) for c in org_locations]),
        ]
        self.fields['location'].choices = choices
        self.fields['tn_count'].disabled = True

    class Meta:
        model = Trip
        fields = '__all__'
        exclude = ['owner']
        widgets = {
            'start_date': forms.DateTimeInput(attrs={
                'type': 'datetime-local',  # HTML5-Attribut für DateTime-Picker
                'class': 'form-control',
            }),
            'end_date': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control',
            }),
        }


class TripConstructionForm(ModelForm):
    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(TripConstructionForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization
        # Materialien gruppieren
        org_constructions = Construction.objects.filter(owner=organization).order_by('name')
        external_constructions = Construction.objects.filter(
            Q(owner__isnull=True) | Q(public=True) & ~Q(owner=organization)
        ).order_by('name')

        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Eigene Konstruktionen", [(con.id, con.name) for con in org_constructions]),
            ("Öffentliche Konstruktionen", [(con.id, con.name) for con in external_constructions]),
        ]
        self.fields['construction'].choices = choices

    class Meta:
        model = TripConstruction
        fields = '__all__'
        exclude = ['owner']


TripConstructionFormSet = inlineformset_factory(
    Trip, TripConstruction, form=TripConstructionForm,
    fields=("construction", "count","description"),
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
        # Externe Orte, entweder öffentlich oder ohne zugewiesenen Eigentümer
        external_locations = Location.objects.filter(
            Q(owner__isnull=True) | Q(public=True) & ~Q(owner=organization)
        )
        # Setze das Queryset für das `ModelChoiceField`
        self.fields['location'].queryset = external_locations
        self.fields['location'].empty_label = "---------"
        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Öffentliche Orte", [(c.id, c.name) for c in external_locations]),
        ]
        self.fields['location'].choices = choices
