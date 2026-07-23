import io
from datetime import date
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont
from leiterrunden.forms import MeetingGuestFormSet, MeetingMinutesForm, MeetingMinutesItemFormSet
from leiterrunden.models import (
    MeetingAttendance,
    MeetingGuest,
    MeetingMinutes,
    MeetingMinutesAcceptance,
    MeetingMinutesItem,
)
from main.decorators import leiterrundenmitglied_required, pro6_required
from main.models import Membership

def _notify_leiterrunde(request, minutes):
    recipients = list(Membership.objects.filter(organization=request.org, leiterrundenmitglied=True).exclude(user__email="").values_list("user__email", flat=True).distinct())
    if recipients:
        subject = "Geändertes" if minutes.replaces_id else "Neues"
        detail_url = request.build_absolute_uri(reverse("meeting_minutes_detail", args=[minutes.pk]))
        text_message = (
            f"Hallo,\n\n"
            f"das Protokoll „{minutes.title}“ vom {minutes.meeting_start:%d.%m.%Y} wurde veröffentlicht.\n\n"
            f"Bitte prüfe es und bestätige es anschließend über den Button „Annehmen“:\n"
            f"{detail_url}\n\n"
            f"Es gilt als angenommen, sobald mehr als die Hälfte der Leiterrundenmitglieder und alle "
            f"für TOPs verantwortlichen Personen zugestimmt haben.\n\nSchwarzzeltland"
        )
        html_message = render_to_string(
            "leiterrunden/meeting_minutes_email.html",
            {"minutes": minutes, "detail_url": detail_url},
        )
        send_mail(
            f"{subject} Leiterrunden-Protokoll: {minutes.title}",
            text_message,
            f"{request.org.name} <{settings.DEFAULT_FROM_EMAIL or settings.EMAIL_HOST_USER}>",
            recipients,
            html_message=html_message,
            fail_silently=False,
        )
    return len(recipients)

def _form_data(request, minutes=None):
    return (MeetingMinutesForm(request.POST, instance=minutes), MeetingMinutesItemFormSet(request.POST, instance=minutes, form_kwargs={"organization": request.org}), MeetingGuestFormSet(request.POST, instance=minutes))

def _attendance_rows(minutes, organization):
    saved = {row.membership_id: row for row in minutes.attendances.all()} if minutes else {}
    return [(member, saved.get(member.id)) for member in organization.membership_set.filter(leiterrundenmitglied=True).select_related("user").order_by("user__username")]


def _acceptance_rows(minutes):
    acceptances = {
        acceptance.membership_id: acceptance
        for acceptance in minutes.acceptances.select_related("membership__user")
    }
    return [
        (member, acceptances.get(member.id))
        for member in minutes.organization.membership_set.filter(leiterrundenmitglied=True)
        .select_related("user")
        .order_by("user__username")
    ]


def _minutes_tree(minutes):
    items = list(minutes.items.all())
    children = {item.id: [] for item in items}
    roots = []
    for item in items:
        (children.get(item.parent_id, roots) if item.parent_id else roots).append(item)

    def number(nodes, prefix=""):
        for index, item in enumerate(nodes, start=1):
            item.display_number = f"{prefix}.{index}" if prefix else str(index)
            item.tree_children = children[item.id]
            number(item.tree_children, item.display_number)

    number(roots)
    return roots


def _duplicate_minutes(source, user, title, replaces=None):
    """Create a complete, editable copy while preserving the TOP hierarchy."""
    with transaction.atomic():
        duplicate = MeetingMinutes.objects.create(
            organization=source.organization,
            title=title,
            meeting_date=source.meeting_date,
            meeting_start=source.meeting_start,
            meeting_end=source.meeting_end,
            introduction=source.introduction,
            created_by=user,
            replaces=replaces,
        )
        item_map = {}
        source_items = list(source.items.prefetch_related("responsible_members").all())
        for item in source_items:
            copied_item = MeetingMinutesItem.objects.create(
                minutes=duplicate,
                topic=item.topic,
                notes=item.notes,
                responsible=item.responsible,
                due_date=item.due_date,
                position=item.position,
            )
            copied_item.responsible_members.set(item.responsible_members.all())
            item_map[item.pk] = copied_item
        for item in source_items:
            if item.parent_id:
                copied_item = item_map[item.pk]
                copied_item.parent = item_map[item.parent_id]
                copied_item.save(update_fields=["parent"])
        MeetingGuest.objects.bulk_create(
            [MeetingGuest(minutes=duplicate, name=guest.name, note=guest.note) for guest in source.guests.all()]
        )
        MeetingAttendance.objects.bulk_create(
            [
                MeetingAttendance(
                    minutes=duplicate,
                    membership=attendance.membership,
                    present=attendance.present,
                    note=attendance.note,
                )
                for attendance in source.attendances.all()
            ]
        )
    return duplicate

