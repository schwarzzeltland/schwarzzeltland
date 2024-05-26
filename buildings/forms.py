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

        # Modify the queryset of the material field
        self.fields['material'].queryset = Material.objects.filter(
            Q(owner=organization) | Q(owner__isnull=True) | Q(public=True))

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
        self.fields['construction'].queryset = Construction.objects.filter(Q(owner=organization) | Q(owner__isnull=True) | Q(public=True))

class ConstructionMaterialForm(ModelForm):
    count = IntegerField(required=True)
    storage_place = CharField(required=False)
    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(ConstructionMaterialForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization

    class Meta:
        model = ConstructionMaterial
        fields = '__all__'
        exclude = ['construction']

ConstructionMaterialFormSet = inlineformset_factory(
    Construction, ConstructionMaterial, form=ConstructionMaterialForm, extra=15
)
