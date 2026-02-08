from django.db import models
from main.models import Organization


class RecipeTag(models.Model):
    name = models.CharField(max_length=50)
    is_public = models.BooleanField(default=False, verbose_name="Öffentlich")
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='owned_tags',
                              null=True,
                              blank=True)

    def __str__(self):
        return self.name

    class Meta:
        unique_together = ('name', 'owner')  # erlaubt gleiche Namen für verschiedene Owner


class Recipe(models.Model):
    title = models.CharField(max_length=200, verbose_name="Name")
    description = models.CharField(max_length=2048, default="", blank=True, verbose_name="Beschreibung")
    author = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='authored_recipes')
    owner = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='owned_recipes')
    is_public = models.BooleanField(default=False, verbose_name="Öffentlich")
    created_at = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField(RecipeTag, blank=True, related_name="recipes")

    def __str__(self):
        return self.title


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='ingredients')
    name = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"{self.quantity or ''} {self.unit or ''} {self.name}".strip()


class RecipeStep(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='steps')
    description = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.order}: {self.description[:30]}"
