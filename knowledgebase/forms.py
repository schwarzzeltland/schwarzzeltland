from django import forms
from .models import Recipe

from django import forms
from .models import Recipe

class RecipeForm(forms.ModelForm):
    class Meta:
        model = Recipe
        fields = ['title','description', 'is_public']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description':forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
