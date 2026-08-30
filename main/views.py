import datetime
from audioop import reverse
from builtins import str
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse, request
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.sites.shortcuts import get_current_site
from django.db.models import Q, Exists, OuterRef

from buildings.models import Construction
from events.forms import EventPlanningChecklistItemForm
from events.models import EventPlanningChecklistItem
from leiterrunden.models import MeetingMinutesItem, MeetingMinutesItemCompletion
from main.decorators import material_manager_required, organization_admin_required, pro3_required
from main.forms import (
    CustomUserCreationForm,
    MembershipFormset,
    MessageSendForm,
    MessageShowForm,
    OrganizationForm,
    UsernameReminderForm,
)
from main.media_access import serve_protected_media
from main.models import Membership, Message, Organization


def home_view(request):
    constructions = Construction.objects.filter(Q(owner__isnull=True) | Q(public=True))
    return render(request, "main/index.html", {"title": "Home", "constructions": constructions})


def protected_media(request, path):
    return serve_protected_media(request, path)


@login_required
def organization_view(request):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    if request.method == "POST" and request.membership.admin:
        form = OrganizationForm(request.POST, request.FILES, instance=request.org)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved")
            return redirect("organization")
    else:
        form = OrganizationForm(instance=request.org)
    return render(request, "main/organization.html", {
        "title": "Organisation",
        "form": form,
        "members": request.org.membership_set.all(),
        "organization": request.org,
        "usermaterialmanager": m.material_manager,
    })


@login_required
def create_organization(request):
    if request.method == "POST":
        form = OrganizationForm(request.POST, request.FILES)
        formset = MembershipFormset(request.POST)
        if form.is_valid() and formset.is_valid():
            org = form.save()
            formset.instance = org
            formset.save()
            request.session["org"] = org.id
            messages.success(request, "Saved")
            return redirect("organization")
    else:
        form = OrganizationForm()
        formset = MembershipFormset(initial=[{"user": request.user.username}])
    return render(request, "main/create_organization.html", {
        "title": "Organisation",
        "form": form,
        "formset": formset,
        "members": request.org.membership_set.all(),
    })


@organization_admin_required
def change_admin(request, pk):
    m = request.org.membership_set.get(pk=pk)
    if m.user == request.user or request.org.get_owner() == m:
        return HttpResponse("You're not allowed to change yourself", status=403)
    m.admin = not m.admin
    m.save()
    return HttpResponse(status=200)


@organization_admin_required
def change_material_manager(request, pk):
    m = request.org.membership_set.get(pk=pk)
    m.material_manager = not m.material_manager
    m.save()
    return HttpResponse(status=200)


@organization_admin_required
def change_event_manager(request, pk):
    m: Membership = request.org.membership_set.get(pk=pk)
    m.event_manager = not m.event_manager
    m.save()
    return HttpResponse(status=200)


@organization_admin_required
def change_knowledge_manager(request, pk):
    m: Membership = request.org.membership_set.get(pk=pk)
    m.knowledge_manager = not m.knowledge_manager
    m.save()
    return HttpResponse(status=200)


@organization_admin_required
def change_cashier_manager(request, pk):
    m: Membership = request.org.membership_set.get(pk=pk)
    m.cashier_manager = not m.cashier_manager
    m.save()
    return HttpResponse(status=200)


@organization_admin_required
def change_leiterrundenmitglied(request, pk):
    m: Membership = request.org.membership_set.get(pk=pk)
    m.leiterrundenmitglied = not m.leiterrundenmitglied
    m.save(update_fields=["leiterrundenmitglied"])
    return HttpResponse(status=200)


@organization_admin_required
def delete_membership(request, pk):
    m = request.org.membership_set.get(pk=pk)
    if m == request.org.get_owner():
        return HttpResponse("You're not allowed to delete the owner", status=403)
    m.delete()
    return HttpResponse(status=200)


