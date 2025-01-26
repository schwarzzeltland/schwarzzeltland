from builtins import str

from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.models import User
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.http import HttpResponse

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.contrib import messages
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from buildings.models import Construction
from django.shortcuts import redirect

from main.decorators import organization_admin_required
from main.forms import OrganizationForm, MembershipFormset, CustomUserCreationForm
from main.models import Organization, Membership


# Create your views here.
def home_view(request):
    return render(request, 'main/index.html', {
        'title': 'Home',
        'constructions': Construction.objects.filter(Q(owner__isnull=True) | Q(public=True)),
    })


@login_required
def organization_view(request):
    if request.method == 'POST' and request.membership.admin:
        form = OrganizationForm(request.POST, request.FILES, instance=request.org)
        if form.is_valid():
            form.save()
            messages.success(request, "Saved")
            return redirect('organization')  # 'organization' sollte der URL-Name für diese Seite sein
    else:
        form = OrganizationForm(instance=request.org)
    return render(request, 'main/organization.html', {
        'title': 'Organisation',
        'form': form,
        'members': request.org.membership_set.all(),
        'organization': request.org,
    })


@login_required
def create_organization(request):
    if request.method == 'POST':
        form = OrganizationForm(request.POST, request.FILES)
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


def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active= False
            user.set_password(form.cleaned_data['password'])
            user.save()

            # Erstelle Token und sende E-Mail
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(str(user.pk).encode('utf-8'))
            domain = get_current_site(request).domain
            link = f"http://{domain}/main/activate/{uid}/{token}/"

            subject = 'Aktiviere dein Konto'
            message = render_to_string('main/activation_email.html', {
                'user': user,
                'link': link,
            })
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email],html_message=message)

            return redirect('email_verification')
    else:
        form = CustomUserCreationForm()
    return render(request, 'main/register.html', {'form': form})


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
        return redirect('home')
    else:
        return redirect('invalid_activation_link')


def email_verification(request):

        return render(request, 'main/email_verification.html')


def invalid_activation_link(request):
    return render(request, 'main/invalid_activation_link.html')
