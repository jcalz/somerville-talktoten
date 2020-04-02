import itertools
from datetime import date

from dateutil.relativedelta import relativedelta
from django import forms
from django.db import OperationalError
from django.db.models import Case
from django.db.models import ExpressionWrapper
from django.db.models import Q
from django.db.models import Value, PositiveSmallIntegerField, BooleanField
from django.db.models import When
from django.forms.models import ModelForm

from TalkToTen.models import Resident, ContactRecord, SupportLevels, ContactRecordActionChoices, ContactTypeChoices


def strings_to_choices(strs):
    try:
        return tuple((str, str) for str in strs)
    except OperationalError:
        print("THERE'S A PROBLEM")
        return (('oops','oops'))


class MatchForm(forms.Form):
    preferred_name = forms.CharField(required=False)

    preferred_minimum_age = forms.IntegerField(required=False, min_value=0, max_value=120)
    preferred_maximum_age = forms.IntegerField(required=False, min_value=0, max_value=120)

    GENDER_PREFERENCE = (
        ('', 'Any'),
        (Resident.FEMALE, 'Female'),
        (Resident.MALE, 'Male')
    )

    preferred_gender = forms.ChoiceField(required=False, choices=GENDER_PREFERENCE)

    NEIGHBORHOODS = (
        (11, 'East Somerville (Pearl to Mt Vernon)'),
        (12, 'East Somerville (Broadway, Rush, Cross, Wisconsin, plus Assembly Sq.)'),
        (13, 'East Somerville (Otis, Gilman, Flint)'),
        (21, 'Union Square (East of Union Square, Target Area)'),
        (22, 'Union Square (Lincoln Park, Inman)'),
        (23, 'Beacon & Park'),
        (31, 'Prospect Hill'),
        (32, 'Central Hill (Avon, Oxford)'),
        (33, 'Central Hill (Belmont, Porter)'),
        (41, 'Ten Hills, Mystic'),
        (42, 'Broadway West of McGrath (Marshall, Sargent, Jacques)'),
        (43, 'Healey Area'),
        (51, 'Winter Hill/Magoun'),
        (52, 'Bike Path Area (Josephine, Maxwell Green, Cedar)'),
        (53, 'Davis/Porter Square (Cherry, Lexington, Highland)'),
        (61, 'Davis Square (Elm, Orchard, Willow)'),
        (62, 'Brown School Area (Foskett, Hall, Morrison)'),
        (63, 'West Somerville (College Ave, Powderhouse, Tufts)'),
        (71, 'West Somerville (Electric, Ossipee, Packard)'),
        (72, 'West Somerville (Alewife Brook, North Street)'),
        (73, 'West Somerville (Alewife Brook, Hillside, Upland)')
    )

    preferred_neighborhoods = forms.MultipleChoiceField(required=False, choices=NEIGHBORHOODS)

    streets = Resident.objects.values_list('household__street', flat=True).distinct().order_by(
        'household__street')
    preferred_streets = forms.MultipleChoiceField(required=False, choices=strings_to_choices(streets))

    occupations = Resident.objects.exclude(occupation='').values_list('occupation', flat=True).distinct().order_by(
        'occupation')
    preferred_occupations = forms.MultipleChoiceField(required=False, choices=strings_to_choices(occupations))

    nationalities = Resident.objects.exclude(nationality='').values_list('nationality', flat=True).distinct().order_by(
        'nationality')
    preferred_nationalities = forms.MultipleChoiceField(required=False, choices=strings_to_choices(nationalities))

    lengths_of_time_in_home = Resident.objects.exclude(length_of_time_in_home='').values_list('length_of_time_in_home',
                                                                                              flat=True).distinct().order_by(
        'length_of_time_in_home')
    # put 'less than*' in front
    front, back = [], []
    for l in lengths_of_time_in_home:
        (front if l.lower().startswith('less') else back).append(l)
    lengths_of_time_in_home = front + back

    preferred_lengths_of_time_in_home = forms.MultipleChoiceField(required=False,
                                                                  choices=strings_to_choices(lengths_of_time_in_home))

    university_affiliations = sorted(
        (set(Resident.objects.values_list('university_affiliation_1', flat=True).distinct())
         | set(Resident.objects.values_list('university_affiliation_2', flat=True).distinct())
         | set(Resident.objects.values_list('university_affiliation_3', flat=True).distinct())
         ) - {''})
    preferred_university_affiliations = forms.MultipleChoiceField(required=False,
                                                                  choices=strings_to_choices(university_affiliations))

    SCHOOL_AGE = 's'
    YOUNG_AGE = 'y'
    CHILDREN_AGE_CHOICES = (
        (YOUNG_AGE, 'Young children'),
        (SCHOOL_AGE, 'School-aged children')
    )

    preferred_child_ages = forms.MultipleChoiceField(required=False, choices=CHILDREN_AGE_CHOICES)

    HAS_DOG = 'dog'
    DOG_OWNERSHIP_PREFERENCE = (
        ('', 'Any'),
        (HAS_DOG, 'Has dog(s)'),
    )

    preferred_dog_ownership_status = forms.ChoiceField(required=False, choices=DOG_OWNERSHIP_PREFERENCE)

    def find_potential_matches(self, user, as_resident):

        if not self.is_valid():
            return None

        if (as_resident):
            resident = Resident.objects.get(user=user)
            preferred_name = resident.last_name
            preferred_minimum_age = None
            preferred_maximum_age = None
            if (resident.age):
                preferred_minimum_age = resident.age - 5
                preferred_maximum_age = resident.age + 5
            preferred_gender = None
            preferred_neighborhoods = []
            if (resident.household.ward_number and resident.household.precinct_number):
                preferred_neighborhoods.append(resident.household.ward_number * 10 + resident.household.precinct_number)
            preferred_streets = []
            if resident.household.street:
                preferred_streets.append(resident.household.street)
            preferred_occupations = []
            if resident.occupation:
                preferred_occupations.append(resident.occupation)
            preferred_nationalities = []
            if resident.nationality:
                preferred_nationalities.append(resident.nationality)
            preferred_lengths_of_time_in_home = []
            if resident.length_of_time_in_home:
                preferred_lengths_of_time_in_home.append(resident.length_of_time_in_home)
            preferred_university_affiliations = [x for x in
                                                 [resident.university_affiliation_1,
                                                  resident.university_affiliation_2,
                                                  resident.university_affiliation_3]
                                                 if x]
            preferred_child_ages = []
            resident_child_ages = [resident.child_age_1, resident.child_age_2, resident.child_age_3]
            if any(a and a <= 5 for a in resident_child_ages):
                preferred_child_ages.append(MatchForm.YOUNG_AGE)
            if any(a and a > 5 for a in resident_child_ages):
                preferred_child_ages.append(MatchForm.SCHOOL_AGE)
            preferred_dog_ownership_status = MatchForm.HAS_DOG if resident.known_to_have_dog else None
        else:
            cd = self.cleaned_data
            preferred_name = cd.get('preferred_name', None)
            preferred_minimum_age = cd.get('preferred_minimum_age', None)
            preferred_maximum_age = cd.get('preferred_maximum_age', None)
            preferred_gender = cd.get('preferred_gender', None)
            preferred_neighborhoods = cd.get('preferred_neighborhoods', None)
            preferred_streets = cd.get('preferred_streets', None)
            preferred_occupations = cd.get('preferred_occupations', None)
            preferred_nationalities = cd.get('preferred_nationalities', None)
            preferred_lengths_of_time_in_home = cd.get('preferred_lengths_of_time_in_home', None)
            preferred_university_affiliations = cd.get('preferred_university_affiliations', None)
            preferred_child_ages = cd.get('preferred_child_ages', None)
            preferred_dog_ownership_status = cd.get('preferred_dog_ownership_status', None)

        potential_matches = Resident.objects

        # apparently we only want to consider people who voted in the presidential election
        potential_matches = potential_matches.filter(voted_2016_11_08=True)
        # and people who are not opponents
        potential_matches = potential_matches.exclude(
            level_of_support__in=[SupportLevels.POSSIBLE_OPPONENT, SupportLevels.DEFINITE_OPPONENT])


        criteria = []

        # name criterion
        if (preferred_name):
            criterion = None
            import re
            for name in filter(bool, re.split('[^-a-zA-Z\']', preferred_name)):
                crit_piece = Q(last_name__icontains=name) | Q(first_name__icontains=name)
                if (criterion):
                    criterion &= crit_piece
                else:
                    criterion = crit_piece
            criteria.append(criterion)

        # age criterion
        if (preferred_minimum_age or preferred_maximum_age):
            today = date.today()
            age_criterion = None
            if (preferred_minimum_age):
                age_criterion = Q(date_of_birth__lte=today - relativedelta(years=preferred_minimum_age))
            if (preferred_maximum_age):
                max_age_criterion = Q(date_of_birth__gt=today - relativedelta(years=preferred_maximum_age + 1))
                if (age_criterion):
                    age_criterion = age_criterion & max_age_criterion
                else:
                    age_criterion = max_age_criterion
            criteria.append(age_criterion)

        # gender criterion
        if (preferred_gender):
            criteria.append(Q(gender=preferred_gender))

        # neighboorhoods
        if (preferred_neighborhoods):
            for i, neighborhood in enumerate(preferred_neighborhoods):
                q = Q(household__ward_number=(int(neighborhood) // 10), household__precinct_number=(int(neighborhood) % 10))
                if (i == 0):
                    criterion = q
                else:
                    criterion = criterion | q
            criteria.append(criterion)

        # streets
        if (preferred_streets):
            criteria.append(Q(household__street__in=preferred_streets))

        # occupations
        if (preferred_occupations):
            criteria.append(Q(occupation__in=preferred_occupations))

        # nationalities
        if (preferred_nationalities):
            criteria.append(Q(nationality__in=preferred_nationalities))

        # university affiliations
        if (preferred_university_affiliations):
            criteria.append(
                Q(university_affiliation_1__in=preferred_university_affiliations)
                | Q(university_affiliation_2__in=preferred_university_affiliations)
                | Q(university_affiliation_3__in=preferred_university_affiliations))

        # lengths of time in home
        if (preferred_lengths_of_time_in_home):
            criteria.append(Q(length_of_time_in_home__in=preferred_lengths_of_time_in_home))

        # child ages
        if (preferred_child_ages):
            criterion = None
            if (MatchForm.YOUNG_AGE in preferred_child_ages):
                criterion = Q(child_age_1__lte=5) | Q(child_age_2__lte=5) | Q(child_age_3__lte=5)
            if (MatchForm.SCHOOL_AGE in preferred_child_ages):
                criterion_school = Q(child_age_1__gt=5) | Q(child_age_2__gt=5) | Q(child_age_3__gt=5)
                if (criterion):
                    criterion |= criterion_school
                else:
                    criterion = criterion_school
            if (criterion):
                criteria.append(criterion)

        # dog ownership
        if (preferred_dog_ownership_status == MatchForm.HAS_DOG):
            criteria.append(Q(known_to_have_dog=True))

        # do the thing
        zero = Value(0, output_field=PositiveSmallIntegerField())
        one = Value(1, output_field=PositiveSmallIntegerField())

        num_matches = zero

        for criterion in criteria:
            num_matches = num_matches + Case(When(criterion, then=one), default=zero)

        # donor special sauce
        big_donor = Q(
            donor_local_amount__gte=200, donor_local_progressive_percent__gte=50
        ) | Q(
            donor_federal_amount__gte=200, donor_federal_progressive_percent__gte=50
        )

        num_matches += 0.5 * max(1, len(criteria) - 1) * Case(When(big_donor, then=one), default=zero)

        taken_contacts = ContactRecord.objects.exclude(status=ContactRecord.COMPLETE_BUT_UNRESERVED).values('resident')

        unavailable = ExpressionWrapper(Q(user=user) |
                                        Q(id__in=taken_contacts) |
                                        Q(level_of_support=SupportLevels.DEFINITE_SUPPORTER),
                                        output_field=BooleanField()
                                        )

        potential_matches = potential_matches.annotate(unavailable=unavailable, num_matches=num_matches)

        potential_matches = potential_matches.order_by('-num_matches', '-count_elections')

        def potential_match_generator():
            chunk_size = 100
            number_available = 0
            for chunk in itertools.count():
                for potential_match in potential_matches[chunk_size * chunk:chunk_size * (chunk + 1)]:
                    if number_available >= 40:
                        return
                    if not potential_match.unavailable:
                        number_available += 1
                    yield potential_match

        return potential_match_generator()


class ContactRecordForm(ModelForm):
    interest_areas = forms.MultipleChoiceField(required=False, label='(Optional) interests',
                                               choices=((f.name, f.verbose_name) for f in
                                                        ContactRecord._meta.get_fields() if
                                                        f.name.startswith('interest_area')))
    ACTION_CHOICES = (
        ('', "-- Choose a contact method --"),
        (ContactRecordActionChoices.SEND_MAIL, "Send an email"),
        (ContactRecordActionChoices.FOLLOW_UP, "Have Stephanie follow up"),
        (ContactRecordActionChoices.NO_FOLLOW_UP, "Send a postcard yourself"),
        (ContactRecordActionChoices.RELINQUISH, "Remove from contacts"),
    )

    action = forms.ChoiceField(required=False, choices=ACTION_CHOICES)

    class Meta:
        model = ContactRecord
        fields = ['email', 'phone', 'notes', 'action', 'interest_areas', 'level_of_support']
        widgets = {
            'notes': forms.TextInput,
        }
        labels = {
            'level_of_support': '(Optional) level of support'
        }

    def __init__(self, *args, **kwargs):
        if ('instance' in kwargs):
            initial = kwargs.get('initial', {})
            initial['interest_areas'] = kwargs['instance'].interest_areas
            kwargs['initial'] = initial
        super(ContactRecordForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(ContactRecordForm, self).clean()
        action = cleaned_data.get('action')
        if action == ContactRecordActionChoices.SEND_MAIL:
            email = cleaned_data.get('email')
            if not email:
                raise forms.ValidationError('Please enter an email address if you want to send an email')

    def save(self, commit=True):
        contact_record = super(ContactRecordForm, self).save(commit=False)
        contact_record.follow_up_date = None
        contact_record.contact_type = ContactTypeChoices.TALK_TO_TEN
        contact_record.interest_areas = self.cleaned_data['interest_areas']
        if (commit):
            contact_record.save()
        return contact_record
