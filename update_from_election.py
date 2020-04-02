import os
from datetime import datetime

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

# prefix for scratchwork
notes_prefix = '$!%'

# change to be the election txt file
csvfile = open(os.path.join(BASE_DIR, 'Campaign', 'data', '20171107elec.txt'))
data_reader = csv.reader(csvfile, delimiter='|', quotechar='"')
next(data_reader)  # skip first line

from django.db import transaction

Resident.objects.all().update(voted_2017_11_07=False)
num_processed = 0

def process_next_line(data_reader):
    global num_processed

    try:
        row = next(data_reader)
    except StopIteration:
        return False
    rowiter = iter(row)

    next(rowiter) # skip party affiliation
    resident_id_number = next(rowiter) # VoterID

    try:
        resident = Resident.objects.get(resident_id_number=resident_id_number)
    except ObjectDoesNotExist:
        print("UH OH PERSON WITH ID "+resident_id_number+" DOES NOT EXIST")
        print(row)
        return True

    num_processed += 1
    resident.voted_2017_11_07=True
    resident.count_elections += 1

    resident.save()

    return True


BATCH_SIZE = 500
count = 0
more_data = True
while more_data:
    with transaction.atomic():
        print('--------------------',count)
        while more_data:
            count += 1
            more_data = process_next_line(data_reader)
            if (count % BATCH_SIZE) == 0:
                break


print ("PROCESSED "+str(num_processed)+" RESIDENTS")




