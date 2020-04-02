import os
from datetime import datetime
from itertools import groupby

from re import sub

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Value
from django.db.models.functions import Substr, Concat

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Campaign.settings")
import django

django.setup()

from TalkToTen.models import Resident
from Campaign.settings import BASE_DIR
import csv

from django.db import transaction

def run_job():
    MAX_OTHERS_LISTED = 5
    cnt = 0
    for (household, resgen) in groupby(Resident.objects.order_by('household',
                                                                 'last_name',
                                                                 'first_name'),
                                       lambda r: r.household):
        residents = list(resgen)
        res_suffix = '...' if len(residents) > (MAX_OTHERS_LISTED + 1) else ''
        res_names = [resident.full_display_name + ' (' + str(resident.age) + ')' for resident in
                     residents[:MAX_OTHERS_LISTED + 1]]
        for (idx, resident) in enumerate(residents):
            other_residents = ', '.join(res_names[:idx] + res_names[idx + 1:]) + res_suffix
            resident.other_residents_at_address = other_residents
            resident.save()
            cnt += 1
            if (cnt % 500 == 0):
                print(cnt)
                yield
    yield

gen = run_job()

try:
    while True:
        with transaction.atomic():
            next(gen)
except StopIteration:
    print('done')