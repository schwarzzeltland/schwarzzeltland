from django.db import models


class SubsidyProfile(models.Model):
    organization = models.ForeignKey("main.Organization", on_delete=models.CASCADE, related_name="subsidy_profiles")
    name = models.CharField(max_length=255)
    active = models.BooleanField(default=True)
    registration_deadline = models.DateField(null=True, blank=True)
    full_rate_days = models.PositiveIntegerField(default=56)
    reduced_rate_days = models.PositiveIntegerField(default=90)
    rate_per_person_day = models.DecimalField(max_digits=7, decimal_places=2, default=4)
    rate_per_person_hour = models.DecimalField(max_digits=7, decimal_places=2, default=2)
    reduced_rate_factor = models.DecimalField(max_digits=5, decimal_places=4, default="0.625")
    late_rate_factor = models.DecimalField(max_digits=5, decimal_places=4, default="0.5")
    maximum_cost_share = models.DecimalField(max_digits=5, decimal_places=4, default="0.4")
    minimum_eligible_participants = models.PositiveIntegerField(default=7)
    minimum_event_days = models.PositiveIntegerField(default=2)
    education_qs_exempt_from_minimum_days = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = (("organization", "name"),)

    def __str__(self):
        return self.name


class EventCalculation(models.Model):
    trip = models.OneToOneField("events.Trip", on_delete=models.CASCADE, related_name="calculation")
    profile = models.ForeignKey(SubsidyProfile, on_delete=models.PROTECT)
    eligible_participants = models.PositiveIntegerField(default=0)
    total_participants = models.PositiveIntegerField(default=0)
    guest_count = models.PositiveIntegerField(default=0)
    guest_subsidy_per_person = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    leader_count = models.PositiveIntegerField(default=0)
    leader_discount_per_person = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    event_days = models.PositiveIntegerField(default=0)
    is_education_or_qs = models.BooleanField(default=False)
    education_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    other_subsidies = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    leader_discounts = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    participant_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    non_member_participants = models.PositiveIntegerField(default=0)
    non_member_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    documents_received_at = models.DateField(null=True, blank=True)
    actual_eligible_costs_override = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    actual_income_manual = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)


class CalculationLine(models.Model):
    MODE_FIXED = "fixed"
    MODE_PER_PERSON = "per_person"
    MODE_PER_PERSON_DAY = "per_person_day"
    MODE_CHOICES = ((MODE_FIXED, "Fixer Betrag"), (MODE_PER_PERSON, "Betrag pro Person"), (MODE_PER_PERSON_DAY, "Betrag pro Person und Tag"))
    calculation = models.ForeignKey(EventCalculation, on_delete=models.CASCADE, related_name="lines")
    category = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True)
    calculation_mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_FIXED)
    planned_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    eligible = models.BooleanField(default=True)


class CalculationParticipantGroup(models.Model):
    calculation = models.ForeignKey(EventCalculation, on_delete=models.CASCADE, related_name="participant_groups")
    name = models.CharField(max_length=255)
    count = models.PositiveIntegerField(default=0)
    fee_per_person = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    discount_per_person = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    eligible_for_subsidy = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]


class CalculationTransport(models.Model):
    MODE_BUS = "bus"
    MODE_CAR = "car"
    MODE_TRAIN = "train"
    MODE_OTHER = "other"
    MODE_CHOICES = ((MODE_BUS, "Bus"), (MODE_CAR, "PKW"), (MODE_TRAIN, "Zug"), (MODE_OTHER, "Sonstiges"))
    calculation = models.ForeignKey(EventCalculation, on_delete=models.CASCADE, related_name="transports")
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_OTHER)
    description = models.CharField(max_length=255, blank=True)
    persons = models.PositiveIntegerField(default=0)
    distance_km = models.DecimalField(max_digits=8, decimal_places=1, default=0)
    rate_per_km = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fixed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    @property
    def planned_amount(self):
        return self.fixed_amount + self.distance_km * self.rate_per_km


class CalculationEducationSession(models.Model):
    calculation = models.ForeignKey(EventCalculation, on_delete=models.CASCADE, related_name="education_sessions")
    topic = models.CharField(max_length=255)
    hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
