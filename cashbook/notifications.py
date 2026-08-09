import logging
from email.utils import formataddr

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse


logger = logging.getLogger(__name__)


def _absolute_url(path, organization):
    return f"{settings.SITE_URL.rstrip('/')}{path}?org={organization.pk}"


def notify_responsible_about_request(reimbursement):
    responsible = reimbursement.cashbook.responsible
    if not responsible or not responsible.user.email:
        return False
    url = _absolute_url(reverse("reimbursement_review", args=[reimbursement.pk]), reimbursement.cashbook.organization)
    html_message = render_to_string("cashbook/email/reimbursement_new.html", {
        "reimbursement": reimbursement,
        "recipient_name": responsible.user.get_full_name() or responsible.user.username,
        "action_url": url,
    })
    send_mail(
        subject=f"Neue Auszahlungsanfrage: {reimbursement.title}",
        message=(
            f"Hallo {responsible.user.get_full_name() or responsible.user.username},\n\n"
            f"für das Kassenbuch „{reimbursement.cashbook.name}“ wurde eine neue "
            f"Auszahlungsanfrage über {reimbursement.amount} {reimbursement.cashbook.currency} gestellt.\n\n"
            f"Antragsteller: {reimbursement.requester.get_full_name() or reimbursement.requester.username}\n"
            f"Auslage: {reimbursement.title}\n\n"
            f"Anfrage prüfen: {url}\n"
        ),
        from_email=formataddr((reimbursement.cashbook.organization.name, settings.EMAIL_HOST_USER)),
        recipient_list=[responsible.user.email],
        html_message=html_message,
        fail_silently=False,
    )
    return True


def notify_requester_about_decision(reimbursement):
    if not reimbursement.requester.email:
        return False
    approved = reimbursement.status == reimbursement.STATUS_APPROVED
    status = "genehmigt" if approved else "abgelehnt"
    url = _absolute_url(reverse("reimbursement_list"), reimbursement.cashbook.organization)
    note = f"\nPrüfvermerk: {reimbursement.review_note}\n" if reimbursement.review_note else ""
    html_message = render_to_string("cashbook/email/reimbursement_decision.html", {
        "reimbursement": reimbursement,
        "recipient_name": reimbursement.requester.get_full_name() or reimbursement.requester.username,
        "approved": approved,
        "status": status,
        "action_url": url,
    })
    send_mail(
        subject=f"Auszahlungsanfrage {status}: {reimbursement.title}",
        message=(
            f"Hallo {reimbursement.requester.get_full_name() or reimbursement.requester.username},\n\n"
            f"deine Auszahlungsanfrage „{reimbursement.title}“ über "
            f"{reimbursement.amount} {reimbursement.cashbook.currency} wurde {status}.\n"
            f"{note}\nAuszahlungsanfragen ansehen: {url}\n"
        ),
        from_email=formataddr((reimbursement.cashbook.organization.name, settings.EMAIL_HOST_USER)),
        recipient_list=[reimbursement.requester.email],
        html_message=html_message,
        fail_silently=False,
    )
    return True
