from typing import Type

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db.models import Q
from urllib3.filepost import iter_field_objects

from buildings.models import Material, StockMaterial, Construction, ConstructionMaterial, MaterialContainer, StoragePlan, StorageArea

from django.forms import IntegerField, CharField, ModelForm, Form, ModelChoiceField, inlineformset_factory, \
    BaseModelFormSet, BaseModelForm


class LocationChoiceMixin:
    LOCATION_CONTAINER = "container"
    LOCATION_PLAN = "plan"
    LOCATION_FREE = "free"
    supports_container = True

    def configure_location_choice(self):
        if not self.supports_container:
            self.fields["location_type"].choices = (
                (self.LOCATION_PLAN, "Bereich im Lagerplan"),
                (self.LOCATION_FREE, "Freier Lagerort"),
            )
        field_order = list(self.fields)
        field_order.remove("location_type")
        location_index = field_order.index("storage_place") if "storage_place" in field_order else len(field_order)
        field_order.insert(location_index, "location_type")
        self.order_fields(field_order)
        if self.is_bound:
            return
        if self.supports_container and getattr(self.instance, "container_id", None):
            self.initial["location_type"] = self.LOCATION_CONTAINER
        elif getattr(self.instance, "storage_area_id", None):
            self.initial["location_type"] = self.LOCATION_PLAN
        else:
            self.initial["location_type"] = self.LOCATION_FREE

    def clean(self):
        cleaned = super().clean()
        location_type = cleaned.get("location_type")
        if location_type == self.LOCATION_CONTAINER and self.supports_container:
            container = cleaned.get("container")
            if not container:
                self.add_error("container", "Bitte eine Materialkiste auswählen.")
            cleaned["storage_area"] = None
            if container:
                cleaned["storage_place"] = container.stock_storage_place
        elif location_type == self.LOCATION_PLAN:
            area = cleaned.get("storage_area")
            if not area:
                self.add_error("storage_area", "Bitte einen Bereich im Lagerplan auswählen.")
            if self.supports_container:
                cleaned["container"] = None
            if area:
                cleaned["storage_place"] = f"{area.plan.name} / {area.name}"
        elif location_type == self.LOCATION_FREE:
            if self.supports_container:
                cleaned["container"] = None
            cleaned["storage_area"] = None
        return cleaned


class AddMaterialStockForm(LocationChoiceMixin, ModelForm):
    location_type = forms.ChoiceField(
        label="Art des Lagerorts", choices=(("container", "Materialkiste"), ("plan", "Bereich im Lagerplan"), ("free", "Freier Lagerort")),
        widget=forms.RadioSelect, initial="free",
    )

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(AddMaterialStockForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization

        self.fields['container'].queryset = MaterialContainer.objects.filter(organization=organization)
        self.fields['container'].label_from_instance = lambda container: container.name
        self.fields['container'].widget.attrs["class"] = "form-select tom-select-location"
        self.fields['storage_area'].queryset = StorageArea.objects.filter(plan__organization=organization).select_related("plan")
        self.fields['storage_area'].widget.attrs["class"] = "form-select tom-select-location"
        self.configure_location_choice()

        # Konstruktionen der eigenen Organisation
        org_material = Material.objects.filter(owner=organization).order_by('name')

        # Externe Konstruktionen, entweder öffentlich oder ohne zugewiesenen Eigentümer
        external_material = Material.objects.filter(Q(public=True) & ~Q(owner=organization) & Q(owner__isnull=False)).order_by('name')
        public_material = Material.objects.filter(Q(owner__isnull=True)).order_by('name')
        # Kombiniere beide Gruppen von Konstruktionen und setze sie als Queryset für das Feld
        combined_queryset = org_material | public_material | external_material

        # Setze das Queryset für das `ModelChoiceField`
        self.fields['material'].queryset = combined_queryset
        self.fields['material'].widget.attrs.update({
            "class": "form-select tom-select-location",
            "data-placeholder": "Material suchen und auswählen",
        })
        self.fields['material'].empty_label = "---------"
        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Eigenes Material", [(c.id, c.name) for c in org_material]),
            ("Grundmaterial", [(c.id, c.name) for c in public_material]),
            ("Öffentliches Material anderer Organisationen", [ (c.id, f"{c.name} ({c.owner.name})")  # Füge den Organisationsnamen hinzu
            for c in external_material]),
        ]
        self.fields['material'].choices = choices

    class Meta:
        model = StockMaterial
        fields = '__all__'
        exclude = ['organization',"condition_healthy","condition_medium_healthy","condition_broke","material_condition_description"]


