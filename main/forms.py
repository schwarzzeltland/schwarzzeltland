from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.forms import ModelForm, CharField
from django.forms.models import inlineformset_factory

from main.models import Organization, Message


class OrganizationForm(ModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'image', 'recipientcode']


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
        fields = ['user', 'admin', 'material_manager', 'event_manager']


MembershipFormset = inlineformset_factory(Organization, Organization.members.through, form=MembershipForm, extra=1,
                                          can_delete=False)


class CustomUserCreationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput,
        label="Passwort",
        help_text="Das Passwort muss mindestens 8 Zeichen lang sein und sowohl Buchstaben als auch Zahlen enthalten."
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        label="Passwort bestätigen"
    )

    class Meta:
        model = User
        fields = ['username', 'email']
        labels = {
            'username': 'Benutzername',
            'email': 'E-Mail-Adresse'
        }

    def clean_password(self):
        password = self.cleaned_data.get('password')

        # Passwortvalidierung durch Django durchführen
        validate_password(password)

        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        # Überprüfen, ob die Passwörter übereinstimmen
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Die Passwörter stimmen nicht überein.")
        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Ein Benutzer mit dieser E-Mail-Adresse existiert bereits.")
        return email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Felder individuell anpassen
        self.fields['email'].required = True  # E-Mail als Pflichtfeld
        self.fields['username'].widget.attrs.update({'placeholder': 'Benutzername'})
        self.fields['email'].widget.attrs.update({'placeholder': 'E-Mail-Adresse'})
        self.fields['password'].widget.attrs.update({'placeholder': 'Passwort'})
        self.fields['password_confirm'].widget.attrs.update({'placeholder': 'Passwort bestätigen'})


class UsernameReminderForm(forms.Form):
    email = forms.EmailField(label="Deine E-Mail-Adresse")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = True  # E-Mail als Pflichtfeld


class MessageSendForm(forms.ModelForm):
    recipient_name = forms.CharField(label="Empfänger", max_length=255)

    class Meta:
        model = Message
        fields = ['recipient_name', 'subject', 'text']  # nicht recipient, sondern recipient_name

    def clean_recipient_name(self):
        name = self.cleaned_data['recipient_name'].strip()
        from main.models import Organization
        try:
            return Organization.objects.get(name__iexact=name)  # ggf. auch .get(reciepentcode=name)
        except Organization.DoesNotExist:
            raise forms.ValidationError("Organisation mit diesem Namen nicht gefunden.")

    def save(self, commit=True):
        message = super().save(commit=False)
        message.recipient = self.cleaned_data['recipient_name']
        if commit:
            message.save()
        return message


class MessageShowForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Alle Felder readonly machen (nicht bearbeitbar)
        for field in self.fields.values():
            field.disabled = True
