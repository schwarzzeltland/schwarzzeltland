from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.crypto import get_random_string

def generate_recipient_code():
    return get_random_string(length=20)

class Organization(models.Model):
    name = models.CharField(unique=True, max_length=254)
    image = models.ImageField(upload_to="users/", blank=True, null=True,verbose_name="Bild")
    recipientcode = models.CharField(default=generate_recipient_code, max_length=20,verbose_name="Empfängercode für den Materialverleih")
    members = models.ManyToManyField(
        User,
        through='Membership',
    )

    def get_owner(self) -> 'Membership':
        return self.membership_set.earliest("id")

    def __str__(self):
        return self.name


class Membership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    admin = models.BooleanField(default=False,verbose_name="Admin")
    material_manager = models.BooleanField(default=False)
    event_manager = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username

    class Meta:
        unique_together = (("user", "organization"),)


@receiver(post_save, sender=User)
def user_created(sender, instance, created, **kwargs):
    if created:
        orga = Organization.objects.create(name=f"{instance.username}s Organisation")
        Membership.objects.create(user=instance, organization=orga, admin=True, material_manager=True)
