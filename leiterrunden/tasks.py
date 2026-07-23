from email.utils import formataddr

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from leiterrunden.models import MeetingMinutesItem
from main.models import Membership


@shared_task
def send_due_meeting_minutes_items_today():
    """Notify the responsible members, or the complete Leiterrunde, about due TOPs."""
    today = timezone.localdate()
    items = (
        MeetingMinutesItem.objects.select_related("minutes__organization")
        .prefetch_related("responsible_members__user")
        .filter(
            due_date=today,
            minutes__published=True,
        )
        .filter(
            Q(minutes__replacement__isnull=True)
            | Q(minutes__replacement__published=False)
        )
    )
    sent_count = 0
    for item in items:
        responsible_members = list(item.responsible_members.select_related("user"))
        if responsible_members:
            recipients = sorted(
                {
                    member.user.email
                    for member in responsible_members
                    if member.user.email
                }
            )
        else:
            recipients = sorted(
                set(
                    Membership.objects.filter(
                        organization=item.minutes.organization,
                        leiterrundenmitglied=True,
                    )
                    .exclude(user__email="")
                    .values_list("user__email", flat=True)
                )
            )
        if not recipients:
            continue

        detail_url = (
            settings.SITE_URL.rstrip("/")
            + reverse("meeting_minutes_detail", args=[item.minutes_id])
            + f"?org={item.minutes.organization_id}"
        )
        text_message = (
            f"Hallo,\n\n"
            f"der folgende TOP aus dem Protokoll „{item.minutes.title}“ ist heute fällig:\n\n"
            f"{item.topic}\n"
            f"Fällig am: {item.due_date:%d.%m.%Y}\n\n"
            f"Zum Protokoll: {detail_url}\n\n"
            f"Schwarzzeltland"
        )
        html_message = render_to_string(
            "leiterrunden/meeting_minutes_due_email.html",
            {"item": item, "detail_url": detail_url},
        )
        send_mail(
            subject=f"⏰ Heute fällig: {item.topic}",
            message=text_message,
            recipient_list=recipients,
            html_message=html_message,
            from_email=formataddr(
                (
                    item.minutes.organization.name,
                    settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER,
                )
            ),
            fail_silently=False,
        )
        sent_count += 1
    return sent_count