class MaterialForm(LocationChoiceMixin, ModelForm):
    location_type = forms.ChoiceField(label="Art des Lagerorts", choices=(("container", "Materialkiste"), ("plan", "Bereich im Lagerplan"), ("free", "Freier Lagerort")), widget=forms.RadioSelect, initial="free")
    count = IntegerField(required=True, validators=[MinValueValidator(0)],label='Anzahl')
    storage_place = CharField(required=False,label='Lagerort')
    container = ModelChoiceField(queryset=MaterialContainer.objects.none(), required=False, label="Materialkiste")
    storage_area = ModelChoiceField(queryset=StorageArea.objects.none(), required=False, label="Bereich im Lagerplan")

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(MaterialForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization
        self.fields["container"].queryset = MaterialContainer.objects.filter(organization=organization) if organization else MaterialContainer.objects.none()
        self.fields["container"].widget.attrs["class"] = "form-select tom-select-location"
        self.fields["storage_area"].queryset = StorageArea.objects.filter(plan__organization=organization).select_related("plan") if organization else StorageArea.objects.none()
        self.fields["storage_area"].widget.attrs["class"] = "form-select tom-select-location"
        self.configure_location_choice()

    class Meta:
        model = Material
        fields = '__all__'
        exclude = ['owner']


class StockMaterialForm(LocationChoiceMixin, ModelForm):
    location_type = forms.ChoiceField(
        label="Art des Lagerorts", choices=(("container", "Materialkiste"), ("plan", "Bereich im Lagerplan"), ("free", "Freier Lagerort")),
        widget=forms.RadioSelect, initial="free",
    )
    class Meta:
        model = StockMaterial
        fields = ["count", "storage_place", "container", "storage_area", "condition_healthy","condition_medium_healthy","condition_broke","material_condition_description"]

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)
        self.fields["container"].queryset = MaterialContainer.objects.filter(organization=organization) if organization else MaterialContainer.objects.none()
        self.fields["container"].label_from_instance = lambda container: container.name
        self.fields["container"].widget.attrs["class"] = "form-select tom-select-location"
        self.fields["storage_area"].queryset = StorageArea.objects.filter(plan__organization=organization).select_related("plan") if organization else StorageArea.objects.none()
        self.fields["storage_area"].widget.attrs["class"] = "form-select tom-select-location"
        self.fields['condition_healthy'].widget.attrs['readonly'] = True  # Nutzer kann es nicht direkt ändern
        self.configure_location_choice()

class MaterialContainerForm(LocationChoiceMixin, ModelForm):
    supports_container = False
    location_type = forms.ChoiceField(label="Art des Lagerorts", choices=(("plan", "Bereich im Lagerplan"), ("free", "Freier Lagerort")), widget=forms.RadioSelect, initial="free")
    class Meta:
        model = MaterialContainer
        fields = ["name", "storage_place", "storage_area", "description"]

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization", None)
        super().__init__(*args, **kwargs)
        self.fields["storage_area"].queryset = StorageArea.objects.filter(plan__organization=organization).select_related("plan") if organization else StorageArea.objects.none()
        self.fields["storage_area"].widget.attrs["class"] = "form-select tom-select-location"
        self.configure_location_choice()


class StoragePlanForm(ModelForm):
    class Meta:
        model = StoragePlan
        fields = ["name", "image"]


