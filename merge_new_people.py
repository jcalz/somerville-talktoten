import os
import socket
from datetime import datetime

from re import sub

from decimal import Decimal
from urllib.error import HTTPError, URLError

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Value, F, IntegerField
from django.db.models.functions import Substr, Concat, Cast
import urllib.request
import urllib.parse
import json
from itertools import groupby


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Campaign.settings")
import django
django.setup()

from TalkToTen.models import Resident, Household, StreetSegment
from Campaign.settings import BASE_DIR
import csv

# prefix for scratchwork

month_string = '201909'
notes_suffix = ' (NotPresent' + month_string + ')'
file_name = 'updatedvoter-'+month_string+'.txt'

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


def closest_street_segment(household):
    closest = Household.objects.filter(street_segment__isnull=False).annotate(sqdist=
                               1.835*(F('latitude')-household.latitude)*(F('latitude')-household.latitude)+
                               (F('longitude')-household.longitude)*(F('longitude')-household.longitude)).order_by("-sqdist").first()
    if (closest):
        return closest.street_segment
    return None



from django.db import transaction

def geocode_household(household):
    import time
    latitude = None
    longitude = None
    # first see if existing household
    existing_house = Household.objects.filter(
        longitude__isnull=False,
        latitude__isnull=False,
        house_number=household.house_number,
        house_number_suffix=household.house_number_suffix,
        street=household.street,
        ward_number=household.ward_number,
        zip_code=household.zip_code
    ).first()
    if existing_house:
        latitude = existing_house.latitude
        longitude = existing_house.longitude
    else:
        addr = str(household.house_number) + (" " if household.house_number_suffix[:1].isdigit() else "") + \
               household.house_number_suffix + " " + household.street
        print("    GEOCODING "+addr)
        url = "https://geocoding.geo.census.gov/geocoder/locations/address?street=" + urllib.parse.quote(
            addr) + "&city=Somerville&state=MA&zip=" + urllib.parse.quote(
            household.zip_code)+"&benchmark=Public_AR_Current&format=json"

        delay = 0.001
        str_response = ""
        while True:
            code = 200
            try:
                response = urllib.request.urlopen(url, None, 8)
                str_response = response.read().decode('utf-8')
            except socket.timeout as e:
                code = 500
            except HTTPError as e:
                code = e.code
            except URLError as e:
                code = 0
            if (code != 500 or delay > 5):
                break
            time.sleep(delay)
            print("    GEOCODING DELAY " + addr)
            delay *= 2

        try:
            addressMatch = json.loads(str_response)['result']['addressMatches'][0]
        except:
            addressMatch = None

        try:
            isSomerville = addressMatch['addressComponents']['city'].lower() == 'somerville'
        except:
            isSomerville = False

        if isSomerville:
            latitude = addressMatch['coordinates']['y']
            longitude = addressMatch['coordinates']['x']
        else:
            print("    GEOCODE no geocode for ",household.address)
            existing_houses = Household.objects.filter(
                longitude__isnull=False,
                latitude__isnull=False,
                street=household.street,
                ward_number=household.ward_number
            ).order_by("house_number")
            if not existing_houses:
                print("    GEOCODE cannot geocode and no existing street, do manually")
            else:
                fh = existing_houses.first()
                latitude = fh.latitude
                longitude = fh.longitude
                lh = existing_houses.last()
                hndist = lh.house_number - fh.house_number
                if hndist != 0:
                    frac = Decimal(float((household.house_number - fh.house_number))/float(hndist))
                    latitude += frac * (lh.latitude - fh.latitude)
                    longitude += frac * (lh.longitude - fh.longitude)
                    print("   GEOCODE set",household.address,"coords interpolated between",fh.address,"and",lh.address)
                else:
                    print("   GEOCODE set",household.address,"coords to same as",fh.address)

    if ((latitude is not None) and (longitude is not None)):
        household.latitude = latitude
        household.longitude = longitude
        print("    GEOCODE added lat/lng for "+household.address)
    else:
        print("GEOCODE ERROR!!!!, SKIPPING: NO GEOCODE ADDRESS FOR " + household.address)

