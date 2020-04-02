import os
from datetime import datetime

from re import sub

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Value
from django.db.models.functions import Substr, Concat

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Campaign.settings")
import django
django.setup()

from TalkToTen.models import Household
from Campaign.settings import BASE_DIR
import urllib.request
import urllib.parse
import json

def safeInt(str, default=None):
    if (str):
        return int(str)
    else:
        return default

for household in Household.objects.exclude(latitude__isnull=False, longitude__isnull=False).order_by('street', 'house_number', 'house_number_suffix'):
    addr = str(household.house_number)+household.house_number_suffix+" "+household.street+", Somerville, MA "+household.zip_code
    print(addr)
    url = "http://www.datasciencetoolkit.org/street2coordinates/"+urllib.parse.quote(addr)
    response = urllib.request.urlopen(url)
    str_response = response.read().decode('utf-8')
    results = json.loads(str_response)
    data = results[addr]
    if (data is None):
        print("ERROR, SKIPPING: NO GEOCODE ADDRESS FOR "+addr)
    else:
            latitude = data['latitude']
            longitude = data['longitude']
    if ((latitude is not None) and (longitude is not None)):
        household.latitude = latitude
        household.longitude = longitude
        household.save()
    continue

from django.db import transaction




