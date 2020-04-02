import os
from datetime import datetime

from re import sub

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Value
from django.db.models.functions import Substr, Concat

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Campaign.settings")
import django
django.setup()

from TalkToTen.models import Household, GeoEdge
from django.db.models import F

from Campaign.settings import BASE_DIR


from django.db import transaction

cnt = 0
print('Households')
for household in Household.objects.filter(geo_edge__isnull=True):
    cnt += 1
    if (cnt % 100 == 0):
        print(cnt)
    edge = GeoEdge.objects.filter(
        street=household.street
    ).annotate(
        dist=(69. * (household.latitude - (0.5 * (F('start_node__latitude') + F('end_node__latitude'))))) ** 2 +
             (51. * (household.longitude - (0.5 * (F('start_node__longitude') + F('end_node__longitude'))))) ** 2
    ).order_by('dist').first()
    if edge is None:
        print("CANNOT FIND GEOEDGE FOR HOUSEHOLD", household.address)
    else:
        household.geo_edge = edge
        household.save()