@organization_admin_required
def add_user(request):
    username = request.POST.get("name2", None)
    user = User.objects.filter(username=username).first()
    if user:
        if request.org.membership_set.filter(user=user).exists():
            return HttpResponse("The person is already a member", status=403)
        m = Membership.objects.create(
            organization=request.org,
            user=user,
            admin=request.POST.get("admin", None) == "on",
            material_manager=request.POST.get("material_manager", None) == "on",
            event_manager=request.POST.get("event_manager", None) == "on",
            knowledge_manager=request.POST.get("knowledge_manager", None) == "on",
            cashier_manager=request.POST.get("cashier_manager", None) == "on",
            leiterrundenmitglied=request.POST.get("leiterrundenmitglied", None) == "on",
        )
        return render(request, "main/member_list_entry.html", {"m": m})
    print("unknown user", username)
    return HttpResponse(status=404)


def contacts_view(request):
    return render(request, "main/contacts.html", {"title": "Kontakt"})


def impressum_view(request):
    return render(request, "main/impressum.html", {"title": "Impressum"})


def disclaimer_view(request):
    return render(request, "main/disclaimer.html", {"title": "Haftungsausschluss"})


def privacypolice_view(request):
    return render(request, "main/privacypolice.html", {"title": "Datenschutzerklärung"})


def help_view(request):
    if request.user.is_authenticated:
        membership = request.user.membership_set.filter(organization=request.org).first()
        return render(request, "main/help_authenticated.html", {
            "title": f"Hilfe für {request.org.name}",
            "organization": request.org,
            "membership": membership,
        })
    return render(request, "main/help.html", {"title": "Was ist Schwarzzeltland?"})


def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.set_password(form.cleaned_data["password"])
            user.save()

            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(str(user.pk).encode("utf-8"))
            domain = get_current_site(request).domain
            link = f"http://{domain}/main/activate/{uid}/{token}/"

            subject = "Aktiviere dein Konto"
            message = render_to_string("main/activation_email.html", {"user": user, "link": link})
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], html_message=message)
            return redirect("email_verification")
    else:
        form = CustomUserCreationForm()
    return render(request, "main/register.html", {"form": form})


def activate(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = get_user_model().objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        login(request, user)
        return redirect("home")
    return redirect("invalid_activation_link")


def email_verification(request):
    return render(request, "main/email_verification.html")


def invalid_activation_link(request):
    return render(request, "main/invalid_activation_link.html")


def send_username_email(request):
    if request.method == "POST":
        form = UsernameReminderForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            try:
                user = User.objects.get(email=email)
                username = user.username
                subject = "Dein Benutzername"
                message = f"Hallo {user.username},\n\nDein Benutzername lautet: {username}."
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], html_message=message)
                return render(request, "main/username_sent.html", {"email": email})
            except User.DoesNotExist:
                form.add_error("email", "Es wurde kein Benutzer mit dieser E-Mail-Adresse gefunden.")
    else:
        form = UsernameReminderForm()

    return render(request, "main/username_sent.html", {"form": form})


@login_required
@organization_admin_required
def delete_organization(request, pk=None):
    organization_d = get_object_or_404(Organization, pk=pk)
    if organization_d.name == f"{request.user.username}s Organisation":
        messages.error(request, "Du kannst diese Organisation nicht löschen, da sie deine Hauptorganisation ist.")
        return HttpResponseRedirect(reverse_lazy("organization"))
    if request.method == "POST":
        if request.membership.organization == organization_d and request.membership.admin:
            organization_d.delete()
            messages.success(request, f"Organisation {organization_d.name} erfolgreich gelöscht.")
            return HttpResponseRedirect(reverse_lazy("home"))
    return render(request, "main/delete_organization.html", {"title": "Organisation löschen", "organization": organization_d})


@login_required
def messages_view(request, pk=None):
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    return render(request, "main/messages.html", {"title": "Nachrichten", "isadmin": m.admin})


