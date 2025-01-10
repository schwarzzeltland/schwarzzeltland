from django.forms import ModelForm

from events.models import Trip
class TripForm(ModelForm):

    def __init__(self, *args, **kwargs):
        organization = kwargs.pop('organization', None)
        super(TripForm, self).__init__(*args, **kwargs)
        self.instance.organization = organization

    class Meta:
        model = Trip
        fields = '__all__'

