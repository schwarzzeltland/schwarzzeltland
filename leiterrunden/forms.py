from django import forms
from django.forms import inlineformset_factory

from leiterrunden.models import MeetingGuest, MeetingMinutes, MeetingMinutesItem


class MeetingMinutesForm(forms.ModelForm):
    class Meta:
        model = MeetingMinutes
        fields = ["title", "meeting_start", "meeting_end", "introduction"]
        widgets = {
            "meeting_start": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "meeting_end": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "introduction": forms.Textarea(attrs={"rows": 4}),
        }

    def clean(self):
        data = super().clean()
        if data.get("meeting_start") and data.get("meeting_end") and data["meeting_end"] < data["meeting_start"]:
            self.add_error("meeting_end", "Das Sitzungsende darf nicht vor dem Beginn liegen.")
        return data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ("meeting_start", "meeting_end"):
            self.fields[field].required = True
            self.fields[field].input_formats = ["%Y-%m-%dT%H:%M"]


class MeetingMinutesItemForm(forms.ModelForm):
    parent_reference = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = MeetingMinutesItem
        fields = ["parent", "topic", "notes", "responsible_members", "due_date", "position"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3}), "due_date": forms.DateInput(attrs={"type": "date"}), "position": forms.HiddenInput()}

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop("organization", None)
        minutes = kwargs.get("instance").minutes if kwargs.get("instance") and kwargs["instance"].pk else None
        super().__init__(*args, **kwargs)
        self.fields["position"].required = False
        self.fields["responsible_members"].required = False
        self.fields["responsible_members"].queryset = organization.membership_set.filter(leiterrundenmitglied=True).select_related("user") if organization else self.fields["responsible_members"].queryset.none()
        self.fields["responsible_members"].widget.attrs.update({"class": "form-select select2-responsible"})
        self.fields["parent"].required = False
        self.fields["parent"].queryset = minutes.items.exclude(pk=self.instance.pk) if minutes else MeetingMinutesItem.objects.none()

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if parent and parent.parent and parent.parent.parent:
            raise forms.ValidationError("Es sind maximal zwei Unterebenen erlaubt.")
        return parent


MeetingMinutesItemFormSet = inlineformset_factory(
    MeetingMinutes,
    MeetingMinutesItem,
    form=MeetingMinutesItemForm,
    extra=0,
    can_delete=True,
)
MeetingGuestFormSet = inlineformset_factory(
    MeetingMinutes,
    MeetingGuest,
    fields=["name", "note"],
    extra=0,
    can_delete=True,
)