def _save_minutes(request, minutes=None, publish=False):
    form, item_formset, guest_formset = _form_data(request, minutes)
    if not (form.is_valid() and item_formset.is_valid() and guest_formset.is_valid()): return form, item_formset, guest_formset, None
    with transaction.atomic():
        saved = form.save(commit=False)
        if minutes is None: saved.organization, saved.created_by = request.org, request.user
        saved.meeting_date = saved.meeting_start.date() if saved.meeting_start else timezone.localdate()
        if publish: saved.published, saved.published_at = True, timezone.now()
        saved.save(); item_formset.instance = saved
        for index, item in enumerate(item_formset.save(commit=False), start=1):
            item.position = item.position or index
            item.save()
        for item in item_formset.deleted_objects: item.delete()
        item_formset.save_m2m()
        items_by_prefix = {item_form.prefix: item_form.instance for item_form in item_formset.forms if item_form.instance.pk}
        for item_form in item_formset.forms:
            parent_reference = item_form.cleaned_data.get("parent_reference")
            if parent_reference and item_form.prefix in items_by_prefix and parent_reference in items_by_prefix:
                item = items_by_prefix[item_form.prefix]
                item.parent = items_by_prefix[parent_reference]
                item.save(update_fields=["parent"])
        guest_formset.instance = saved; guest_formset.save()
        for member, _ in _attendance_rows(saved, request.org):
            MeetingAttendance.objects.update_or_create(minutes=saved, membership=member, defaults={"present": request.POST.get(f"attendance_{member.id}") == "on", "note": request.POST.get(f"attendance_note_{member.id}", "").strip()})
    return form, item_formset, guest_formset, saved

@login_required
@leiterrundenmitglied_required
@pro6_required
def meeting_minutes_list(request):
    minutes = MeetingMinutes.objects.filter(organization=request.org).prefetch_related(
        "items__responsible_members",
        "acceptances",
    )
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    if query:
        minutes = minutes.filter(
            Q(title__icontains=query)
            | Q(introduction__icontains=query)
            | Q(items__topic__icontains=query)
            | Q(items__notes__icontains=query)
        ).distinct()
    if status == "draft":
        minutes = minutes.filter(published=False)
    elif status == "published":
        minutes = minutes.filter(published=True).filter(
            Q(replacement__isnull=True) | Q(replacement__published=False)
        )
    elif status == "changed":
        minutes = minutes.filter(replacement__published=True)
    try:
        if date_from:
            minutes = minutes.filter(meeting_date__gte=date.fromisoformat(date_from))
        if date_to:
            minutes = minutes.filter(meeting_date__lte=date.fromisoformat(date_to))
    except ValueError:
        messages.warning(request, "Der angegebene Zeitraum ist ungültig.")
    minutes = list(minutes)
    if status == "accepted":
        minutes = [minute for minute in minutes if minute.accepted]
    elif status == "pending":
        minutes = [minute for minute in minutes if minute.published and not minute.changed and not minute.accepted]
    return render(
        request,
        "leiterrunden/meeting_minutes_list.html",
        {
            "title": "Leiterrunden-Protokolle",
            "minutes": minutes,
            "query": query,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "filters_active": any((query, status, date_from, date_to)),
        },
    )

@login_required
@leiterrundenmitglied_required
@pro6_required
def meeting_minutes_create(request):
    if request.method == "POST":
        publish = request.POST.get("action") == "publish"; form, items, guests, minutes = _save_minutes(request, publish=publish)
        if minutes:
            messages.success(request, f"Protokoll veröffentlicht und {_notify_leiterrunde(request, minutes)} Leiterrundenmitglied(er) benachrichtigt." if publish else "Entwurf gespeichert.")
            return redirect("meeting_minutes_detail", pk=minutes.pk)
    else: form, items, guests = MeetingMinutesForm(), MeetingMinutesItemFormSet(form_kwargs={"organization": request.org}), MeetingGuestFormSet()
    return render(request, "leiterrunden/meeting_minutes_form.html", {"title": "Leiterrunden-Protokoll erstellen", "form": form, "formset": items, "guest_formset": guests, "attendance_rows": _attendance_rows(None, request.org), "minutes": None})

@login_required
@leiterrundenmitglied_required
@pro6_required
def meeting_minutes_detail(request, pk):
    minutes = get_object_or_404(MeetingMinutes.objects.select_related("replaces").prefetch_related("items__responsible_members__user", "attendances__membership__user", "guests"), pk=pk, organization=request.org)
    membership = Membership.objects.get(user=request.user, organization=request.org)
    has_accepted = minutes.acceptances.filter(membership=membership).exists()
    return render(
        request,
        "leiterrunden/meeting_minutes_detail.html",
        {
            "title": minutes.title,
            "minutes": minutes,
            "minutes_tree": _minutes_tree(minutes),
            "has_accepted": has_accepted,
            "acceptance_rows": _acceptance_rows(minutes) if minutes.published else [],
        },
    )

