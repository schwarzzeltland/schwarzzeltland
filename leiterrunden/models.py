from django.conf import settings
from django.db import models


class MeetingMinutes(models.Model):
    organization = models.ForeignKey(
        "main.Organization", on_delete=models.CASCADE, related_name="meeting_minutes", verbose_name="Organisation"
    )
    title = models.CharField(max_length=255, verbose_name="Titel")
    meeting_date = models.DateField(verbose_name="Sitzungsdatum")
    meeting_start = models.DateTimeField(null=True, blank=True, verbose_name="Sitzungsbeginn")
    meeting_end = models.DateTimeField(null=True, blank=True, verbose_name="Sitzungsende")
    introduction = models.TextField(blank=True, verbose_name="Einleitung / allgemeine Notizen")
    published = models.BooleanField(default=False, verbose_name="An Leiterrunde veröffentlichen")
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    replaces = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replacement",
        verbose_name="Ersetzt Protokoll",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_meeting_minutes", verbose_name="Erstellt von"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-meeting_date", "-id"]
        verbose_name = "Leiterrunden-Protokoll"
        verbose_name_plural = "Leiterrunden-Protokolle"

    def __str__(self):
        return f"{self.title} ({self.meeting_date:%d.%m.%Y})"

    @property
    def changed(self):
        return hasattr(self, "replacement") and self.replacement.published

    @property
    def accepted(self):
        from main.models import Membership

        if not self.published:
            return False
        eligible_ids = set(
            self.organization.membership_set.filter(leiterrundenmitglied=True).values_list("id", flat=True)
        )
        if not eligible_ids:
            return False
        accepted_ids = set(self.acceptances.values_list("membership_id", flat=True)) & eligible_ids
        responsible_ids = set(
            Membership.objects.filter(
                assigned_meeting_minutes_items__minutes=self,
                leiterrundenmitglied=True,
            ).values_list("id", flat=True)
        )
        return len(accepted_ids) * 2 > len(eligible_ids) and responsible_ids.issubset(accepted_ids)


class MeetingMinutesItem(models.Model):
    minutes = models.ForeignKey(MeetingMinutes, on_delete=models.CASCADE, related_name="items")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children", verbose_name="Übergeordneter TOP")
    topic = models.CharField(max_length=255, verbose_name="Tagesordnungspunkt")
    notes = models.TextField(blank=True, verbose_name="Notizen / Beschluss")
    responsible = models.CharField(max_length=255, blank=True, verbose_name="Verantwortlich")
    responsible_members = models.ManyToManyField("main.Membership", blank=True, related_name="assigned_meeting_minutes_items", verbose_name="Verantwortliche")
    due_date = models.DateField(null=True, blank=True, verbose_name="Fällig am")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Protokollpunkt"
        verbose_name_plural = "Protokollpunkte"

    @property
    def level(self):
        return 0 if not self.parent_id else 1 if not self.parent.parent_id else 2


class MeetingAttendance(models.Model):
    minutes = models.ForeignKey(MeetingMinutes, on_delete=models.CASCADE, related_name="attendances")
    membership = models.ForeignKey("main.Membership", on_delete=models.CASCADE, related_name="meeting_attendances")
    present = models.BooleanField(default=False)
    note = models.CharField(max_length=500, blank=True, verbose_name="Notiz")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["minutes", "membership"], name="unique_minutes_attendance")]
        ordering = ["membership__user__username"]


class MeetingGuest(models.Model):
    minutes = models.ForeignKey(MeetingMinutes, on_delete=models.CASCADE, related_name="guests")
    name = models.CharField(max_length=255, verbose_name="Name")
    note = models.CharField(max_length=500, blank=True, verbose_name="Notiz")


class MeetingMinutesAcceptance(models.Model):
    minutes = models.ForeignKey(MeetingMinutes, on_delete=models.CASCADE, related_name="acceptances")
    membership = models.ForeignKey("main.Membership", on_delete=models.CASCADE, related_name="meeting_minutes_acceptances")
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["minutes", "membership"],
                name="unique_minutes_acceptance",
            )
        ]
        ordering = ["accepted_at"]
        verbose_name = "Protokollannahme"
        verbose_name_plural = "Protokollannahmen"
