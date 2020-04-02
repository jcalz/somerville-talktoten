import random
from datetime import datetime, timedelta, date


import dateutil
import math
from dateutil.relativedelta import relativedelta
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from re import sub

from django.db.models import Sum, Max
from django.db.models.functions import Cast
from django.db.models.manager import Manager
from django.forms.fields import ChoiceField, IntegerField
from django.forms.widgets import TextInput

from django.utils import timezone

from Campaign.utils import index_min, index_max
from typing import Union, Iterable, Optional, List, Dict, Set, MutableSequence, DefaultDict, Tuple

class SupportLevels:
    DEFINITE_SUPPORTER = 1
    POSSIBLE_SUPPORTER = 2
    NEUTRAL = 3
    POSSIBLE_OPPONENT = 4
    DEFINITE_OPPONENT = 5
    CHOICES = (
        (None, 'Unknown'),
        (DEFINITE_SUPPORTER, 'Definite support'),
        (POSSIBLE_SUPPORTER, 'Possible support'),
        (NEUTRAL, 'Undecided'),
        (POSSIBLE_OPPONENT, 'Not really interested'),
        (DEFINITE_OPPONENT, 'Definitely not interested')
    )


class ContactRecordActionChoices:
    SEND_MAIL = 'mail'
    FOLLOW_UP = 'follow'
    NO_FOLLOW_UP = 'nofollow'
    RELINQUISH = 'remove'

class ContactTypeChoices:
    CANVASS = 'Canvass'
    HOUSE_PARTY = 'House party'
    POST_CARD = 'Post card'
    PHONE_CALL = 'Phone call'
    TALK_TO_TEN = 'Talk to ten'
    EMAIL = 'Email'
    EVENT = 'Event'
    OTHER = 'Other'
    CHOICES = (
        ('', 'Unknown'),
        (CANVASS, 'Canvass'),
        (HOUSE_PARTY, 'House party'),
        (POST_CARD, 'Post card'),
        (PHONE_CALL, 'Phone call'),
        (EMAIL, 'Email'),
        (EVENT, 'Event'),
        (TALK_TO_TEN, 'Talk to Ten'),
        (OTHER, 'Other'),
    )

class FacebookStatus:
    UNCHECKED = 'U'
    NO_FB_ACCOUNT = 'N'
    FRIEND_REQUEST = 'R'
    FRIEND = 'F'
    CHOICES = (
        (UNCHECKED, 'Unchecked'),
        (NO_FB_ACCOUNT, 'No Facebook Account'),
        (FRIEND_REQUEST, 'Sent Friend Request'),
        (FRIEND, 'Friend'),
    )

from collections import namedtuple
PollingPlace = namedtuple("PollingPlace", ["ward_number","precinct_number","name","address"])
PollingPlaces = (
    PollingPlace(ward_number=1, precinct_number=1, address="150 Glen Street",
                 name="Michael E. Capuano School"),
    PollingPlace(ward_number=1, precinct_number=2, address="50 Cross St. (Glen St. Entrance)",
                 name="East Somerville Community School"),
    PollingPlace(ward_number=1, precinct_number=3, address="50 Cross St. (Glen St. Entrance)",
                 name="East Somerville Community School"),
    PollingPlace(ward_number=2, precinct_number=1, address="220 Washington Street",
                 name="Police Station"),
    PollingPlace(ward_number=2, precinct_number=2, address="290 Washington Street",
                 name="Albert F. Argenziano School"),
    PollingPlace(ward_number=2, precinct_number=3, address="651 Somerville Avenue",
                 name="Lowell Street Fire Station"),
    PollingPlace(ward_number=3, precinct_number=1, address="81 Highland Avenue",
                 name="Atrium at Somerville High School"),
    PollingPlace(ward_number=3, precinct_number=2, address="81 Highland Avenue",
                 name="Atrium at Somerville High School"),
    PollingPlace(ward_number=3, precinct_number=3, address="5 Dante Terrace", name="Dante Club"),
    PollingPlace(ward_number=4, precinct_number=1, address="530 Mystic Avenue",
                 name="Mystic Activity Center"),
    PollingPlace(ward_number=4, precinct_number=2, address="115 Sycamore Street",
                 name="Winter Hill Community School"),
    PollingPlace(ward_number=4, precinct_number=3, address="115 Sycamore Street",
                 name="Winter Hill Community School"),
    PollingPlace(ward_number=5, precinct_number=1, address="17 Franey Road",
                 name="DPW Water Department Building"),
    PollingPlace(ward_number=5, precinct_number=2, address="201 Willow Ave. (Kidder Ave. Entrance)",
                 name="Brown School"),
    PollingPlace(ward_number=5, precinct_number=3, address="265 Highland Avenue",
                 name="Engine 7 Fire Station"),
    PollingPlace(ward_number=6, precinct_number=1, address="5 Cherry St. (Main Entrance & Sartwell Ave. Entrance)",
                 name="John F. Kennedy School"),
    PollingPlace(ward_number=6, precinct_number=2, address="31 College Avenue",
                 name="Somerville Community Baptist Church"),
    PollingPlace(ward_number=6, precinct_number=3, address="14 Chapel Street",
                 name="Holy Bible Baptist Church"),
    PollingPlace(ward_number=7, precinct_number=1, address="167 Holland Street",
                 name="Tufts Administration Building (TAB)"),
    PollingPlace(ward_number=7, precinct_number=2, address="177 Powder House Boulevard",
                 name="West Somerville Neighborhood School"),
    PollingPlace(ward_number=7, precinct_number=3, address="405 Alewife Brook Parkway",
                 name="Visiting Nurse Association")
)