@login_required
@leiterrundenmitglied_required
@pro6_required
def meeting_minutes_edit(request, pk):
    minutes = get_object_or_404(MeetingMinutes, pk=pk, organization=request.org)
    if minutes.published: messages.error(request, "Veröffentlichte Protokolle sind gesperrt."); return redirect("meeting_minutes_detail", pk=minutes.pk)
    if request.method == "POST":
        publish = request.POST.get("action") == "publish"; form, items, guests, saved = _save_minutes(request, minutes, publish)
        if saved:
            messages.success(request, f"Protokoll veröffentlicht und {_notify_leiterrunde(request, saved)} Leiterrundenmitglied(er) benachrichtigt." if publish else "Entwurf gespeichert.")
            return redirect("meeting_minutes_detail", pk=saved.pk)
    else: form, items, guests = MeetingMinutesForm(instance=minutes), MeetingMinutesItemFormSet(instance=minutes, form_kwargs={"organization": request.org}), MeetingGuestFormSet(instance=minutes)
    return render(request, "leiterrunden/meeting_minutes_form.html", {"title": "Leiterrunden-Protokoll bearbeiten", "form": form, "formset": items, "guest_formset": guests, "attendance_rows": _attendance_rows(minutes, request.org), "minutes": minutes})


@login_required
@leiterrundenmitglied_required
@pro6_required
def meeting_minutes_duplicate(request, pk):
    source = get_object_or_404(
        MeetingMinutes.objects.prefetch_related("items__responsible_members", "attendances", "guests"),
        pk=pk,
        organization=request.org,
    )
    if request.method != "POST":
        return redirect("meeting_minutes_detail", pk=source.pk)
    duplicate = _duplicate_minutes(source, request.user, f"{source.title} – Duplikat")
    messages.success(request, "Das Protokoll wurde als Entwurf dupliziert.")
    return redirect("meeting_minutes_edit", pk=duplicate.pk)


@login_required
@leiterrundenmitglied_required
@pro6_required
def meeting_minutes_revise(request, pk):
    source = get_object_or_404(
        MeetingMinutes.objects.prefetch_related("items__responsible_members", "attendances", "guests"),
        pk=pk,
        organization=request.org,
        published=True,
    )
    if request.method != "POST":
        return redirect("meeting_minutes_detail", pk=source.pk)
    if source.changed:
        messages.error(request, "Für dieses Protokoll wurde bereits eine neue Fassung veröffentlicht.")
        return redirect("meeting_minutes_detail", pk=source.pk)
    existing_draft = MeetingMinutes.objects.filter(replaces=source, published=False).first()
    revision = existing_draft or _duplicate_minutes(source, request.user, source.title, replaces=source)
    messages.info(request, "Die neue Fassung wurde als Entwurf angelegt. Veröffentliche sie nach der Bearbeitung.")
    return redirect("meeting_minutes_edit", pk=revision.pk)


@login_required
@leiterrundenmitglied_required
@pro6_required
def meeting_minutes_accept(request, pk):
    minutes = get_object_or_404(
        MeetingMinutes,
        pk=pk,
        organization=request.org,
        published=True,
    )
    if request.method != "POST":
        return redirect("meeting_minutes_detail", pk=minutes.pk)
    if minutes.changed:
        messages.error(request, "Eine veraltete Protokollfassung kann nicht mehr angenommen werden.")
        return redirect("meeting_minutes_detail", pk=minutes.pk)
    membership = get_object_or_404(
        Membership,
        user=request.user,
        organization=request.org,
        leiterrundenmitglied=True,
    )
    _, created = MeetingMinutesAcceptance.objects.get_or_create(minutes=minutes, membership=membership)
    messages.success(request, "Du hast das Protokoll angenommen." if created else "Du hast dieses Protokoll bereits angenommen.")
    return redirect("meeting_minutes_detail", pk=minutes.pk)

@login_required
@leiterrundenmitglied_required
@pro6_required
def meeting_minutes_delete(request, pk):
    minutes = get_object_or_404(MeetingMinutes, pk=pk, organization=request.org)
    if minutes.published: messages.error(request, "Veröffentlichte Protokolle sind gesperrt."); return redirect("meeting_minutes_detail", pk=minutes.pk)
    if request.method == "POST": minutes.delete(); messages.success(request, "Entwurf gelöscht."); return redirect("meeting_minutes_list")
    return render(request, "leiterrunden/meeting_minutes_delete.html", {"title": "Protokoll löschen", "minutes": minutes})