@login_required
@organization_admin_required
def sendmessage_view(request, pk=None):
    initial_data = {}
    if pk is not None:
        old_message = get_object_or_404(Message, recipient=request.org, pk=pk)
        initial_data = {"recipient_name": old_message.sender.name, "subject": f"AW: {old_message.subject}"}
    if request.method == "POST":
        form = MessageSendForm(request.POST)
        if form.is_valid():
            sentmessages = form.save(commit=False)
            sentmessages.sender = request.org
            sentmessages.save()
            messages.success(request, f"Nachricht an {sentmessages.recipient} am {sentmessages.created} gesendet")
            recipient_org = sentmessages.recipient
            admins = Membership.objects.filter(organization=recipient_org, admin=True)
            recipients = [admin.user.email for admin in admins if admin.user.email]

            if recipients:
                subject = f"Neue Nachricht von {sentmessages.sender.name}"
                text_message = (
                    f"Hallo,\n\n"
                    f"es wurde eine neue Nachricht an eure Organisation {recipient_org.name} gesendet.\n\n"
                    f"Betreff: {sentmessages.subject}\n\n"
                    f"Bitte melde dich in Schwarzzeltland an, um die Nachricht zu lesen:\n"
                    f"{request.build_absolute_uri(reverse_lazy('messages'))}\n\n"
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
                                            <h2 style="color:#333;">Neue Nachricht erhalten</h2>
                                            <p>Hallo,</p>
                                            <p>es wurde eine neue Nachricht an eure Organisation <strong>{recipient_org.name}</strong> gesendet.</p>
                                            <p><strong>Betreff:</strong> {sentmessages.subject}</p>
                                            <div style="text-align:center; margin:32px 0;">
                                              <a href="{request.build_absolute_uri(reverse_lazy('inboxmessages'))}?org={recipient_org.id}"
                                                 style="
                                                   background-color:#ffc451;
                                                   color:#ffffff;
                                                   padding:14px 24px;
                                                   text-decoration:none;
                                                   border-radius:6px;
                                                   display:inline-block;
                                                   font-weight:bold;
                                                 ">
                                                Nachricht öffnen
                                              </a>
                                            </div>
                                            <p style="color:#666; font-size:13px;">Schwarzzeltland</p>
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
                    from_email=f"Schwarzzeltland <{settings.EMAIL_HOST_USER}>",
                    recipient_list=recipients,
                    html_message=html_message,
                    fail_silently=False,
                )
            return HttpResponseRedirect(reverse_lazy("messages"))
    else:
        form = MessageSendForm(initial=initial_data)
    return render(request, "main/sendmessage.html", {"title": "Nachricht senden", "sendmessageform": form})


@login_required
@organization_admin_required
def showmessage_view(request, pk=None):
    message = get_object_or_404(Message.objects.filter(Q(sender=request.org) | Q(recipient=request.org)), pk=pk)
    viewer = "sender" if message.sender == request.org else "recipient"

    if not message.is_read and viewer == "recipient":
        message.is_read = True
        message.save(update_fields=["is_read"])
    message.save(update_fields=["is_read"])
    form = MessageShowForm(instance=message)
    return render(request, "main/showmessage.html", {
        "title": "Nachricht anzeigen",
        "form": form,
        "viewer": viewer,
        "message_pk": message.pk,
    })


@login_required
@organization_admin_required
def messagessent_view(request, pk=None):
    sent_messages = Message.objects.filter(sender=request.org).order_by("-id")
    return render(request, "main/messagessent.html", {"title": "Gesendete Nachrichten", "sent_messages": sent_messages})


@login_required
@organization_admin_required
def messagesinbox_view(request, pk=None):
    inbox_messages = Message.objects.filter(recipient=request.org).order_by("-id")
    return render(request, "main/inbox.html", {"title": "Empfangene Nachrichten", "inbox_messages": inbox_messages})


@csrf_exempt
def accept_cookies(request):
    response = JsonResponse({"status": "ok"})
    response.set_cookie("cookies_accepted", "true", max_age=31536000, samesite="Lax", secure=True)
    return response


def custom_csrf_failure(request, reason=""):
    context = {"reason": reason}
    return render(request, "403_csrf.html", context, status=403)


@login_required
@material_manager_required
@pro3_required
def organization_material_checklist(request):
    items = EventPlanningChecklistItem.objects.filter(organization=request.org, trip__isnull=True).order_by("done", "due_date")
    form = EventPlanningChecklistItemForm()
    responsible_users = User.objects.filter(membership__organization=request.org, membership__material_manager=True).distinct().order_by("username")
    return render(request, "main/organization_material_checklist.html", {
        "title": f"Materialwart To-Do-Liste: {request.org.name}",
        "items": items,
        "form": form,
        "responsible_users": responsible_users,
    })


