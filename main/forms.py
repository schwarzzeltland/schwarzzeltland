from django.forms import ModelForm

from main.models import Organization


class OrganizationForm(ModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'image']