@login_required
@leiterrundenmitglied_required
@pro6_required
def meeting_minutes_pdf(request, pk):
    minutes = get_object_or_404(MeetingMinutes.objects.prefetch_related("items", "attendances__membership__user", "guests"), pk=pk, organization=request.org, published=True)
    lines = [minutes.title, f"{minutes.meeting_start:%d.%m.%Y %H:%M} – {minutes.meeting_end:%d.%m.%Y %H:%M}", "", f"Anwesend: {', '.join(a.membership.user.username for a in minutes.attendances.all() if a.present) or '-'}", f"Gäste: {', '.join(g.name for g in minutes.guests.all()) or '-'}", ""] + [f"{item.topic}: {item.notes}" for item in minutes.items.all()]
    image = Image.new("RGB", (1654, 2339), "white"); draw = ImageDraw.Draw(image); y = 100
    for line in lines: draw.text((100, y), line[:180], fill="black", font=ImageFont.load_default()); y += 34
    buffer = io.BytesIO(); image.save(buffer, format="PDF"); response = HttpResponse(buffer.getvalue(), content_type="application/pdf"); response["Content-Disposition"] = f'attachment; filename="leiterrunde-{minutes.pk}.pdf"'; return response


@login_required
@leiterrundenmitglied_required
@pro6_required
def meeting_minutes_pdf(request, pk):
    minutes = get_object_or_404(MeetingMinutes.objects.prefetch_related("items__responsible_members__user", "attendances__membership__user", "guests"), pk=pk, organization=request.org, published=True)
    minutes_tree = _minutes_tree(minutes)
    try:
        from weasyprint import CSS, HTML
        acceptance_rows = _acceptance_rows(minutes)
        html = render_to_string(
            "leiterrunden/meeting_minutes_pdf.html",
            {
                "minutes": minutes,
                "minutes_tree": minutes_tree,
                "acceptance_rows": acceptance_rows,
            },
            request=request,
        )
        pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf(stylesheets=[CSS(string="@page { size: A4; margin: 16mm; }")])
    except (ImportError, OSError):
        lines = [minutes.title, f"{minutes.meeting_start:%d.%m.%Y %H:%M} - {minutes.meeting_end:%d.%m.%Y %H:%M}"]
        if minutes.changed:
            lines += ["", "HINWEIS: Dieses Protokoll wurde geändert.", "Es gibt eine neuere veröffentlichte Fassung."]
        elif minutes.replaces_id:
            lines += ["", "HINWEIS: Geänderte Fassung.", "Dieses Protokoll ersetzt eine vorherige Veröffentlichung."]
        lines += ["", "ANWESEND"]
        lines += [a.membership.user.username for a in minutes.attendances.all() if a.present]
        tree_lines = []
        def add_tree_lines(items, level=0):
            for item in items:
                tree_lines.append((level, f"TOP {item.display_number} {item.topic}"))
                if item.notes:
                    tree_lines.append((level + 1, item.notes))
                add_tree_lines(item.tree_children, level + 1)
        add_tree_lines(minutes_tree)
        lines += ["", "TAGESORDNUNG"] + tree_lines
        acceptance_rows = _acceptance_rows(minutes)
        lines += ["", "ANNAHME", "Status: Angenommen" if minutes.accepted else "Status: Noch nicht angenommen"]
        accepted_rows = [
            f"{member.user.username}: angenommen am {timezone.localtime(acceptance.accepted_at):%d.%m.%Y %H:%M}"
            for member, acceptance in acceptance_rows
            if acceptance
        ]
        pending_rows = [
            member.user.username
            for member, acceptance in acceptance_rows
            if not acceptance
        ]
        lines += ["Angenommen von:"] + (accepted_rows or ["-"])
        lines += ["Noch nicht angenommen von:"] + (pending_rows or ["-"])
        image = Image.new("RGB", (2480, 3508), "white")
        draw = ImageDraw.Draw(image); y = 160
        draw.rectangle((120, 100, 2360, 290), fill="#243447")
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 32)
            title_font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 46)
        except OSError:
            font = ImageFont.load_default()
            title_font = font
        for index, line in enumerate(lines):
            level, text = line if isinstance(line, tuple) else (0, line)
            draw.text((160 + level * 110, y), text[:120], fill="white" if index == 0 else "black", font=title_font if index == 0 else font)
            y += 72 if index else 190
        buffer = io.BytesIO(); image.save(buffer, format="PDF", resolution=300.0); pdf = buffer.getvalue()
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="leiterrunde-{minutes.pk}.pdf"'
    return response
