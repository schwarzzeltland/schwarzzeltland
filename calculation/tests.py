from datetime import datetime, timezone
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from cashbook.models import CashBook, CashBookEntry
from calculation.models import CalculationLine, EventCalculation, SubsidyProfile
from calculation.views import _actual_costs_by_category, _cost_line_rows, _group_cost_rows, _values
from events.models import Trip


class CalculationActualCostsTests(TestCase):
    def test_unplanned_expense_category_is_included_in_actual_calculation(self):
        user = User.objects.create_user(username="owner", password="pw")
        organization = user.organization_set.first()
        trip = Trip.objects.create(
            owner=organization,
            name="Sommerlager",
            start_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 8, 10, tzinfo=timezone.utc),
        )
        profile = SubsidyProfile.objects.create(organization=organization, name="Test")
        calculation = EventCalculation.objects.create(trip=trip, profile=profile, event_days=10)
        CalculationLine.objects.create(
            calculation=calculation,
            category="Verpflegung",
            planned_amount="100.00",
        )
        cashbook = CashBook.objects.create(organization=organization, name="Bankkonto")
        CashBookEntry.objects.create(
            cashbook=cashbook,
            trip=trip,
            entry_type=CashBookEntry.TYPE_EXPENSE,
            booking_date="2026-08-05",
            amount="25.00",
            title="Eintritt",
            category="Eintrittsgelder",
        )

        actual_by_category = _actual_costs_by_category(trip)
        rows = _cost_line_rows(calculation, calculation.total_participants, actual_by_category)
        groups = _group_cost_rows(rows, actual_by_category)
        values = _values(calculation, trip, use_cashbook=True)

        unplanned_group = next(group for group in groups if group["category"] == "eintrittsgelder")
        self.assertTrue(unplanned_group["automatic_only"])
        self.assertEqual(unplanned_group["actual_total"], Decimal("25.00"))
        self.assertEqual(values["actual_costs"], Decimal("25.00"))
        self.assertEqual(values["actual_eligible_costs"], Decimal("25.00"))
