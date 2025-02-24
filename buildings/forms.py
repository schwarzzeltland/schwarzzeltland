from typing import Type

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db.models import Q
from urllib3.filepost import iter_field_objects

from buildings.models import Material, StockMaterial, Construction, ConstructionMaterial

from django.forms import IntegerField, CharField, ModelForm, Form, ModelChoiceField, inlineformset_factory, \
    BaseModelFormSet, BaseModelForm


class AddMaterialStockForm(ModelForm):

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(AddMaterialStockForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization

        # Konstruktionen der eigenen Organisation
        org_material = Material.objects.filter(owner=organization).order_by('name')

        # Externe Konstruktionen, entweder öffentlich oder ohne zugewiesenen Eigentümer
        external_material = Material.objects.filter(Q(public=True) & ~Q(owner=organization) & Q(owner__isnull=False)).order_by('name')
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
            ("Öffentliches Material", [(c.id, c.name) for c in public_material]),
            ("Öffentliches Material anderer Organisationen", [ (c.id, f"{c.name} ({c.owner.name})")  # Füge den Organisationsnamen hinzu
            for c in external_material]),
        ]
        self.fields['material'].choices = choices

    class Meta:
        model = StockMaterial
        fields = '__all__'
        exclude = ['organization',"condition_healthy","condition_medium_healthy","condition_broke","material_condition_description"]


class MaterialForm(ModelForm):
    count = IntegerField(required=True, validators=[MinValueValidator(0)],label='Anzahl')
    storage_place = CharField(required=False,label='Lagerort')

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(MaterialForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization

    class Meta:
        model = Material
        fields = '__all__'
        exclude = ['owner']


class StockMaterialForm(ModelForm):
    class Meta:
        model = StockMaterial
        fields = ["count", "storage_place","condition_healthy","condition_medium_healthy","condition_broke","material_condition_description"]

    def clean(self):
        cleaned_data = super().clean()
        count = cleaned_data.get("count")
        condition_healthy = cleaned_data.get("condition_healthy") or 0
        condition_medium_healthy = cleaned_data.get("condition_medium_healthy") or 0
        condition_broke = cleaned_data.get("condition_broke") or 0

        total_condition = condition_healthy + condition_medium_healthy + condition_broke

        if count is not None and total_condition != count:
            error_msg = "Die Summe der Zustände darf nicht größer als die Gesamtanzahl sein."
            self.add_error("condition_healthy", error_msg)
            self.add_error("condition_medium_healthy", error_msg)
            self.add_error("condition_broke", error_msg)

        return cleaned_data

class PlainMaterialForm(ModelForm):
    class Meta:
        model = Material
        fields = "__all__"
        exclude = ['owner']


class ConstructionForm(ModelForm):
    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(ConstructionForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization

    class Meta:
        model = Construction
        fields = '__all__'
        exclude = ['owner']


class ImportConstructionForm(Form):
    construction = ModelChoiceField(queryset=Construction.objects.none())

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(ImportConstructionForm, self).__init__(*args, **kwargs)
        self.organization = organization

        # Konstruktionen der eigenen Organisation
        org_constructions = Construction.objects.filter(owner=organization).order_by('name')

        # Externe Konstruktionen, entweder öffentlich oder ohne zugewiesenen Eigentümer
        external_constructions = Construction.objects.filter(Q(public=True) & ~Q(owner=organization) & Q(owner__isnull=False)).order_by('name')
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
            ("Öffentliche Konstruktionen", [(c.id, c.name) for c in public_constructions]),
            ("Öffentliche Konstruktionen anderer Organisationen", [ (c.id, f"{c.name} ({c.owner.name})")  # Füge den Organisationsnamen hinzu
            for c in external_constructions]),
        ]
        self.fields['construction'].choices = choices


class ConstructionMaterialForm(ModelForm):
    count = IntegerField(required=True, validators=[MinValueValidator(0)], label='Anzahl')
    storage_place = CharField(required=False, label='Lagerort')
    add_to_stock = forms.BooleanField(
        required=False,
        label="In Lager übernehmen",
        initial=False
    )

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(ConstructionMaterialForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization

        # Konstruktionen der eigenen Organisation
        org_material = Material.objects.filter(owner=organization).order_by('name')

        # Externe Konstruktionen, entweder öffentlich oder ohne zugewiesenen Eigentümer
        external_material = Material.objects.filter(Q(public=True) & ~Q(owner=organization) & Q(owner__isnull=False)).order_by('name')
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
            ("Öffentliches Material", [(c.id, c.name) for c in public_material]),
            ("Öffentliches Material anderer Organisationen", [ (c.id, f"{c.name} ({c.owner.name})")  # Füge den Organisationsnamen hinzu
            for c in external_material]),
        ]
        self.fields['material'].choices = choices

    class Meta:
        model = ConstructionMaterial
        fields = '__all__'
        exclude = ['construction', 'packed']


ConstructionMaterialFormSet = inlineformset_factory(
    Construction, ConstructionMaterial, form=ConstructionMaterialForm,
    fields=("material", "count", "storage_place", "add_to_stock"),
    extra=1, can_delete=True
)