@login_required
@require_POST
@pro3_required
@material_manager_required
def add_organization_material_checklist_item(request):
    title = request.POST.get("title")
    due_date = request.POST.get("due_date") or None
    responsible = User.objects.filter(pk=request.POST.get("responsible") or None, membership__organization=request.org, membership__material_manager=True).first()
    if due_date:
        try:
            naive_dt = datetime.strptime(due_date, "%Y-%m-%dT%H:%M")
        except ValueError:
            naive_dt = datetime.strptime(due_date, "%Y-%m-%d")
        due_date = timezone.make_aware(naive_dt)
    item = EventPlanningChecklistItem.objects.create(organization=request.org, title=title, due_date=due_date, responsible=responsible)
    return JsonResponse({
        "success": True,
        "item": {
            "id": item.id,
            "title": item.title,
            "done": item.done,
            "due_date": item.due_date.isoformat() if item.due_date else "",
            "responsible_id": item.responsible_id,
            "toggle_url": reverse("toggle_checklist_item", args=[item.id]),
            "delete_url": reverse("delete_checklist_item", args=[item.id]),
        },
    })


@login_required
def personal_todo_list(request):
    membership = request.user.membership_set.filter(organization=request.org).first()
    if not membership or not (membership.event_manager or membership.material_manager or membership.leiterrundenmitglied):
        raise PermissionDenied
    checklist_scope = Q(pk__in=[])
    if membership.event_manager:
        checklist_scope |= Q(trip__owner=request.org)
    if membership.material_manager:
        checklist_scope |= Q(organization=request.org, trip__isnull=True)
    checklist_items = EventPlanningChecklistItem.objects.filter(
        checklist_scope, responsible=request.user
    ).select_related("trip", "organization").order_by("done", "due_date", "title") if request.org.pro3 and (membership.event_manager or membership.material_manager) else []
    meeting_items = MeetingMinutesItem.objects.filter(
        minutes__organization=request.org,
        minutes__published=True,
        responsible_members=membership,
    ).filter(Q(minutes__replacement__isnull=True) | Q(minutes__replacement__published=False)).annotate(
        personal_completed=Exists(MeetingMinutesItemCompletion.objects.filter(item_id=OuterRef("pk"), user=request.user, completed=True))
    ).select_related("minutes").order_by("personal_completed", "due_date", "position") if request.org.pro6 and membership.leiterrundenmitglied else []
    return render(request, "main/personal_todo_list.html", {
        "title": "Meine To-dos",
        "checklist_items": checklist_items,
        "meeting_items": meeting_items,
        "show_checklist_card": request.org.pro3 and (membership.event_manager or membership.material_manager),
        "show_meeting_card": request.org.pro6 and membership.leiterrundenmitglied,
    })


@login_required
@require_POST
def toggle_personal_todo(request, item_id):
    membership = request.user.membership_set.filter(organization=request.org).first()
    if not membership or not (membership.event_manager or membership.material_manager or membership.leiterrundenmitglied) or not request.org.pro3:
        raise PermissionDenied
    item = get_object_or_404(
        EventPlanningChecklistItem,
        Q(pk=item_id, responsible=request.user) & (Q(trip__owner=request.org) | Q(organization=request.org)),
    )
    item.done = not item.done
    item.save(update_fields=["done"])
    return JsonResponse({"success": True, "done": item.done})


@login_required
@require_POST
def toggle_personal_meeting_item(request, item_id):
    membership = request.user.membership_set.filter(organization=request.org).first()
    if not membership or not membership.leiterrundenmitglied or not request.org.pro6:
        raise PermissionDenied
    item = get_object_or_404(
        MeetingMinutesItem,
        pk=item_id,
        minutes__organization=request.org,
        minutes__published=True,
        responsible_members=membership,
    )
    completion, created = MeetingMinutesItemCompletion.objects.get_or_create(item=item, user=request.user)
    if not created:
        completion.completed = not completion.completed
        completion.save(update_fields=["completed", "updated_at"])
    return JsonResponse({"success": True, "done": completion.completed})
