from django.contrib.auth.models import User
from django.http import HttpResponse

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.contrib import messages

from buildings.models import Construction
from django.shortcuts import redirect

from main.decorators import organization_admin_required
from main.forms import OrganizationForm, MembershipFormset
from main.models import Organization, Membership


# Create your views here.
def home_view(request):
    return render(request, 'main/index.html', {
        'title': 'Home',
        'constructions': Construction.objects.filter(Q(owner__isnull=True) | Q(public=True)),
    })


@login_required
def organization_view(request):
    if request.method == 'POST':
        form = OrganizationForm(request.POST, instance=request.org)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved")
    else:
        form = OrganizationForm(instance=request.org)
    return render(request, 'main/organization.html', {
        'title': 'Organisation',
        'form': form,
        'members': request.org.membership_set.all(),
    })


@login_required
def create_organization(request):
    if request.method == 'POST':
        form = OrganizationForm(request.POST)
        formset = MembershipFormset(request.POST)
        if form.is_valid() and formset.is_valid():
            org = form.save()
            formset.instance = org
            formset.save()
            request.session["org"] = org.id
            messages.success(request, "Saved")
            return redirect('organization')
    else:
        form = OrganizationForm()
        formset = MembershipFormset(initial=[
            {
                "user": request.user.username,
            }
        ])
    return render(request, 'main/create_organization.html', {
        'title': 'Organisation',
        'form': form,
        'formset': formset,
        'members': request.org.membership_set.all(),
    })


@organization_admin_required
def change_admin(request, pk):
    m = request.org.membership_set.get(pk=pk)
    if m.user == request.user:
        return HttpResponse("You're not allowed to change yourself", status=403)
    m.admin = not m.admin
    m.save()
    return HttpResponse(status=200)


@organization_admin_required
def change_material_manager(request, pk):
    m = request.org.membership_set.get(pk=pk)
    if m.user == request.user:
        return HttpResponse("You're not allowed to change yourself", status=403)
    m.material_manager = not m.material_manager
    m.save()
    return HttpResponse(status=200)

@organization_admin_required
def change_event_manager(request, pk):
    m : Membership = request.org.membership_set.get(pk=pk)
    if m.user == request.user:
        return HttpResponse("You're not allowed to change yourself", status=403)
    m.event_manager = not m.event_manager
    m.save()
    return HttpResponse(status=200)


@organization_admin_required
def delete_membership(request, pk):
    m = request.org.membership_set.get(pk=pk)
    m.delete()
    return HttpResponse(status=200)


@organization_admin_required
def add_user(request):
    username = request.POST.get("name2", None)
    user = User.objects.filter(username=username).first()
    if user:
        m = Membership.objects.create(organization=request.org, user=user,
                                      admin=request.POST.get("admin", None) == "on",
                                      material_manager=request.POST.get("material_manager", None) == "on",
                                      event_manager=request.POST.get("event_manager", None) == "on")
        return render(request, 'main/member_list_entry.html', {
            'm': m,
        })
    print("unknown user", username)
    return HttpResponse(status=404)


def contacts_view(request):
    return render(request, 'main/contacts.html', {
        'title': 'Kontakt',
    })


def impressum_view(request):
    return render(request, 'main/impressum.html', {
        'title': 'Impressum',
    })


def disclaimer_view(request):
    return render(request, 'main/disclaimer.html', {
        'title': 'Haftungsausschluss',
    })


def privacypolice_view(request):
    return render(request, 'main/privacypolice.html', {
        'title': 'Datenschutzerklärung',
    })


def help_view(request):
    return render(request, 'main/help.html', {
        'title': 'Was ist Schwarzzeltland?',
    })