class StreetSegment(models.Model):
    ward_number = models.PositiveIntegerField()
    street_name = models.CharField(max_length=255)
    house_number_min = models.PositiveIntegerField()
    house_number_max = models.PositiveIntegerField()
    ordering = models.PositiveIntegerField(db_index=True)
    def __str__(self):
        house_range = str(self.house_number_min)
        if (self.house_number_min != self.house_number_max):
            house_range += '-' + str(self.house_number_max)
        return house_range + ' ' + self.street_name+", Ward "+str(self.ward_number)+" [SEG"+str(self.id).zfill(4)+"]"

class Household(models.Model):
    class Meta:
        index_together = [["street","house_number","house_number_suffix"]]
    house_number = models.PositiveIntegerField(blank=True, null=True)
    house_number_suffix = models.CharField(max_length=30, blank=True)
    street = models.CharField(max_length=255, blank=True, db_index=True)
    apartment_number = models.CharField(max_length=30, blank=True)
    zip_code = models.CharField(max_length=30, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    street_segment = models.ForeignKey(StreetSegment, blank=True, null=True)
    ward_number = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    precinct_number = models.PositiveSmallIntegerField(null=True, blank=True)
    is_a_building = models.BooleanField(default=False)

    geo_edge = models.ForeignKey('GeoEdge', blank=True, null=True)

    @property
    def x(self):
        # noinspection PyTypeChecker
        return (float(self.longitude) + 71.0995) * 51.0

    @property
    def y(self):
        # noinspection PyTypeChecker
        return (float(self.latitude) - 42.3876) * 69.0

    def euclidean_distance(self, other_node: Union['GeoNode','Household']) -> float:
        return ((self.x - other_node.x)**2 + (self.y - other_node.y)**2) ** 0.5

    @property
    def address(self):
        if (not self.street):
            return "Unknown Address"
        addr = str(self.house_number) + self.house_number_suffix + ' ' + self.street
        if (self.apartment_number):
            addr += ' #' + self.apartment_number
        return sub('\s+', ' ', addr).strip()

    @property
    def polling_place(self):
        return next((p for p in PollingPlaces if p.ward_number==self.ward_number and p.precinct_number==self.precinct_number), None)

    def __str__(self):
        return self.address



class Volunteer(Household):
    class Meta:
        proxy = True


class Resident(models.Model):


    user = models.OneToOneField(User, null=True, blank=True)

    # voted in 2017 election
    voted_2017_11_07 = models.BooleanField(default=False)

    # voted in 2018 primary
    voted_2018_09_04 = models.BooleanField(default=False)

    # voter in 2018 election
    voted_2018_11_06 = models.BooleanField(default=False)

    YARD_SIGN_NO = ''
    YARD_SIGN_YES = 'Y'
    YARD_SIGN_REQUESTED = 'R'
    YARD_SIGN_CHOICES = (
        (YARD_SIGN_NO, 'No'),
        (YARD_SIGN_YES, 'Yes'),
        (YARD_SIGN_REQUESTED, 'Requested')
    )
    yard_sign = models.CharField(max_length=20, blank=True, choices=YARD_SIGN_CHOICES)

    level_of_support = models.PositiveSmallIntegerField(blank=True, null=True, choices=SupportLevels.CHOICES)
    level_of_support_ilana = models.PositiveSmallIntegerField(blank=True, null=True, choices=SupportLevels.CHOICES)


    count_elections = models.PositiveSmallIntegerField(default=0)

    resident_id_number = models.CharField(max_length=12, db_index=True)
    email = models.EmailField(blank=True)

    does_not_want_to_receive_email = models.BooleanField(default=False)

    phone = models.CharField(max_length=30, blank=True)
    phone_came_from_van = models.BooleanField(default=False)

    # name
    last_name = models.CharField(max_length=255, blank=True)
    first_name = models.CharField(max_length=255, blank=True)

    date_of_birth = models.DateField(null=True, blank=True)

    # address


    occupation = models.CharField(max_length=255, blank=True)

    DEMOCRAT = 'D'
    REPUBLICAN = 'R'
    UNAFFILIATED = 'U'
    GREEN = 'G'
    OTHER = 'O'
    PARTY_CHOICES = (
        (DEMOCRAT, 'Democrat'),
        (UNAFFILIATED, 'Unaffiliated'),
        (REPUBLICAN, 'Republican'),
        ('', 'Unregistred'),
        (GREEN, 'Green'),
        (OTHER, 'Other')
    )
    party_affiliation = models.CharField(max_length=2, blank=True, choices=PARTY_CHOICES)
    nationality = models.CharField(max_length=255, blank=True)

    FEMALE = 'F'
    MALE = 'M'
    GENDER_CHOICES = (
        ('', 'Unknown'),
        (FEMALE, 'Female'),
        (MALE, 'Male')
    )
    gender = models.CharField(max_length=1, blank=True, choices=GENDER_CHOICES)

    # voting record
    voted_2016_11_08 = models.BooleanField()
    voted_recent_municipal = models.BooleanField(default=False)

    donor_local_amount = models.PositiveIntegerField(default=0)
    donor_local_progressive_percent = models.PositiveSmallIntegerField(default=0)
    donor_federal_amount = models.PositiveIntegerField(default=0)
    donor_federal_progressive_percent = models.PositiveSmallIntegerField(default=0)


    university_affiliation_1 = models.CharField(max_length=255, blank=True)
    university_affiliation_2 = models.CharField(max_length=255, blank=True)
    university_affiliation_3 = models.CharField(max_length=255, blank=True)

    child_age_1 = models.PositiveSmallIntegerField(null=True, blank=True)
    child_name_1 = models.CharField(max_length=255, blank=True)

    child_age_2 = models.PositiveSmallIntegerField(null=True, blank=True)
    child_name_2 = models.CharField(max_length=255, blank=True)

    child_age_3 = models.PositiveSmallIntegerField(null=True, blank=True)
    child_name_3 = models.CharField(max_length=255, blank=True)

    notes = models.TextField(blank=True)


    length_of_time_in_home = models.CharField(max_length=255, blank=True)

    known_to_have_dog = models.BooleanField(default=False)
    dog_names = models.CharField(max_length=255, blank=True)

    campaign_donation_amount = models.PositiveIntegerField(default=0)

    needs_followup = models.BooleanField(default=False)

    to_canvass = models.BooleanField(default=False)
    canvass_complete = models.BooleanField(default=False)
    canvass_complete_2017 = models.BooleanField(default=False)
    gotv_canvass_complete = models.BooleanField(default=False)
    canvass_complete_ilana = models.BooleanField(default=False)

    facebook_status = models.CharField(max_length=1, blank=False, null=False, choices=FacebookStatus.CHOICES, default=FacebookStatus.UNCHECKED)

    household = models.ForeignKey(Household, null=True)
    other_residents_at_address = models.TextField(blank=True)



    # volunteer options
    volunteer_option_canvass = models.BooleanField(default=False)
    volunteer_option_gotv = models.BooleanField(default=False)
    volunteer_option_election_day = models.BooleanField(default=False)
    volunteer_option_dear_friend = models.BooleanField(default=False)
    volunteer_option_needs_followup = models.BooleanField(default=False)

    # categories
    category_it = models.BooleanField(default=False)
    category_fams = models.BooleanField(default=False)
    category_dems = models.BooleanField(default=False)
    category_gotv = models.BooleanField(default=False)
    category_election_day_gotv = models.BooleanField(default=False)



    def __str__(self):

        return self.full_display_name + ' @ ' + self.resident_address
        #       return '{o.first_name} {o.last_name}'.format(o=self)

    @property
    def full_display_name(self):
        n = '{o.first_name} {o.last_name}'.format(o=self)
        return sub('[\s]+', ' ', n).strip()

    @property
    def contacts(self):
        return ', '.join(
            [c.contacter.get_full_name() or c.contacter.get_username()
             for c in self.contactrecord_set.select_related('contacter')])

    @property
    def resident_address(self):
        return self.household.address

    @property
    def identifying_information(self):
        return self.full_display_name + ' at ' + self.resident_address + ", " + self.household.zip_code

    @property
    def age(self):
        if (not self.date_of_birth):
            return None
        return relativedelta(date.today(),self.date_of_birth).years


def add_tag_to_resident_id_set(resident_ids, tag):
    count = 0
    existing = set(Resident.objects.filter(residenttag__tag=tag).values_list('id', flat=True).distinct())
    with transaction.atomic():
        for resident_id in resident_ids:
            if resident_id not in existing:
                ResidentTag.objects.create(resident_id=resident_id, tag=tag)
                count += 1
    return count

def remove_tag_from_resident_id_set(resident_ids, tag):
    count = 0
    residents_left = resident_ids
    with transaction.atomic():
        while residents_left:
            chunk = residents_left[:100]
            deleted = ResidentTag.objects.filter(resident_id__in=chunk, tag=tag).delete()
            count += deleted[0]
            residents_left = residents_left[100:]
    return count

class Event(models.Model):
    name = models.CharField(max_length=255)
    date = models.DateTimeField(null=True, blank=True)

class ContactRecordManager(Manager):

    def pending_contacts_for_user(self, user):
        return self.filter(contacter=user, status=ContactRecord.PENDING)

    def resident_available_for_match(self, resident):
        return not self.filter(resident=resident, status__in=[ContactRecord.PENDING, ContactRecord.COMPLETE])

def get_steph_id():
    return User.objects.filter(username='shirsch').values_list('id', flat=True).first()

def default_follow_up_date():
    return date.today() + timedelta(days=30)


class ContactRecord(models.Model):

    objects = ContactRecordManager()

    contacter = models.ForeignKey(User, default=get_steph_id)  # requires a user
    resident = models.ForeignKey(Resident) #requires a resident
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    level_of_support = models.PositiveSmallIntegerField(blank=True, null=True, choices=SupportLevels.CHOICES)

    notes = models.TextField(blank=True)

    contact_date = models.DateField(default=date.today, blank=True, null=True)

    contact_type = models.CharField(max_length=20, blank=True, choices=ContactTypeChoices.CHOICES)

    follow_up_date = models.DateField(default=default_follow_up_date, blank=True, null=True)
    open = models.BooleanField(default=True)


    interest_area_envir = models.BooleanField(verbose_name='Environment/climate change', default=False)
    interest_area_trans = models.BooleanField(verbose_name='Transit, infrastructure, and traffic calming', default=False)
    interest_area_commu = models.BooleanField(
        verbose_name='Community and youth infrastructure (fields, recreation, programming, libraries, community theater, etc.)', default=False)
    interest_area_parks = models.BooleanField(verbose_name='Open space, parks, urban farming, off-leash areas.', default=False)
    interest_area_zonin = models.BooleanField(verbose_name='Zoning/housing/development issues', default=False)
    interest_area_immig = models.BooleanField(verbose_name='Immigration, equity, and poverty relief', default=False)
    interest_area_educa = models.BooleanField(verbose_name='Education and the schools', default=False)
    interest_area_addic = models.BooleanField(verbose_name='Addressing addiction and opioid abuse', default=False)
    interest_area_affor = models.BooleanField(verbose_name='Affordability', default=False)
    interest_area_busin = models.BooleanField(verbose_name='Business development', default=False)
    interest_area_artis = models.BooleanField(verbose_name='Support for artists and art in the community', default=False)
    interest_area_histo = models.BooleanField(verbose_name='Historic preservation', default=False)
    interest_area_safet = models.BooleanField(verbose_name='Public safety', default=False)
    interest_area_quali = models.BooleanField(
        verbose_name='Quality of life issues (rats, trash, airplane noise, etc.)',default=False)
    interest_area_senio = models.BooleanField(verbose_name='Issues affecting seniors', default=False)
    interest_area_smart = models.BooleanField(verbose_name='Smart city infrastructure', default=False)

    def get_interest_areas(self):
        return [f.name for f in self._meta.get_fields() if f.name.startswith('interest_area_') and getattr(self,f.name)]

    def set_interest_areas(self, value):
        for f in self._meta.get_fields():
            if f.name.startswith('interest_area_'):
                setattr(self, f.name, f.name in value)

    interest_areas = property(get_interest_areas, set_interest_areas)

    PENDING = 0
    COMPLETE = 1
    COMPLETE_BUT_UNRESERVED = 2
    STATUS_CHOICES = (
        (PENDING, 'Pending'),
        (COMPLETE, 'Complete - Close resident to new contacts'),
        (COMPLETE_BUT_UNRESERVED, 'Complete - Open resident to new contacts')
    )
    status = models.PositiveSmallIntegerField(default=COMPLETE_BUT_UNRESERVED, choices=STATUS_CHOICES)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
          return self.contacter.get_username()+' ('+self.contacter.get_full_name()+')  contacting '+str(self.resident)

    def copy_into_resident_and_mark_complete(self, contact_action=ContactRecordActionChoices.FOLLOW_UP):
        resident = self.resident
        changed = False
        if self.email and not resident.email:
            resident.email = self.email
            changed = True
        if self.phone and not resident.phone:
            resident.phone = self.phone
            changed = True
        if self.level_of_support and not resident.level_of_support:
            resident.level_of_support = self.level_of_support
            changed = True
        if self.notes.strip():
            resident.notes = (resident.notes + '\n' + self.notes).strip()
            changed = True
        if contact_action == ContactRecordActionChoices.FOLLOW_UP:
            resident.needs_followup = True
            changed = True
        if (changed):
            resident.save()
        if (self.status != ContactRecord.COMPLETE):
            self.status = ContactRecord.COMPLETE
            self.open = False
            self.save()


import collections

class ResidentTag(models.Model):
    class Meta:
        unique_together = (("resident", "tag"))
    resident = models.ForeignKey(Resident)
    tag = models.CharField(max_length=64,blank=True,null=True)

#################

class GeoNode(models.Model):
    latitude = models.FloatField()
    longitude = models.FloatField()

    @property
    def x(self):
        return (self.longitude + 71.0995) * 51.0

    @property
    def y(self):
        return (self.latitude - 42.3876) * 69.0

    @property
    def edges(self):
        if not hasattr(self, '_edges'):
            self._edges = set(
                DirectedEdge(e, self, e.end_node) for e in self.outgoing_edges.all()
            ) | set(
                DirectedEdge(e, self, e.start_node) for e in self.incoming_edges.all()
            )
        return self._edges

    def euclidean_distance(self, other_node: Union['GeoNode','Household']) -> float:
        return ((self.x - other_node.x)**2 + (self.y - other_node.y)**2) ** 0.5

    @property
    def intersection(self):
        #if hasattr(self, 'name'):
        #    return str(self.name)
        names = set(e.street for e in self.edges)
        if len(names)==0:
            return "Nowhere?!"
        elif len(names)==1:
            return "On "+names.pop()
        return "Intersection of "+','.join(names)

    def validate(self):
        pass
        # for e in self.edges:
        #     if (e.start_node != self):
        #         raise Exception("Node " + str(self.id) + " is not the start of edge " + str(e.edge))


class GeoEdge(models.Model):
    start_node = models.ForeignKey(GeoNode, related_name='outgoing_edges')
    end_node = models.ForeignKey(GeoNode, related_name='incoming_edges')
    street = models.CharField(max_length=255)
    length = models.FloatField()


class DirectedEdge:
    def __init__(self, edge: GeoEdge, start_node: GeoNode, end_node: GeoNode):
        self.edge = edge
        self.start_node = start_node
        self.end_node = end_node

    @property
    def length(self):
        return self.edge.length

    @property
    def street(self):
        return self.edge.street


class TourSegment:
    def __init__(self, journey: List[DirectedEdge] = None, goal: DirectedEdge = None,
                 goal_residents: List[Resident] = None):

        if journey is None:
            j = []
        else:
            j = journey
        self.journey = j

        self.journey_length = sum(e.length for e in j)
        self.goal = goal

        if goal_residents is None:
            gr = [] # type: List[Resident]
        else:
            gr = goal_residents
        self.goal_residents = gr

class Tour:
    def __init__(self, segments: List[TourSegment] = None):
        if segments is None:
            s = []
        else:
            s = segments
        self.segments = s  # type: List[TourSegment]

    def append_edge(self, edge: DirectedEdge, in_goal: bool):
        if len(self.segments) == 0:
            self.segments.append(TourSegment())
        cur_segment = self.segments[-1]
        if (cur_segment.goal):
            cur_segment = TourSegment()
            self.segments.append(cur_segment)
        if in_goal:
            cur_segment.goal = edge
        else:
            cur_segment.journey_length += edge.length
            cur_segment.journey.append(edge)

    def get_length(self):
        return sum(e.journey_length + e.goal.length for e in self.segments)

    @property
    def length(self):
        return self.get_length()

    @property
    def num_households(self):
        return sum(len(set(r.household.id for r in s.goal_residents)) for s in self.segments)

    @property
    def num_residents(self):
        return sum(len(set(r.id for r in s.goal_residents)) for s in self.segments)

def validate_segments(segments: List[TourSegment]):
    pass
    # # TODO make this a no-op for runtime
    # cur_node = None
    # cnt = 0
    # last_seg_no_goal = False
    # for seg in segments:
    #     if last_seg_no_goal:
    #         raise Exception("BROKEN TOUR!" + "Segment " + str(cnt) + " after empty goal")
    #     j = 0
    #     for edge in seg.journey:
    #         if (cnt == 0):
    #             raise Exception("BROKEN TOUR!" + "Segment 0 has a journey")
    #         if cur_node is None:
    #             cur_node = edge.start_node
    #         if (edge.start_node != cur_node):
    #             raise Exception("BROKEN TOUR!"+"Segment:"+str(cnt)+" journey edge:"+str(j))
    #         cur_node = edge.end_node
    #         j+=1
    #     if seg.goal:
    #         if cur_node is None:
    #             cur_node = seg.goal.start_node
    #         if (seg.goal.start_node != cur_node):
    #             raise Exception("BROKEN TOUR!" + "Segment:" + str(cnt) + " goal edge")
    #         cur_node = seg.goal.end_node
    #     else:
    #         last_seg_no_goal = True
    #     cnt += 1

class GeoGraph:
    def __init__(self):
        num = 0
        nodes_map = {n.id: n for n in GeoNode.objects.all().order_by('id')}
        for nid, n in nodes_map.items():
            n._edges = set()
            num += 1
            n.name = num

        edges_map = {e.id: e for e in GeoEdge.objects.all().select_related('start_node','end_node')}
        for eid, e in edges_map.items():
            sn = nodes_map[e.start_node.id]
            en = nodes_map[e.end_node.id]
            sn._edges.add(DirectedEdge(e, sn, en))
            en._edges.add(DirectedEdge(e, en, sn))
            e.start_node._edges = sn._edges
            e.start_node.name = sn.name
            e.end_node._edges = en._edges
            e.end_node.name = en.name

        self.nodes_map = nodes_map
        self.edges_map = edges_map

    def validate(self):
        pass
        # for nid, n in self.nodes_map.items():
        #     n.validate()


    # note, assumes "distance to closest goal node" is a consistent heuristic which is probably mostly true?  have to think
    def find_path(self, start_node: GeoNode, goal_or_goals: Union['GeoNode', Iterable['GeoNode']]) -> Optional[List['DirectedEdge']]:
        start_node = self.nodes_map[start_node.id]
        goals = [goal_or_goals] if isinstance(goal_or_goals, GeoNode) else goal_or_goals  # type: Iterable[GeoNode]

        def heuristic_cost_estimate(start_node: 'GeoNode', end_nodes: Iterable['GeoNode']):
            return min((start_node.euclidean_distance(end_node) for end_node in end_nodes), default=math.inf)

        def reconstruct_path(came_from: Dict[int, DirectedEdge], current: GeoNode) -> List[DirectedEdge]:
            total_path = collections.deque()  # type: MutableSequence[DirectedEdge]
            while current.id in came_from:
                edge = came_from[current.id]
                total_path.insert(0, edge)
                current = edge.start_node
            return list(total_path)

        closed_set = set()  # type: Set[GeoNode]
        open_set = set()  # type: Set[GeoNode]
        came_from = dict()  # type: Dict[int, DirectedEdge]
        open_set.add(start_node)
        g_score = collections.defaultdict(lambda: math.inf)  # type: DefaultDict[int, float]
        g_score[start_node.id] = 0
        f_score = collections.defaultdict(lambda: math.inf)  # type: DefaultDict[int, float]
        f_score[start_node.id] = heuristic_cost_estimate(start_node, goals)
        while open_set:
            current = min(open_set, key=lambda n: f_score[n.id])  # type: GeoNode
            #print("CURRENT:",current.intersection,"G: ",g_score[current.id],"F: ",f_score[current.id])
            if current in goals:
                return reconstruct_path(came_from, current)
            open_set.remove(current)
            closed_set.add(current)
            for edge in current.edges:
                neighbor = edge.end_node
                if neighbor in closed_set:
                    continue
                if neighbor not in open_set:
                    open_set.add(neighbor)

                tentative_g_score = g_score[current.id] + edge.length
                #print("  CONSIDERING EDGE", edge.street, "TO", neighbor.intersection, ":", tentative_g_score, "LEN: ",edge.length)
                if tentative_g_score >= g_score[neighbor.id]:
                    #print("  NOPE")
                    continue
                #print("  YES")
                came_from[neighbor.id] = edge
                g_score[neighbor.id] = tentative_g_score
                f_score[neighbor.id] = g_score[neighbor.id] + heuristic_cost_estimate(neighbor, goals)
        return None

    def find_greedy_tour_of_edges(self, edges: Iterable[GeoEdge]) -> Tour:

        tour = Tour()
        if not edges:
            return tour

        remaining_edges = set(edges)
        reasonably_close_nodes = set()
        cur_node = min((e.start_node for e in edges), key=lambda n: n.longitude)
        cur_node.validate()
        while True:
           # print(datetime.now(),"EDGES LEFT",len(remaining_edges))
            # find the shortest goal edge on the current node and traverse it
            cur_edge = min((e for e in cur_node.edges if e.edge in remaining_edges),
                           key=lambda e: e.length, default=None)

            if cur_edge is not None:
                tour.append_edge(cur_edge, True)
                validate_segments(tour.segments)
                cur_node = cur_edge.end_node
                cur_node.validate()
                remaining_edges.remove(cur_edge.edge)
                if not remaining_edges:
                    return tour

            while True:
                remaining_nodes = set(e.start_node for e in remaining_edges) | set(e.end_node for e in remaining_edges)
                reasonably_close_nodes &= remaining_nodes
                if not reasonably_close_nodes:
                    reasonably_close_nodes = set(n for n in remaining_nodes if cur_node.euclidean_distance(n)<0.1)
                closest_node = min(reasonably_close_nodes if reasonably_close_nodes else remaining_nodes, key=cur_node.euclidean_distance)
                path_to_closest_node = self.find_path(cur_node, closest_node)

                if path_to_closest_node is None:
                    print("HEY HEY HEY UH OH")
                    print("NO WAY TO GET FROM "+str(cur_node.intersection)+" ("+str(cur_node.id)+") TO "+str(closest_node.intersection)+" ("+str(closest_node.id)+")")
                    for edge in closest_node.edges:
                        if edge.edge in remaining_edges:
                            remaining_edges.remove(edge.edge)
                else:
                    break

            for e in path_to_closest_node:
                if e.edge in remaining_edges:
                    break
                tour.append_edge(e, False)
                validate_segments(tour.segments)
                cur_node = e.end_node
                cur_node.validate()



    def shorten_tour_of_edges(self, tour: Tour, end_time: datetime = None) -> Optional[Tour]:

        tour_length = len(tour.segments)
        validate_segments(tour.segments)
        if (tour_length <= 2):
            return None # can't shorten a zero-or-one-length tour

        # find lengths
        lengths = [s.journey_length for s in tour.segments]
        for k in range(tour_length-1):
            lengths[k] += tour.segments[k+1].journey_length

        # find biggest jump
        while True:
            if end_time and datetime.now() > end_time:
                return None

            i = index_max(lengths)
            #print("i",i)
            if (lengths[i]<=0):
                return None

            improvement = lengths[i] # type: float
            lengths[i] = 0

            # so we will pluck goal i out, and join the two next to it

            new_segments = [s for s in tour.segments]
            validate_segments(new_segments)
            new_journey = None
            if (i>0) and (i+1 < tour_length):
                new_journey = self.find_path(new_segments[i-1].goal.end_node, new_segments[i+1].goal.start_node)
                if new_journey is None:
                    #print("WHOOPS")
                    continue # whoops, can't get there from here?!

                new_segments[i+1]=TourSegment(new_journey, new_segments[i+1].goal, new_segments[i+1].goal_residents)
                improvement -= new_segments[i+1].journey_length

            new_segments.pop(i)
            if (i==0):
                new_segments[0]=TourSegment([], new_segments[0].goal, new_segments[0].goal_residents)

            validate_segments(new_segments)

            # find closest other in new_segments
            sn = tour.segments[i].goal.start_node
            en = tour.segments[i].goal.start_node
            distances_to_goal = [
                s.goal.start_node.euclidean_distance(sn) +
                s.goal.end_node.euclidean_distance(sn) +
                s.goal.start_node.euclidean_distance(en) +
                s.goal.end_node.euclidean_distance(en)
                for s in new_segments
            ]

            while True:
                if end_time and datetime.now() > end_time:
                    return None
                j = index_min(distances_to_goal)
                #print("  j", j)
                if (distances_to_goal[j] == math.inf):
                    break
                distances_to_goal[j] = math.inf
                orig_j = j
                for offset in [0, 1, -1, 2]:
                    j = orig_j+offset
                    if j<0 or j>=tour_length:
                        continue
                    orig_edge = tour.segments[i].goal
                    orig_residents = tour.segments[i].goal_residents
                    for flip in [False, True]:
                        edge = orig_edge
                        if flip:
                            edge = DirectedEdge(orig_edge.edge, orig_edge.end_node, orig_edge.start_node)
                        # now we have a new goal edge and a j to insert BEFORE
                        # let's see if it helps

                        payment = 0.

                        new_journey_first = []
                        if j > 0:
                            start_node = new_segments[j - 1].goal.end_node
                            new_journey_first = self.find_path(start_node, edge.start_node)
                            if new_journey_first is None:
                                print("WHOOPS")
                                continue  # whoops, can't get there from here?!
                            new_journey_first_length = sum(e.length for e in new_journey_first)
                            payment += new_journey_first_length

                        if (j + 1 < tour_length):
                            end_node = new_segments[j].goal.start_node
                            new_journey_last = self.find_path(edge.end_node, end_node)
                            if new_journey_last is None:
                                print("WHOOPS")
                                continue # whoops, can't get there from here?!
                            new_journey_last_length = sum(e.length for e in new_journey_last)
                            payment += new_journey_last_length
                            payment -= new_segments[j].journey_length

                        # here's where we see if there's at least a 0.05 mile improvement
                        if (payment + 0.05 >= improvement):
                            continue
                        #okay, we're going to return a new tour here!

                        if (j + 1 < tour_length):
                            new_segments[j].journey = new_journey_last
                            new_segments[j].journey_length = new_journey_last_length

                        new_segments.insert(j, TourSegment(new_journey_first, edge, orig_residents))
                        validate_segments(new_segments)
                        return Tour(new_segments)



    def optimize_tour(self, tour: Tour, max_time_secs: float=15.) -> Tour:
        print(datetime.now(), "ORIGINAL TOUR LENGTH ", tour.get_length())
        end_time = datetime.now() + timedelta(seconds=max_time_secs)
        while (datetime.now() < end_time):
            improved_tour = self.shorten_tour_of_edges(tour, end_time)
            if improved_tour is None:
                return tour
            tour = improved_tour
            print(datetime.now(), "==> IMPROVED TOUR LENGTH ", tour.get_length())
        return tour

    def find_tour_of_edges(self, edges: Iterable[GeoEdge], max_time_secs: float=15.) -> Tour:
        tour = self.find_greedy_tour_of_edges(edges)
        #print(datetime.now(), "GREEDY TOUR LENGTH ", tour.get_length())
        return self.optimize_tour(tour, max_time_secs)

    def add_residents_to_tour(self, residents: Iterable[Resident], tour: Tour) -> Tour:
        resident_map = dict()  # type: Dict[int, Set(Resident)]
        for resident in residents:
            geo_edge_id = resident.household.geo_edge.id
            if geo_edge_id not in resident_map:
                resident_map[geo_edge_id] = set()
            resident_map[geo_edge_id].add(resident)
        for segment in tour.segments:
            residents_for_segment = resident_map[segment.goal.edge.id]
            sx = segment.goal.start_node.x
            sy = segment.goal.start_node.y
            dx = segment.goal.end_node.x - sx
            dy = segment.goal.end_node.y - sy

            segment.goal_residents = sorted(
                residents_for_segment,
                key=lambda r: (
                    (r.household.x-sx)*dx + (r.household.y-sy)*dy,
                    r.household.house_number,
                    r.household.house_number_suffix,
                    r.household.apartment_number,
                    r.last_name,
                    r.first_name,
                    r.date_of_birth
                )
            )
        return tour
       # tour = self.find_tour_of_edges(resident_map.keys(), max_time_secs)

    def find_tour(self, residents: Iterable[Resident], max_time_secs: float=15.) -> Tour:
        edges = set(self.edges_map[r.household.geo_edge.id] for r in residents)
        tour = self.find_tour_of_edges(edges, max_time_secs)
        tour = self.add_residents_to_tour(residents, tour)
        return tour

    def find_turfs(self, residents: Iterable[Resident], max_walk_miles: float=2.0,
                   max_num_households:int=60, max_num_residents:int=200,
                   max_time_secs: float=20.) -> List[Tour]:

        frac_of_time_on_init = 0.2
        long_tour = self.find_tour(residents, max_time_secs*frac_of_time_on_init)
        tours = [] # type: List[Tour]
        cur_tour = None
        cur_walk_miles = 0
        cur_num_households = 0
        cur_num_residents = 0
        for segment in long_tour.segments:
            seg_walk_miles = segment.journey_length + segment.goal.length
            # if (seg_walk_miles>0.7):
            #     print("LONG SEGMENT:")
            #     for e in segment.journey + [segment.goal]:
            #         print("   ",e.edge.street, "FROM ", e.start_node.intersection, "TO", e.end_node.intersection)
            seg_num_residents = len(segment.goal_residents)
            seg_num_households = len(set(r.household.id for r in segment.goal_residents))
            # print(len(tours),"CUR_WALK_MILES",cur_walk_miles,"; SEG_WALK_MILES",seg_walk_miles,"; SUM",cur_walk_miles+seg_walk_miles)
            if (cur_tour is None
                or seg_walk_miles + cur_walk_miles > max_walk_miles
                or seg_num_residents + cur_num_residents > max_num_residents
                or seg_num_households + cur_num_households > max_num_households):
                cur_tour = Tour()
                tours.append(cur_tour)
                cur_walk_miles = 0
                cur_num_households = 0
                cur_num_residents = 0
                segment.journey = []
                segment.journey_length = 0
                seg_walk_miles = segment.goal.length
            cur_tour.segments.append(segment)
            cur_walk_miles += seg_walk_miles
            cur_num_residents += seg_num_residents
            cur_num_households += seg_num_households

        each_time = (max_time_secs*(1.0-frac_of_time_on_init))/sum(t.length for t in tours)
        optimized_tours = [self.optimize_tour(t, t.length * each_time) for t in tours]
        return optimized_tours

# TODO TODO TODO
# TODO get foot paths also, that's what we're doing
