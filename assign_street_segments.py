import os
from datetime import datetime

from re import sub

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Value
from django.db.models.functions import Substr, Concat

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Campaign.settings")
import django
django.setup()

from TalkToTen.models import Resident, Household, StreetSegment
from Campaign.settings import BASE_DIR
import csv



from django.db import transaction

cnt = 0
for household in Household.objects.filter(street_segment__isnull=True):
    cnt += 1
    try:
        street_segment = StreetSegment.objects.get(ward_number=household.ward_number, street_name=household.street, house_number_max__gte=household.house_number, house_number_min__lte=household.house_number)
    except ObjectDoesNotExist:
        street_segment = None
        print('no street segment for ',household.address)
    if street_segment:
        household.street_segment = street_segment
        household.save()
    print(cnt)





