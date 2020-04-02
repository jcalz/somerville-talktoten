import os
from datetime import datetime

from re import sub

from django.core.exceptions import ObjectDoesNotExist
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Campaign.settings")
import django
django.setup()

from TalkToTen.models import Resident
from Campaign.settings import BASE_DIR
import csv


def safeInt(str, default=None):
    if (str):
        return int(str)
    else:
        return default

def fix_zip_code(str: str) -> str:
    if (not str):
        return str
    zip = sub('\D', '', str)
    plusfour = None
    if (len(zip) > 5):
        plusfour = zip[-4:]
        zip = zip[:-4]
    zip = zip.zfill(5)
    if (plusfour):
        zip = zip + '-' + plusfour
    return zip

def title_university(str: str) -> str:
    ret = str.title()
    if (ret == 'Mit'):
        return 'MIT'
    return ret


csvfile = open(os.path.join(BASE_DIR, 'Campaign', 'data', 'census.csv'))
data_reader = csv.reader(csvfile, delimiter=',', quotechar='"')
next(data_reader)  # skip first line

from django.db import transaction

def process_next_line(data_reader):
    try:
        row = next(data_reader)
    except StopIteration:
        return False
    rowiter = iter(row)

    next(rowiter) # ignore Kickoff field
    next(rowiter) # ignore RSVPStatus field
    next(rowiter) # ignore Followup field
    next(rowiter) # ignore TalktoTen field
    next(rowiter) # ignore MailChimp field

    no_email = bool(safeInt(next(rowiter))) # NoEmail
    next(rowiter) # ignore EmailBounch field

    resident_id_number = next(rowiter) # VoterID

    try:
        resident = Resident.objects.get(resident_id_number=resident_id_number)
    except ObjectDoesNotExist:
        resident = Resident()
        resident.resident_id_number = resident_id_number

    resident.does_not_want_to_receive_email = no_email

    resident.count_elections = next(rowiter) # .Elections
    resident.voted_recent_municipal = bool(safeInt(next(rowiter))) # Municipal

    resident.email = next(rowiter) # Email
    resident.phone = next(rowiter) # Phone

    last_name = next(rowiter).title() # Last
    resident.last_name = last_name
    first_name = next(rowiter).title() # First
    resident.first_name = first_name

    dob = next(rowiter) # DOB
    if dob:
        resident.date_of_birth = datetime.strptime(dob, '%m/%d/%Y %H:%M:%S')


    resident.household.house_number = safeInt(next(rowiter)) # Street
    resident.household.house_number_suffix = next(rowiter) # Street.Suffix

    street = next(rowiter) # StreetName
    # we need an address
    if not street:
        return True

    resident.household.street = street.title() # StreetName
    next(rowiter) # ignore StreetNameShort field
    resident.household.apartment_number = next(rowiter) # Unit
    resident.household.zip_code = fix_zip_code(next(rowiter)) # Zip

    resident.occupation = next(rowiter).title() # SumProfession

    party = next(rowiter) # Party
    if party not in (p for (p,_) in Resident.PARTY_CHOICES):
        party = Resident.OTHER

    resident.party_affiliation = party
    resident.nationality = next(rowiter).title() # SumNationality
    resident.gender = next(rowiter) # Gender
    resident.ward_number = safeInt(next(rowiter)) # Ward
    resident.precinct_number = safeInt(next(rowiter)) # Precinct
    resident.voted_2016_11_08 = bool(safeInt(next(rowiter))) # Nov16

    resident.donor_local_amount = safeInt(next(rowiter), 0) # LocalDonor_Total
    resident.donor_local_progressive_percent = safeInt(next(rowiter), 0) # LocalDonor_%Progressive
    resident.donor_federal_amount = safeInt(next(rowiter), 0) # FederalDonor_Total
    resident.donor_federal_progressive_percent = safeInt(next(rowiter), 0) # FederalDonor_%Progressive

    resident.university_affiliation_1 = title_university(next(rowiter)) # UniversityAffiliation1
    resident.university_affiliation_2 = title_university(next(rowiter)) # UniversityAffiliation2
    resident.university_affiliation_3 = title_university(next(rowiter)) # UniversityAffiliation3

    resident.child_age_1 = safeInt(next(rowiter)) # Child1
    resident.child_age_2 = safeInt(next(rowiter)) # Child2
    resident.child_age_3 = safeInt(next(rowiter)) # Child3

    resident.child_name_1 = next(rowiter).title() # Child1Name
    resident.child_name_2 = next(rowiter).title() # Child2Name

    resident.known_to_have_dog = bool(safeInt(next(rowiter))) # Animals
    resident.dog_names = next(rowiter).title() # DogNames
    resident.notes = next(rowiter) # Notes
    resident.campaign_donation_amount = safeInt(next(rowiter), 0) # CampaignDonation
    next(rowiter) #ignore Volunteer field

    resident.length_of_time_in_home = next(rowiter) #LengthOfTimeInHome

    resident.save()
    return True


BATCH_SIZE = 500
count = 0
more_data = True
while more_data:
    with transaction.atomic():
        print('--------------------')
        while more_data:
            count += 1
            if count % 100 == 0:
                print(count)
            more_data = process_next_line(data_reader)
            if (count % BATCH_SIZE) == 0:
                break





