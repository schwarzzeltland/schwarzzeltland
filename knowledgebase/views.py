from django.contrib import messages
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from kombu.utils import json

from main.decorators import knowledge_manager_required
from main.models import Membership
from .forms import RecipeForm
from .models import Recipe, RecipeIngredient, RecipeStep, RecipeTag
from django.contrib.auth.decorators import login_required


@login_required
def recipes(request):
    org = request.org
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    context = {
        'organization': org,
        'title': "Rezepte",
        'isknowledge_manager': m.knowledge_manager,
    }
    return render(request, 'knowledgebase/recipes.html', context)


@login_required
def my_recipes(request):
    org = request.org
    m: Membership = request.user.membership_set.filter(organization=request.org).first()
    title_query = request.GET.get("title", "").strip()
    tags_query = request.GET.get("tags", "").strip()
    recipes = Recipe.objects.filter(owner=org)

    # Titel filtern
    if title_query:
        recipes = recipes.filter(title__icontains=title_query)

    # Tags filtern (UND-Suche)
    if tags_query:
        tag_names = [t.strip() for t in tags_query.split(",") if t.strip()]
        for tag_name in tag_names:
            recipes = recipes.filter(tags__name__iexact=tag_name)

    recipes = recipes.distinct().order_by('title')

    return render(request, "knowledgebase/my_recipes.html", {
        "recipes": recipes,
        "title":'Meine Rezepte',
        "title_query": title_query,
        "tags_query": tags_query,
        "is_knowledge_manager": m.knowledge_manager,
    })


@login_required
def public_recipes(request):
    org = request.org
    title_query = request.GET.get("title", "").strip()
    tags_query = request.GET.get("tags", "").strip()
    recipes = Recipe.objects.filter(is_public=True)

    # Titel filtern
    if title_query:
        recipes = recipes.filter(title__icontains=title_query)

    # Tags filtern (UND-Suche)
    if tags_query:
        tag_names = [t.strip() for t in tags_query.split(",") if t.strip()]
        for tag_name in tag_names:
            recipes = recipes.filter(tags__name__iexact=tag_name)

    recipes = recipes.distinct().order_by('title')

    return render(request, "knowledgebase/public_recipes.html", {
        "recipes": recipes,
        "title":'Öffentliche Rezepte',
        "title_query": title_query,
        "tags_query": tags_query,
    })


@login_required
@knowledge_manager_required
def new_recipe(request):
    org = request.org
    if request.method == "POST":
        title = request.POST.get("title")
        is_public = request.POST.get("is_public") == "on"
        description = request.POST.get("description")
        tags_input = request.POST.get("tags", "")  # "Dessert,Kuchen,Schokolade"
        person_count = request.POST.get("servings")
        try:
            person_count = float(person_count)
            if person_count <= 0:
                person_count = 1
        except (TypeError, ValueError):
            person_count = 1  # Fallback auf 1 Person
        recipe = Recipe.objects.create(
            title=title,
            description=description,
            owner=org,
            author=org,
            is_public=is_public
        )

        # Tags
        for t_name in [t.strip() for t in tags_input.split(",") if t.strip()]:
            tag_obj, _ = RecipeTag.objects.get_or_create(name=t_name, owner=org)
            tag_obj.is_public = recipe.is_public
            tag_obj.save()
            recipe.tags.add(tag_obj)

        # Zutaten
        ingredient_names = request.POST.getlist("ingredient_name[]")
        ingredient_qtys = request.POST.getlist("ingredient_qty[]")
        ingredient_units = request.POST.getlist("ingredient_unit[]")
        ingredient_groups = request.POST.getlist("ingredient_group[]")
        servings = float(request.POST.get("servings", 1))
        for name, qty, unit, group in zip(ingredient_names, ingredient_qtys, ingredient_units, ingredient_groups):
            if name.strip():
                RecipeIngredient.objects.create(
                    recipe=recipe,
                    name=name.strip(),
                    quantity=float(qty) / servings if qty else None,
                    unit=unit.strip(),
                    product_group=int(group) if group else None
                )

        # Arbeitsschritte
        step_descriptions = request.POST.getlist("step_description[]")
        for idx, desc in enumerate(step_descriptions):
            if desc.strip():
                RecipeStep.objects.create(
                    recipe=recipe,
                    description=desc.strip(),
                    order=idx
                )
        messages.success(request, f'Rezept {recipe.title} gespeichert.')
        return redirect("recipes")

    # GET → einfach Template rendern
    return render(request, "knowledgebase/new_recipe.html", {"title": "Neues Rezept erstellen"})


