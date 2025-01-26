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
    password1 = forms.CharField(label='Passwort', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Passwort bestätigen', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['first_name','last_name','username', 'email', 'password1', 'password2']

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Die Passwörter stimmen nicht überein.")
        return password2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True  # E-Mail als Pflichtfeld