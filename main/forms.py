from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.forms import CharField, ModelForm
from django.forms.models import inlineformset_factory

from main.models import Message, Organization


class OrganizationForm(ModelForm):
    default_checklist = forms.CharField(
        required=False,
        label="Standard-To-dos bei neuen Veranstaltungen",
        help_text="Eine Zeile pro To-do: Titel | Tage relativ zum Veranstaltungsbeginn. Negative Werte liegen vor, positive nach dem Beginn. Die Tageszahl ist optional.",
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 7,
            "placeholder": "Anmeldung schließen | -14\nMaterial packen | -1\nNachbereitung | 3",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and self.instance and self.instance.pk:
            lines = []
            for item in self.instance.default_checklist or []:
                if isinstance(item, dict):
                    title = str(item.get("title", "")).strip()
                    days = item.get("days_from_start")
                    lines.append(f"{title} | {days}" if days is not None else title)
                else:
                    lines.append(str(item))
            self.initial["default_checklist"] = "\n".join(lines)

    def clean_default_checklist(self):
        entries = []
        for line_number, raw_line in enumerate(self.cleaned_data.get("default_checklist", "").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            title, separator, raw_days = line.rpartition("|")
            if not separator:
                entries.append({"title": line, "days_from_start": None})
                continue
            title = title.strip()
            if not title:
                raise ValidationError(f"In Zeile {line_number} fehlt der Titel des To-dos.")
            try:
                days = int(raw_days.strip())
            except ValueError as exc:
                raise ValidationError(f"In Zeile {line_number} muss nach dem | eine ganze Tageszahl stehen.") from exc
            entries.append({"title": title, "days_from_start": days})
        return entries

    class Meta:
        model = Organization
        fields = ["name", "image", "recipientcode", "default_checklist"]


class MembershipForm(ModelForm):
    user = CharField(label="Benutzer")

    def clean_user(self):
        username = self.cleaned_data["user"]
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise ValidationError("User does not exist") from exc

    class Meta:
        model = Organization.members.through
        fields = ["user", "admin", "material_manager", "event_manager"]


MembershipFormset = inlineformset_factory(
    Organization,
    Organization.members.through,
    form=MembershipForm,
    extra=1,
    can_delete=False,
)


class CustomUserCreationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput,
        label="Passwort",
        help_text="Das Passwort muss mindestens 8 Zeichen lang sein und sowohl Buchstaben als auch Zahlen enthalten.",
    )
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Passwort bestätigen")

    class Meta:
        model = User
        fields = ["username", "email"]
        labels = {"username": "Benutzername", "email": "E-Mail-Adresse"}

    def clean_password(self):
        password = self.cleaned_data.get("password")
        validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Die Passwörter stimmen nicht überein.")
        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Ein Benutzer mit dieser E-Mail-Adresse existiert bereits.")
        return email

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["username"].widget.attrs.update({"placeholder": "Benutzername"})
        self.fields["email"].widget.attrs.update({"placeholder": "E-Mail-Adresse"})
        self.fields["password"].widget.attrs.update({"placeholder": "Passwort"})
        self.fields["password_confirm"].widget.attrs.update({"placeholder": "Passwort bestätigen"})


class UsernameReminderForm(forms.Form):
    email = forms.EmailField(label="Deine E-Mail-Adresse")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True


class MessageSendForm(forms.ModelForm):
    recipient_name = forms.CharField(label="Empfänger", max_length=255)

    class Meta:
        model = Message
        fields = ["recipient_name", "subject", "text"]

    def clean_recipient_name(self):
        name = self.cleaned_data["recipient_name"].strip()
        try:
            return Organization.objects.get(name__iexact=name)
        except Organization.DoesNotExist as exc:
            raise forms.ValidationError("Organisation mit diesem Namen nicht gefunden.") from exc

    def save(self, commit=True):
        message = super().save(commit=False)
        message.recipient = self.cleaned_data["recipient_name"]
        if commit:
            message.save()
        return message


class MessageShowForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.disabled = True