class StorageAreaForm(ModelForm):
    class Meta:
        model = StorageArea
        fields = ["name", "x", "y", "width", "height"]
        widgets = {field: forms.HiddenInput() for field in ("x", "y", "width", "height")}

    def clean(self):
        cleaned = super().clean()
        for position in ("x", "y"):
            value = cleaned.get(position)
            if value is not None and value > 100:
                self.add_error(position, "Die Position muss innerhalb des Plans liegen.")
        for size in ("width", "height"):
            value = cleaned.get(size)
            if value is not None and (value <= 0 or value > 100):
                self.add_error(size, "Die Größe muss zwischen 0 und 100 Prozent liegen.")
        if all(cleaned.get(field) is not None for field in ("x", "y", "width", "height")):
            if cleaned["x"] + cleaned["width"] > 100 or cleaned["y"] + cleaned["height"] > 100:
                raise ValidationError("Der Bereich muss vollständig innerhalb des Plans liegen.")
        return cleaned


class MaterialContainerContentsForm(forms.Form):
    stock_items = forms.ModelMultipleChoiceField(
        queryset=StockMaterial.objects.none(), required=False, label="Inhalt",
        widget=forms.SelectMultiple(attrs={"class": "form-select select2-stock-items", "data-placeholder": "Materialbestände suchen und auswählen"}),
    )

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization")
        container = kwargs.pop("container")
        super().__init__(*args, **kwargs)
        self.container = container
        self.fields["stock_items"].queryset = StockMaterial.objects.filter(organization=organization).filter(Q(container__isnull=True) | Q(container=container)).select_related("material").order_by("material__name", "storage_place")
        self.fields["stock_items"].initial = container.stock_items.values_list("pk", flat=True)
        self.fields["stock_items"].label_from_instance = lambda item: f"{item.material.name} – {item.count} Stück ({item.storage_place or 'ohne Lagerort'})"

    def save(self):
        selected = self.cleaned_data["stock_items"]
        self.container.stock_items.exclude(pk__in=selected.values_list("pk", flat=True)).update(container=None)
        selected.update(container=self.container, storage_place=self.container.stock_storage_place)


class MaterialContainerQrSheetForm(forms.Form):
    TYPE_QR_ONLY = "qr_only"
    TYPE_NAME_LOCATION = "name_location"
    TYPE_WITH_CONTENTS = "with_contents"
    TYPE_CHOICES = (
        (TYPE_QR_ONLY, "Nur QR-Code"),
        (TYPE_NAME_LOCATION, "QR-Code mit Kistenname und Lagerort"),
        (TYPE_WITH_CONTENTS, "QR-Code mit Kistenname, Lagerort und Inhalt"),
    )

    containers = forms.ModelMultipleChoiceField(
        queryset=MaterialContainer.objects.none(), label="Materialkisten",
        widget=forms.SelectMultiple(attrs={"class": "form-select select2-containers"}),
    )
    output_type = forms.ChoiceField(choices=TYPE_CHOICES, label="Art des Ausdrucks", widget=forms.RadioSelect)

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization")
        super().__init__(*args, **kwargs)
        self.fields["containers"].queryset = MaterialContainer.objects.filter(organization=organization).prefetch_related("stock_items__material")
        self.fields["containers"].label_from_instance = lambda container: f"{container.name} – {container.storage_place or 'kein Lagerort'}"


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
        self.fields['construction'].widget.attrs.update({
            "class": "form-select tom-select",
            "data-placeholder": "Konstruktion suchen und auswählen",
        })
        self.fields['construction'].empty_label = "---------"
        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Eigene Konstruktionen", [(c.id, c.name) for c in org_constructions]),
            ("Grundkonstruktionen", [(c.id, c.name) for c in public_constructions]),
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
        self.fields['material'].widget.attrs.update({
            "class": "form-select tom-select",
            "data-placeholder": "Material suchen und auswählen",
        })
        self.fields['material'].empty_label = "---------"
        # Erstelle Optiongroups
        choices = [
            ('', '---------'),
            ("Eigenes Material", [(c.id, c.name) for c in org_material]),
            ("Grundmaterial", [(c.id, c.name) for c in public_material]),
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