def others_at_same_address(household):
    MAX_OTHERS_LISTED = 5
    residents = list(household.resident_set.all())
    res_suffix = '...' if len(residents) > (MAX_OTHERS_LISTED + 1) else ''
    res_names = [resident.full_display_name + ' (' + str(resident.age) + ')' for resident in
                 residents[:MAX_OTHERS_LISTED + 1]]
    for (idx, resident) in enumerate(residents):
        other_residents = ', '.join(res_names[:idx] + res_names[idx + 1:]) + res_suffix
        resident.other_residents_at_address = other_residents
        print("    OTHERS AT RESIDENCE updated for ",resident)
        resident.save()

def assign_to_street_segment(household):
    segments = StreetSegment.objects.filter(ward_number=household.ward_number, street_name=household.street).order_by('house_number_min')
    segment = None
    if not segments:
        print ('    STREET_SEGMENT no street segment for ',household.address)
        segment = StreetSegment()
        segment.ward_number = household.ward_number
        segment.street_name = household.street
        segment.house_number_min = household.house_number
        segment.house_number_max = household.house_number
        closest_segment = closest_street_segment(household)
        if not closest_segment:
            print("STREET_SEGMENT ERROR!!!!! CANNOT FIND CLOSEST SEGMENT TO HOUSE ",household, "ASSIGNING DUMMY ORDERING 0")
            segment.ordering = 0
        else:
            next_seg = StreetSegment.objects.filter(ordering__gt=closest_segment.ordering).order_by("ordering").first()
            next_ordering = next_seg.ordering if next_seg else closest_segment.ordering+2
            segment.ordering = int((closest_segment.ordering+next_ordering)/2)
        print("    STREET_SEGMENT assigning new segment for ",household,"with ordering",segment.ordering)
        segment.save()
    else:
        segment = segments[0]
        if (segment.house_number_min > household.house_number):
            print("    STREET_SEGMENT Extended street segment min to",household.house_number,"for segment",segment)
            segment.house_number_min = household.house_number
            segment.save()
        else:
            for segment in segments:
                if (segment.house_number_min <= household.house_number) and (segment.house_number_max >= household.house_number):
                    break
            if (segment.house_number_max < household.house_number):
                print("    STREET_SEGMENT Extended street segment max to", household.house_number, "for segment", segment)
                segment.house_number_max = household.house_number
                segment.save()

    household.street_segment = segment
    print("    STREET_SEGMENT Assigned household",household,"to segment", segment)

def is_a_building(household):
    return household.resident_set.all().count()>=20 or Household.objects.all().filter(
        street=household.street,
        ward_number=household.ward_number,
        house_number=household.house_number,
        house_number_suffix=household.house_number_suffix
    ).count()>=5


modified_households = set()



