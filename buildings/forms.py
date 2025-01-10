from typing import Type

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
        # Materialien gruppieren
        org_materials = Material.objects.filter(owner=organization).order_by('name')
        external_materials = Material.objects.filter(
            Q(owner__isnull=True) | Q(public=True) & ~Q(owner=organization)
        ).order_by('name')

        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Eigene Materialien", [(mat.id, mat.name) for mat in org_materials]),
            ("Öffentliche Materialien", [(mat.id, mat.name) for mat in external_materials]),
        ]
        self.fields['material'].choices = choices

    class Meta:
        model = StockMaterial
        fields = '__all__'
        exclude = ['organization']


class MaterialForm(ModelForm):
    count = IntegerField(required=True)
    storage_place = CharField(required=False)

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
        fields = ["count", 'storage_place']


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
        org_constructions = Construction.objects.filter(owner=organization)

        # Externe Konstruktionen, entweder öffentlich oder ohne zugewiesenen Eigentümer
        external_constructions = Construction.objects.filter(
            Q(owner__isnull=True) | Q(public=True) & ~Q(owner=organization)
        )

        # Kombiniere beide Gruppen von Konstruktionen und setze sie als Queryset für das Feld
        combined_queryset = org_constructions | external_constructions

        # Setze das Queryset für das `ModelChoiceField`
        self.fields['construction'].queryset = combined_queryset
        self.fields['construction'].empty_label = "---------"
        # Materialien gruppieren
        org_constructions = Construction.objects.filter(owner=organization)
        external_constructions = Construction.objects.filter(
            Q(owner__isnull=True) | Q(public=True) & ~Q(owner=organization)
        )
        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Eigene Konstruktionen", [(c.id, c.name) for c in org_constructions]),
            ("Öffentliche Konstruktionen", [(c.id, c.name) for c in external_constructions]),
        ]
        self.fields['construction'].choices = choices


class ConstructionMaterialForm(ModelForm):
    count = IntegerField(required=True)
    storage_place = CharField(required=False)

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(ConstructionMaterialForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization
        # Materialien gruppieren
        org_materials = Material.objects.filter(owner=organization).order_by('name')
        external_materials = Material.objects.filter(
            Q(owner__isnull=True) | Q(public=True) & ~Q(owner=organization)
        ).order_by('name')

        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Eigene Materialien", [(mat.id, mat.name) for mat in org_materials]),
            ("Öffentliche Materialien", [(mat.id, mat.name) for mat in external_materials]),
        ]
        self.fields['material'].choices = choices

    class Meta:
        model = ConstructionMaterial
        fields = '__all__'
        exclude = ['construction']


ConstructionMaterialFormSet = inlineformset_factory(
    Construction, ConstructionMaterial, form=ConstructionMaterialForm, fields=("material", "count", "storage_place"),
    extra=1, can_delete=True
)
