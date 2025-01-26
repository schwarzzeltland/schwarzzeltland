from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.forms import ModelForm, CharField
from django.forms.models import inlineformset_factory

from main.models import Organization


class OrganizationForm(ModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'image']

class MembershipForm(ModelForm):
    user = CharField(label='Benutzer')  # Override with a CharField

    def clean_user(self):
        username = self.cleaned_data['user']
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            raise ValidationError("User does not exist")

    class Meta:
        model = Organization.members.through
        fields = ['user', 'admin', 'material_manager']


MembershipFormset = inlineformset_factory(Organization, Organization.members.through, form=MembershipForm, extra=1,
                                          can_delete=False)

class CustomUserCreationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'email']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password != password_confirm:
            raise forms.ValidationError("Die Passwörter stimmen nicht überein.")
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True  # E-Mail als Pflichtfeld
