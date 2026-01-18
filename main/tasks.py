from django.utils import timezone

from celery import shared_task
import logging

from django.core.mail import send_mail

from events.models import EventPlanningChecklistItem
from main.models import Membership
from schwarzzeltland import settings

logger = logging.getLogger(__name__)

@shared_task
def heartbeat_task():
    logger.info("The Celery Beat is working!")

@shared_task
def send_due_checklist_items_today():
    """
    Sendet E-Mails für Checklistenpunkte,
    die HEUTE fällig und noch nicht erledigt sind.

    - Trip → Planer
    - Organisation → Materialwarte
    """

    today = timezone.localdate()

    items = (
        EventPlanningChecklistItem.objects
        .select_related("trip", "organization")
        .filter(
            due_date__date=today,
            done=False,
        )
    )

    for item in items:
        recipients = set()

        # 🔹 Fall 1: Trip → Planer
        if item.trip:
            planners = item.trip.planners.all()
            for user in planners:
                if user.email:
                    recipients.add(user.email)

        # 🔹 Fall 2: Organisation → Materialwarte
        if item.organization:
            material_managers = Membership.objects.filter(
                organization=item.organization,
                material_manager=True,
            ).select_related("user")

            for membership in material_managers:
                if membership.user.email:
                    recipients.add(membership.user.email)

        # ❌ Keine Empfänger → keine Mail
        if not recipients:
            continue
        logger.info(f"E-Mail wird an {recipients} mit dem Titel {item.title} gesendet!")
        send_mail(
            subject=f"⏰ Heute fällig: {item.title}",
            message=(
                f"Hallo,\n\n"
                f"der folgende Checklistenpunkt ist heute fällig:\n\n"
                f"• {item.title}\n"
                f"• Fällig am: {item.due_date.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"{f'Trip: {item.trip}' if item.trip else ''}\n"
                f"{f'Organisation: {item.organization}' if item.organization else ''}\n\n"
                f"Schwarzzeltland"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=list(recipients),
            fail_silently=False,
        )