@login_required
def tag_autocomplete(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse([], safe=False)

    org = request.org
    # Filter: eigene Tags, nur Name

    tags = RecipeTag.objects.filter(
        Q(name__icontains=query) & (Q(is_public=True) | Q(owner=org))
    ).values_list("name", flat=True).distinct()
    return JsonResponse(list(tags), safe=False)


@login_required
def public_tag_autocomplete(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse([], safe=False)

    org = request.org

    # Filter: eigene Tags, nur Name
    tags = RecipeTag.objects.filter(
        name__icontains=query,
        is_public=True  # nur öffentliche Tags
    ).values_list("name", flat=True).distinct()

    return JsonResponse(list(tags), safe=False)


@login_required
def show_public_recipe(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk, is_public=True)
    ingredients = recipe.ingredients.all()
    steps = recipe.steps.all()
    tags = recipe.tags.all()
    # Standardmäßig 1 Person
    try:
        servings = int(request.POST.get("servings", 1))
        if servings < 1:
            servings = 1
    except (TypeError, ValueError):
        servings = 1

    # Mengen anpassen
    adjusted_ingredients = []
    for ing in ingredients:
        if ing.quantity is not None:
            adjusted_qty = ing.quantity * servings
        else:
            adjusted_qty = None
        adjusted_ingredients.append({
            "name": ing.name,
            "unit": ing.unit,
            "quantity": adjusted_qty
        })
    return render(request, 'knowledgebase/show_recipe.html', {
        'recipe': recipe,
        'ingredients': adjusted_ingredients,
        'steps': steps,
        'servings': servings,
        'tags': tags,
    })


@knowledge_manager_required
def copy_public_recipe(request, pk):
    original = get_object_or_404(Recipe, pk=pk, is_public=True)

    # Tags, Ingredients, Steps zwischenspeichern
    tags = list(original.tags.all())
    ingredients = list(original.ingredients.all())
    steps = list(original.steps.all())

    # Neues Rezept erstellen
    recipe = original
    recipe.pk = None
    recipe.owner = request.org
    recipe.is_public = False
    recipe.author = request.org
    recipe.save()

    # Tags kopieren
    recipe.tags.set(tags)

    # Ingredients kopieren
    for ing in ingredients:
        ing.pk = None
        ing.recipe = recipe
        ing.save()

    # Steps kopieren
    for step in steps:
        step.pk = None
        step.recipe = recipe
        step.save()

    messages.success(request, f'Rezept {recipe.title} gespeichert.')
    return redirect('recipes')


@login_required
def show_my_recipe(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk, owner=request.org)
    ingredients = recipe.ingredients.all()
    steps = recipe.steps.all()
    tags = recipe.tags.all()
    # 1️⃣ Basiswert aus GET (z. B. vom Trip)
    try:
        servings = int(request.GET.get("persons", 1))
    except (TypeError, ValueError):
        servings = 1
    # 2️⃣ POST überschreibt GET (manuelle Änderung)
    if request.method == "POST":
        try:
            servings = int(request.POST.get("servings", servings))
        except (TypeError, ValueError):
            pass

    servings = max(servings, 1)

    # Mengen anpassen
    adjusted_ingredients = []
    for ing in ingredients:
        if ing.quantity is not None:
            adjusted_qty = ing.quantity * servings
        else:
            adjusted_qty = None
        adjusted_ingredients.append({
            "name": ing.name,
            "unit": ing.unit,
            "quantity": adjusted_qty
        })
    return render(request, 'knowledgebase/show_recipe.html', {
        'recipe': recipe,
        'ingredients': adjusted_ingredients,
        'steps': steps,
        'servings': servings,
        'tags': tags,
    })


@login_required
@knowledge_manager_required
def edit_recipe(request, pk):
    org = request.org
    recipe = get_object_or_404(Recipe, pk=pk, owner=org)

    if request.method == "POST":
        # --- Titel, Beschreibung, Öffentlich ---
        recipe.title = request.POST.get("title", "").strip()
        recipe.description = request.POST.get("description", "").strip()
        recipe.is_public = bool(request.POST.get("is_public"))
        recipe.save()

        # --- Tags ---
        tags_input = request.POST.get("tags", "")
        recipe.tags.clear()
        for t_name in [t.strip() for t in tags_input.split(",") if t.strip()]:
            tag_obj, _ = RecipeTag.objects.get_or_create(name=t_name, owner=org)
            tag_obj.is_public = recipe.is_public
            tag_obj.save()
            recipe.tags.add(tag_obj)

        # --- Zutaten ---
        recipe.ingredients.all().delete()
        ingredient_names = request.POST.getlist("ingredient_name[]")
        ingredient_qtys = request.POST.getlist("ingredient_qty[]")
        ingredient_units = request.POST.getlist("ingredient_unit[]")
        ingredient_groups = request.POST.getlist("ingredient_group[]")
        servings = float(request.POST.get("servings", 1))
        for name, qty, unit, group in zip(ingredient_names, ingredient_qtys, ingredient_units, ingredient_groups):
            if name.strip():
                RecipeIngredient.objects.create(
                    recipe=recipe,
                    name=name.strip(),
                    quantity=float(qty) / servings if qty else None,
                    unit=unit.strip(),
                    product_group=int(group) if group else None
                )

        # --- Schritte ---
        recipe.steps.all().delete()
        steps = request.POST.getlist("step_description[]")
        for s in steps:
            if s.strip():
                RecipeStep.objects.create(recipe=recipe, description=s.strip())

        messages.success(request, f"Rezept {recipe.title} aktualisiert.")
        return redirect("my_recipes")

    # --- GET ---
    ingredient_data = [
        {
            "name": i.name,
            "quantity": i.quantity,
            "unit": i.unit,
            "product_group": str(i.product_group) if i.product_group is not None else ""
        }
        for i in recipe.ingredients.all()
    ]

    step_data = [
        {"description": s.description} for s in recipe.steps.all()
    ]
    tags_list = [t.name for t in recipe.tags.all()]
    return render(request, "knowledgebase/edit_recipe.html", {
        "recipe": recipe,
        "ingredient_data_json": json.dumps(ingredient_data, cls=DjangoJSONEncoder),
        "step_data_json": json.dumps(step_data, cls=DjangoJSONEncoder),
        "tags_list": tags_list,  # für die Badges und Input
    })


@login_required
@knowledge_manager_required
def delete_recipe(request, pk):
    recipe = get_object_or_404(Recipe, pk=pk, owner=request.org)

    if request.method == "POST":
        recipe.delete()
        messages.success(request, f"Rezept '{recipe.title}' gelöscht.")
        return redirect("my_recipes")

    return render(request, "knowledgebase/delete_recipe.html", {"recipe": recipe})
