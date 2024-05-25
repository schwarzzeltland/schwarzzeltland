from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class Organization(models.Model):
    name = models.CharField(unique=True, max_length=254)
    image = models.ImageField(upload_to="users/", blank=True, null=True)
    members = models.ManyToManyField(
        User,
        through='Membership',
    )

    def __str__(self):
        return self.name


class Membership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    admin = models.BooleanField(default=False)
    material_manager = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username

    class Meta:
        unique_together = (("user", "organization"),)


@receiver(post_save, sender=User)
def user_created(sender, instance, created, **kwargs):
    if created:
        orga = Organization.objects.create(name=f"{instance.username}s Organisation")
        Membership.objects.create(user=instance, organization=orga, admin=True, material_manager=True)