def run_job():
    num_added = 0
    num_modified = 0
    num_deleted = 0

    print("caching residents")
    all_residents = Resident.objects.all()
    # [r for r in all_residents]
    print("caching households")
    all_households = Household.objects.all()
    # [h for h in all_households]
    print("starting")

    csvfile = open(os.path.join(BASE_DIR, 'Campaign', 'data', file_name))
    data_reader = csv.reader(csvfile, delimiter='|', quotechar='"')
    next(data_reader)  # skip first line
    # mark all existing users who have voted at least once
    Resident.objects.filter(count_elections__gte=1).update(notes=Concat('notes',Value(notes_suffix)))

    # Go through the new data, add new people if not existing,
    # and remove the prefix for these people

    BATCH_SIZE = 500
    count = 0

    for row in data_reader:
        count += 1
        if (count % BATCH_SIZE == 0):
            print(count)
            yield

        rowiter = iter(row)
        next(rowiter)  # skip Record Sequence Number

        resident_id_number = next(rowiter)  # VoterID

        already_here = False

        try:
            resident = all_residents.get(resident_id_number=resident_id_number)
            already_here = True
            if resident.notes.endswith(notes_suffix):
                resident.notes = resident.notes[:-len(notes_suffix):]
        except ObjectDoesNotExist:
            resident = Resident()
            resident.resident_id_number = resident_id_number
            resident.voted_2016_11_08 = False
            resident.to_canvass = True

        props = dict()

        props['last_name'] = next(rowiter).title()  # Last
        props['first_name'] = next(rowiter).title()  # First
        next(rowiter)  # middle name
        next(rowiter)  # title


        hn = safeInt(next(rowiter))
        hns = next(rowiter)
        s = next(rowiter).title()
        an = next(rowiter)
        z = fix_zip_code(next(rowiter))

        next(rowiter)  # mailing addr st num and name
        next(rowiter)  # mailing addr apt number
        next(rowiter)  # mailing addr city
        next(rowiter)  # mailing addr state
        next(rowiter)  # mail addr zip

#        props['occupation'] = next(rowiter).title() # Occupation

        party = next(rowiter).strip()  # Party
        if party not in (p for (p, _) in Resident.PARTY_CHOICES):
            party = Resident.OTHER
        props['party_affiliation'] = party


        dob = next(rowiter)  # DOB
        if dob:
            props['date_of_birth'] = datetime.strptime(dob, '%m/%d/%Y').date()


 #       props['nationality'] = next(rowiter).title() # Nationality

 #       props['gender'] = next(rowiter)

        next(rowiter)  # date of registration

        wn = safeInt(next(rowiter))
        pn = safeInt(next(rowiter))
        try:
            household = all_households.get(house_number=hn, house_number_suffix=hns, street=s, apartment_number=an)
        except ObjectDoesNotExist:
            household = Household()
            household.house_number = hn
            household.house_number_suffix = hns
            household.street = s
            household.apartment_number = an
            household.zip_code = z
            household.ward_number = wn
            household.precinct_number = pn
            household.is_a_building = is_a_building(household)
            geocode_household(household)
            assign_to_street_segment(household)
            household.save()
            print("    HOUSEHOLD created", household, "is" if household.is_a_building else "is not", "a building")

        if (resident.household != household):
            if (resident.household):
                modified_households.add(resident.household)
            if (household):
                modified_households.add(household)

        props['household'] = household

        changed_props = []
        for k in props:
            old = getattr(resident, k)
            new = props[k]
            if already_here and old != new:
                changed_props.append(
                    k.replace('_number', '').replace('_affiliation', '') + ' from "' + str(old) + '" to "' + str(
                        new) + '"')
            setattr(resident, k, new)
        if changed_props:
            num_modified += 1
            print('  RESIDENT: CHANGED "' + str(resident) + '": ' + '; '.join(changed_props))

        if not already_here:
            num_added += 1
            print('  RESIDENT: ADDED "' + str(resident) + '"')

        resident.save()


    # Now, any people who still have the prefix were prev voters not touched.
    to_delete = Resident.objects.filter(notes__endswith=notes_suffix)
    num_deleted = to_delete.count()
    #for resident in to_delete:
    #    modified_households.add(resident.household)
    #    print ('  RESIDENT: DELETED "'+str(resident)+'"')
    #to_delete.delete()


    # Finally, update others-in-household for modified households
    for household in modified_households:
        count += 1
        if (count % BATCH_SIZE == 0):
            print(count)
            yield
        others_at_same_address(household)


    print('--------------------------------------')
    print ("ADDED "+str(num_added)+" RESIDENTS")
    print ("MODIFIED "+str(num_modified)+" RESIDENTS")
    print ("WOULD HAVE DELETED "+str(num_deleted)+" RESIDENTS")



gen = run_job()
try:
    while True:
        with transaction.atomic():
            next(gen)
except StopIteration:
    print('done')

