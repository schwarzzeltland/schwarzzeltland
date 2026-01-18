from django.urls import reverse
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
        if item.trip:
            url = settings.SITE_URL + reverse(
                "checklist", args=[item.trip.id]
            )
        elif item.organization:
            url = settings.SITE_URL + reverse(
                "organization_material_checklist", args=[item.organization.id]
            )
        else:
            url = settings.SITE_URL
        logger.info(f"E-Mail wird an {recipients} mit dem Titel {item.title} gesendet!")
        subject = f"⏰ Heute fällig: {item.title}"
        text_message = (
            f"Hallo,\n\n"
            f"der folgende Checklistenpunkt ist heute fällig:\n\n"
            f"{item.title}\n"
            f"Fällig am: {item.due_date.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Zum To-Do: {url}\n\n"
            f"Schwarzzeltland"
        )

        html_message = f"""
        <!DOCTYPE html>
        <html>
          <body style="font-family: Arial, sans-serif; background-color: #f6f6f6; padding: 20px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td align="center">
                  <table width="600" style="background:#ffffff; border-radius:8px; padding:24px;">
                    <tr>
                      <td>
                        <h2 style="color:#333;">⏰ Heute fällig</h2>

                        <p>Hallo,</p>

                        <p>
                          der folgende <strong>Checklistenpunkt</strong> ist heute fällig:
                        </p>

                        <p style="font-size:16px; font-weight:bold;">
                          {item.title}
                        </p>

                        <p>
                          <strong>Fällig am:</strong><br>
                          {item.due_date.strftime('%d.%m.%Y %H:%M')}
                        </p>

                        {"<p><strong>Trip:</strong><br>" + str(item.trip) + "</p>" if item.trip else ""}
                        {"<p><strong>Organisation:</strong><br>" + str(item.organization) + "</p>" if item.organization else ""}

                        <div style="text-align:center; margin:32px 0;">
                          <a href="{url}"
                             style="
                               background-color:#1f6feb;
                               color:#ffffff;
                               padding:14px 24px;
                               text-decoration:none;
                               border-radius:6px;
                               display:inline-block;
                               font-weight:bold;
                             ">
                            To-Do öffnen
                          </a>
                        </div>

                        <p style="color:#666; font-size:13px;">
                          Schwarzzeltland – Organisation & Planung
                        </p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </body>
        </html>
        """

        send_mail(
            subject=subject,
            message=text_message,
            recipient_list=recipients,
            html_message=html_message,
            from_email=f"{item.organization.name} – Schwarzzeltland {settings.DEFAULT_FROM_EMAIL}",
            fail_silently=False,
        )
