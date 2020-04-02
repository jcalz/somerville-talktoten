import re

from datetime import datetime, timedelta, date
from decimal import Decimal, InvalidOperation
from itertools import groupby
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode

from dateutil.relativedelta import relativedelta
from django.conf.urls import url
from django.contrib import admin
from django.contrib import messages
from django.contrib.admin import ListFilter, FieldListFilter
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.views.main import ChangeList
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.core import mail
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Case, IntegerField, Min, Max, Count, FloatField
from django.db.models import F, Sum
from django.db.models import Q
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import Cast, Coalesce
from django.db.models.functions import Lower
from django.forms import RadioSelect
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render, render_to_response
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import curry
from django_extensions.admin import ForeignKeyAutocompleteAdmin
from import_export import resources
from import_export.admin import ExportActionModelAdmin
from django import forms
from Campaign import utils
from TalkToTen.models import Resident, ContactRecord, Event, StreetSegment, SupportLevels, Household, Volunteer, \
    ResidentTag, add_tag_to_resident_id_set, remove_tag_from_resident_id_set, GeoGraph, FacebookStatus
import xml.etree.cElementTree as ET

ORDER_VAR = admin.views.main.ORDER_VAR;


class MultiFieldSortableChangeList(ChangeList):
    """
    This class overrides the behavior of column sorting in django admin tables in order
    to allow multi field sorting


    Usage:

    class MyCustomAdmin(admin.ModelAdmin):

        ...

        def get_changelist(self, request, **kwargs):
            return MultiFieldSortableChangeList

        ...

    """

    def get_ordering(self, request, queryset):
        """
        Returns the list of ordering fields for the change list.
        First we check the get_ordering() method in model admin, then we check
        the object's default ordering. Then, any manually-specified ordering
        from the query string overrides anything. Finally, a deterministic
        order is guaranteed by ensuring the primary key is used as the last
        ordering field.
        """
        params = self.params
        ordering = list(self.model_admin.get_ordering(request)
                        or self._get_default_ordering())
        if ORDER_VAR in params:
            # Clear ordering and used params
            ordering = []
            order_params = params[ORDER_VAR].split('.')
            for p in order_params:
                try:
                    none, pfx, idx = p.rpartition('-')
                    field_name = self.list_display[int(idx)]

                    # the following 8 lines are the only ones modified by me------------------------
                    order_fields = self.get_ordering_field(field_name)
                    # I ask for __iter__ because hasattr(x, '__iter__') is true for list and tuples
                    # but false for strings
                    # http://stackoverflow.com/questions/1952464/in-python-how-do-i-determine-if-an-object-is-iterable
                    if not hasattr(order_fields, '__iter__') or isinstance(order_fields, str):
                        order_fields = [order_fields]
                    for order_field in order_fields:
                        if order_field:
                            ordering.append(pfx + order_field)
                except (IndexError, ValueError):
                    continue  # Invalid ordering specified, skip it.

        # Add the given query's ordering fields, if any.
        ordering.extend(queryset.query.order_by)

        # Ensure that the primary key is systematically present in the list of
        # ordering fields so we can guarantee a deterministic order across all
        # database backends.
        pk_name = self.lookup_opts.pk.name
        if not (set(ordering) & set(['pk', '-pk', pk_name, '-' + pk_name])):
            # The two sets do not intersect, meaning the pk isn't present. So
            # we add it.
            ordering.append('-pk')

        return ordering


class MultiFieldSortableModelAdmin(admin.ModelAdmin):
    """
    By inherit from this class, now is possible to define admin_order_field like this:

    def user_full_name(self, obj):
        return obj.get_full_name()
    user_full_name.admin_order_field = ['first_name', 'last_name']

    """

    def get_changelist(self, request, **kwargs):
        return MultiFieldSortableChangeList

ListFilter.template = 'admin/dropdown_filter.html'



def PresentFilter(field_name, empty_value=None, title=None, present_text=None, absent_text=None):

    absent = Q(**{field_name+'__isnull': True})
    if empty_value is not None:
        absent = absent | Q(**{field_name : empty_value})
    filter_title = title
    present_text = present_text or 'Has a value'
    absent_text = absent_text or 'Is empty'

    class _PresentFilter(SimpleListFilter):
        title = filter_title if filter_title else 'presence of '+field_name.replace('_',' ')
        parameter_name = field_name
        def lookups(self, request, model_admin):
            return (
                ('1', present_text),
                ('0', absent_text),
            )
        def queryset(self, request, queryset):
            if self.value() == '1':
                return queryset.exclude(absent)
            if self.value() == '0':
                return queryset.filter(absent)
    return _PresentFilter


class DistanceFilter(ListFilter):

    title='Distance'
    parameter_name = 'distance'
    template = "admin/distance_filter.html"

    def __init__(self, request, params, model, model_admin):
        super(DistanceFilter, self).__init__(request, params, model, model_admin)
        val = params.pop('distance',None);
        if (val is not None):
            val = val.strip()
        if ((val=='!') or (val=='')):
            val = None
        self.used_parameters['distance'] = val

    def has_output(self):
        return True

    def expected_parameters(self):
        """
        Returns the list of parameter names that are expected from the
        request's query string and that will be used by this filter.
        """
        return [self.parameter_name]


    def choices(self, cl):
        addr = None
        dist = None
        val = self.used_parameters['distance']
        if (val is not None):
            [addr, dist]=val.split('!',1)
        return ({
            'addr': addr,
            'dist': dist
        },)

    def queryset(self, request, queryset):
        val = self.used_parameters['distance']
        if (val is None):
            return queryset
        [addr, dist]=val.split('!', 1)
        try:
            dist = Decimal(dist)
        except InvalidOperation:
            return queryset
        import urllib.parse
        import json
        import time
        url = "https://geocoding.geo.census.gov/geocoder/locations/address?street=" + urllib.parse.quote(
            addr)+ "&city=Somerville&state=MA&benchmark=Public_AR_Current&format=json"

        delay = 0.001
        str_response = ""
        while True:
            code = 200
            try:
                response = urllib.request.urlopen(url)
                str_response = response.read().decode('utf-8')
            except HTTPError as e:
                code = e.code
            except URLError as e:
                code = 0
            if (code!=500 or delay > 5):
                break
            print("delay",delay)
            time.sleep(delay)
            delay *= 2

        try:
            addressMatch = json.loads(str_response)['result']['addressMatches'][0]
        except:
            addressMatch = None

        try:
            isSomerville = addressMatch['addressComponents']['city'].lower() == 'somerville'
        except:
            isSomerville = False

        if not isSomerville:
            return queryset
        latitude = addressMatch['coordinates']['y']
        longitude = addressMatch['coordinates']['x']

        return queryset.filter(one__gte=
                ((4775*(F('household__latitude')-latitude)*(F('household__latitude')-latitude))+(2601*(F('household__longitude')-longitude)*(F('household__longitude')-longitude)))/(dist*dist)
        )

class AgeFilter(ListFilter):

    title='Age'
    parameter_name = 'age'
    template = "admin/age_filter.html"

    def __init__(self, request, params, model, model_admin):
        super(AgeFilter, self).__init__(request, params, model, model_admin)
        val = params.pop('age',None);
        if (val is not None):
            val = val.strip()
        if ((val=='!') or (val=='')):
            val = None
        self.used_parameters['age'] = val

    def has_output(self):
        return True

    def expected_parameters(self):
        """
        Returns the list of parameter names that are expected from the
        request's query string and that will be used by this filter.
        """
        return [self.parameter_name]


    def choices(self, cl):
        fromAge = None
        toAge = None
        val = self.used_parameters['age']
        if (val is not None):
            [fromAge, toAge]=val.split('!',1)
        return ({
            'fromAge': fromAge,
            'toAge': toAge
        },)

    def queryset(self, request, queryset):
        val = self.used_parameters['age']
        if (val is None):
            return queryset
        [fromAge, toAge]=val.split('!', 1)
        try:
            fromAge = int(fromAge)
        except ValueError:
            fromAge = None
        try:
            toAge = int(toAge)
        except ValueError:
            toAge = None

        q = queryset

        if (fromAge is not None):
            born_on_or_before = date.today() - relativedelta(years=fromAge)
            q = q.filter(date_of_birth__lte=born_on_or_before)

        if (toAge is not None):
            born_after = date.today() - relativedelta(years=toAge+1)
            q = q.filter(date_of_birth__gt=born_after)

        return q


class ResidentTagFilter(ListFilter):

    title='Tags'
    parameter_name = 'tags'
    template = "admin/tag_filter.html"

    tags = sorted(list(ResidentTag.objects.values_list('tag', flat=True).distinct()), key=lambda s: s.lower())

    def __init__(self, request, params, model, model_admin):
        super(ResidentTagFilter, self).__init__(request, params, model, model_admin)
        val = params.pop('tags',None);
        if (val is not None):
            val = val.strip()
        if (val==''):
            val = None
        self.used_parameters['tags'] = val

    def has_output(self):
        return True

    def expected_parameters(self):
        """
        Returns the list of parameter names that are expected from the
        request's query string and that will be used by this filter.
        """
        return [self.parameter_name]


    def choices(self, cl):
        tags = None
        sense = 'U'
        case_sensitive = 'N'
        parts = 'Y'
        val = self.used_parameters['tags']
        if (val is not None):
            try:
                [tags, sense, case_sensitive, parts] = val.split('::', 3)
            except ValueError:
                pass

        return ({
                    'tags': tags,
                    'sense': sense,
                    'case_sensitive': case_sensitive,
                    'parts': parts
                },)


    def queryset(self, request, queryset):
        val = self.used_parameters['tags']
        if (val is None):
            return queryset
        try:
            [tag_string, sense, case_sensitive, parts] = val.split('::', 3)
        except ValueError:
            return queryset
        tags = [s for s in [t.strip() for t in tag_string.split(',')] if s]
        if not tags:
            return queryset

        intersection = sense.upper().strip() != 'U'
        case_sensitive = case_sensitive.upper().strip() == 'Y'
        parts = parts.upper().strip() == 'Y'

        ids = None
        for tag in tags:
            if (case_sensitive):
                if (parts):
                    query = Q(tag__contains=tag)
                else:
                    query = Q(tag=tag)
            else:
                if (parts):
                    query = Q(tag__icontains=tag)
                else:
                    query = Q(tag__iexact=tag)

            tag_ids = set(ResidentTag.objects.filter(query).values_list('resident_id', flat=True).distinct())

            if ids is None:
                ids = tag_ids
            elif intersection:
                ids &= tag_ids
            else:
                ids |= tag_ids
        return queryset.filter(id__in=ids)


class ResidentResource(resources.ModelResource):
    from import_export import fields
    contacter = fields.Field()
    street_segment_name = fields.Field()
    street_segment_ordering = fields.Field()
    class Meta:
        model = Resident

        fields = [utils.transform(f.name, {'user':'user__username'})
                  for f in Resident._meta.fields]
        fields.append('street_segment_name')
        fields.append('street_segment_ordering')
        fields.append('contacter')
        fields.append('household__ward_number')
        fields.append('household__precinct_number')
        export_order = fields

    def dehydrate_contacter(self, resident):
        return ', '.join([c.contacter.get_full_name() or c.contacter.get_username()
                          for c in resident.contactrecord_set.select_related('contacter')])

    def dehydrate_street_segment_name(self, resident):
        return str(resident.household.street_segment)

    def dehydrate_street_segment_ordering(self, resident):
        return str(resident.household.street_segment.ordering)

    def dehydrate_household(self, resident):
        return str(resident.household)

def dollars(fieldname, short_description=None):
    if not short_description:
        short_description = fieldname.replace('_', ' ').title()
    def disp(self, object):
        return '${:,}'.format(getattr(object,fieldname) or 0)
    disp.admin_order_field = fieldname
    disp.short_description = short_description
    return disp

def percent(fieldname, short_description=None):
    if not short_description:
        short_description = fieldname.replace('_', ' ').title()
    def disp(self, object):
        return '{:,}%'.format(getattr(object,fieldname) or 0)
    disp.admin_order_field = fieldname
    disp.short_description = short_description
    return disp


def rename_field(fieldname, short_description=None, boolean=False, choices=None):
    if not short_description:
        short_description = fieldname.replace('_',' ').title()
    if not choices:
        def disp(self, object):
            return getattr(object,fieldname)
    else:
        def disp(self, object):
            return ','.join([desc for (c, desc) in choices if c == getattr(object, fieldname)])
    disp.admin_order_field = fieldname
    disp.short_description = short_description
    if (boolean):
        disp.boolean = True
    return disp

def PresentFilter(field_name, empty_value=None, title=None, present_text=None, absent_text=None):

    absent = Q(**{field_name+'__isnull': True})
    if empty_value is not None:
        absent = absent | Q(**{field_name : empty_value})
    filter_title = title
    present_text = present_text or 'Has a value'
    absent_text = absent_text or 'Is empty'

    class _PresentFilter(SimpleListFilter):
        title = filter_title if filter_title else 'presence of '+field_name.replace('_',' ')
        parameter_name = field_name
        def lookups(self, request, model_admin):
            return (
                ('1', present_text),
                ('0', absent_text),
            )
        def queryset(self, request, queryset):
            if self.value() == '1':
                return queryset.exclude(absent)
            if self.value() == '0':
                return queryset.filter(absent)
    return _PresentFilter

class FacebookStatusFilter(SimpleListFilter):
    title = "Facebook Status"
    parameter_name = "facebook_status"

    the_choices = [
        dict(key=str(val), title=title, filter=Q(facebook_status=val)) for (val, title) in FacebookStatus.CHOICES
    ]
    # add choices?
    lookup_choices = [(c['key'], c['title']) for c in the_choices]
    vals = {c['key']: c['filter'] for c in the_choices}

    def lookups(self, request, model_admin):
        return self.lookup_choices

    def queryset(self, request, queryset):
        val = self.value()
        if (val is None):
            return
        ret = queryset.filter(self.vals[val])
        return ret

def LevelOfSupportFilter(field_name, title=None):
    filter_title = title
    class _LevelOfSupportFilter(SimpleListFilter):
        title = filter_title if filter_title else field_name.replace('_',' ').title()
        parameter_name = field_name

        the_choices = [
            dict(key=str(val), title=title, filter=Q(**{field_name : val})) for (val, title) in SupportLevels.CHOICES
        ] + [
            dict(key='z12', title='Possible/Definite Supporter', filter=Q(**{field_name+"__in":[1,2]})),
            dict(key='z03', title='Undecideds', filter=Q(**{field_name:3})|Q(**{field_name+"__isnull": True})),
            dict(key='z023', title='Undecideds or Possible Supporter', filter=Q(**{field_name+"__in":[2,3]})|Q(**{field_name+"__isnull":True})),
            dict(key='z0123', title='Undecideds or Possible/Definite Supporter',filter=Q(**{field_name+"__in":[1,2,3]})|Q(**{field_name+"__isnull":True}))
        ]
        lookup_choices = [(c['key'], c['title']) for c in the_choices]
        vals = {c['key']: c['filter'] for c in the_choices}

        def lookups(self, request, model_admin):
            return self.lookup_choices

        def queryset(self, request, queryset):
            val = self.value()
            if (val is None):
                return
            ret = queryset.filter(self.vals[val])
            return ret
    return _LevelOfSupportFilter


class CountElectionsFilter(SimpleListFilter):
    title = '#Elections'
    parameter_name = 'count_elections'

    def lookups(self, request, model_admin):
        vals = list(Resident.objects.order_by('count_elections').values_list('count_elections',flat=True).distinct())
        return [( 'L'+str(v), 'at least '+str(v)) for v in vals[1:]] + [( 'M'+str(v), 'at most '+str(v)) for v in vals[:-1]]

    def queryset(self, request, queryset):
        val = self.value()
        if not val:
            return
        sense = str(val[0]).upper()
        endpoint = int(val[1:])
        if sense == 'L':
            return queryset.filter(count_elections__gte=endpoint)
        elif sense == 'M':
            return queryset.filter(count_elections__lte=endpoint)


class UniversityFilter(SimpleListFilter):
    title = 'University Affiliation'
    parameter_name = 'university'

    def lookups(self, request, model_admin):
        vals = list(Resident.objects.order_by('university_affiliation_1').values_list('university_affiliation_1',flat=True).distinct())
        return [(v,v) for v in vals]

    def queryset(self, request, queryset):
        val = self.value()
        if not val:
            return
        return queryset.filter(Q(university_affiliation_1=val)|Q(university_affiliation_2=val)|Q(university_affiliation_3=val))



class BirthdayFilter(SimpleListFilter):
    title = 'Birthday'
    parameter_name = 'birthday'
    def lookups(self, request, model_admin):
        return [('7','in the next week'),('4','in the next four days'),('1','today')]

    def queryset(self, request, queryset):
        try:
            val = int(self.value() or 0)
        except ValueError:
            return
        if val<=0:
            return
        today = datetime.now()
        months_days = [(date.month, date.day) for date in ( today+timedelta(d) for d in range(int(val)))]
        # leap years!
        if (2,28) in months_days or (3,1) in months_days:
            months_days.append((2,29))
        query = None
        for (month,day) in months_days:
            q = Q(date_of_birth__month=month, date_of_birth__day=day)
            if not query:
                query = q
            else:
                query = query | q
        return queryset.filter(query)

class ContactRecordInline(admin.StackedInline):
    model = ContactRecord
    extra = 0
    can_delete = False
    exclude = list(field.name for field in ContactRecord._meta.get_fields() if field.name.startswith('interest_area_')) + [
        'level_of_support','phone','email'
    ]


class ResidentTagInline(admin.TabularInline):
    model = ResidentTag
    class Media:
        css = {
            'all': ('/static/tabular_inline.css',)
        }

volunteer_household_fields = ['address', 'ward_and_precinct', 'street_segment', 'residents']

volunteer_support_fields = ['level_of_support', 'campaign_donation_amount', 'yard_sign', 'num_contacts']
volunteer_option_fields = [
                    'volunteer_option_canvass', 'volunteer_option_gotv', 'volunteer_option_election_day',
                    'volunteer_option_dear_friend', 'volunteer_option_needs_followup']
category_fields = [ 'category_it', 'category_fams', 'category_dems', 'donor_federal_amount', 'donor_local_amount', 'count_elections' ]


class ResidentAdmin(MultiFieldSortableModelAdmin, ExportActionModelAdmin, ForeignKeyAutocompleteAdmin):
    resource_class = ResidentResource

    ordering = ['last_name','first_name']
    list_display = ['full_name', 'household_link', 'ordered_street_segment', 'occupation', 'ward_and_precinct',
                    'voted_2016', 'voted_municipal', 'num_elections',
                    'donor_local_amount_dollars', 'donor_local_prog',
                    'donor_federal_amount_dollars', 'donor_federal_prog',
                    'followup', 'campaign_donation_amount_dollars',
                    'level_of_support', 'yard_sign',
                    'contact_records', 'level_of_support_ilana']
    list_filter = (ResidentTagFilter,'household__is_a_building','voted_2018_09_04','voted_2017_11_07','canvass_complete',
                   'canvass_complete_2017','canvass_complete_ilana',
                   'household__ward_number', 'household__precinct_number', 'voted_2016_11_08',
                   CountElectionsFilter, 'voted_recent_municipal', PresentFilter('email',empty_value=""),
                   'needs_followup', FacebookStatusFilter,
                   LevelOfSupportFilter('level_of_support'),LevelOfSupportFilter('level_of_support_ilana'),
                   PresentFilter('campaign_donation_amount',empty_value=0),'yard_sign',
                   PresentFilter('numcontactrecords',title='has contact records',present_text='Yes',absent_text='No',empty_value=0),
                   UniversityFilter, BirthdayFilter, DistanceFilter, AgeFilter
                   )
    search_fields = ['last_name', 'first_name', 'household__street', 'email', 'notes']
    readonly_fields = ['household_link', 'volunteer_link', 'zip_code','others']
    exclude = ['other_residents_at_address'] + volunteer_option_fields + ['category_gotv', 'election_day_gotv']

    related_search_fields = {
        'household': ('street', 'house_number'),
    }

    def zip_code(self, obj):
        return obj.household.zip_code

    def household_link(self, obj):
        link = reverse("admin:TalkToTen_household_change", args=[obj.household.id])
        return '<a href="%s">%s</a>' % (link, obj.household)
    household_link.allow_tags = True
    household_link.short_description = 'Household'
    household_link.admin_order_field = ['household__street',
                                 'household__house_number',
                                 'household__house_number_suffix',
                                 'household__apartment_number']

    def others(self, obj):
        arr = []
        for res in Resident.objects.filter(household=obj.household).exclude(pk=obj.pk).order_by('last_name','first_name'):
            link = reverse("admin:TalkToTen_resident_change", args=[res.id])
            arr.append('<a href="%s">%s</a>' % (link, res.full_display_name))
        return ', '.join(arr)
    others.allow_tags = True

    def volunteer_link(self, obj):
        link = reverse("admin:TalkToTen_volunteer_change", args=[obj.household.id])
        return '<a href="%s">%s</a>' % (link, obj.household)
    volunteer_link.allow_tags = True
    volunteer_link.short_description = 'Volunteer'


    address=household_link

    def get_search_results(self, request, queryset, search_term):

        reg_terms = []
        ssid = None
        for s in search_term.split():
            seg_match = re.search(r"^SEG(\d+)$", s, flags=re.IGNORECASE)
            if seg_match:
                ssid = int(seg_match.group(1))
            else:
                reg_terms.append(s)

        q, d = super(ResidentAdmin, self).get_search_results(request, queryset, ' '.join(reg_terms))
        if ssid is not None:
            q &= queryset.filter(household__street_segment__id=ssid)
        return q, d

    inlines = [ ContactRecordInline, ResidentTagInline]
    actions = ['test_canvass', 'add_or_remove_tag', 'mark_voted_2017', 'canvassing_doc', 'mark_canvass_complete',
               'mark_canvass_complete_ilana', 'mark_gotv_canvass_complete', 'voting_rolls_doc',
               'mark_no_facebook_acct', 'mark_friend_request', 'mark_friend']

    voted_2016 = rename_field('voted_2016_11_08', short_description='Voted 2016', boolean=True)
    voted_municipal = rename_field('voted_recent_municipal',short_description='Voted Muni', boolean=True)
    num_elections = rename_field('count_elections', short_description='#Elections')
    donor_local_amount_dollars = dollars('donor_local_amount',short_description='Donor Loc')

    donor_local_prog = percent('donor_local_progressive_percent', short_description='Loc Prog%')
    donor_federal_amount_dollars = dollars('donor_federal_amount',short_description='Donor Fed')
    donor_federal_prog = percent('donor_federal_progressive_percent', short_description='Fed Prog%')
    campaign_donation_amount_dollars = dollars('campaign_donation_amount',short_description='Campaign Donor')
    #household_donation = dollars('household_donation',short_description='Household Donor')
    followup = rename_field('needs_followup',short_description='Followup',boolean=True)

    def get_actions(self, request):
        # Disable delete
        actions = super(ResidentAdmin, self).get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions

    def get_queryset(self, request):
        qs = super(ResidentAdmin, self).get_queryset(request)
        return Resident.objects.annotate(wardprecinct=F('household__ward_number')*10+F('household__precinct_number'),
                                         numcontactrecords=Count('contactrecord'),
                                         one=Value(float(1), output_field=FloatField()))



    def full_name(self, obj):
        return obj.full_display_name
    full_name.admin_order_field = ['last_name','first_name']

    def ward_and_precinct(self, obj):
        return str(obj.household.ward_number) + '/' + str(obj.household.precinct_number)
    ward_and_precinct.short_description = 'Wrd/Pct'
    ward_and_precinct.admin_order_field = 'wardprecinct'

    def ordered_street_segment(self, obj):
        return str(obj.household.street_segment)

    ordered_street_segment.short_description = 'Street Segment'
    ordered_street_segment.admin_order_field = 'household__street_segment__ordering'

    def contact_records(self, obj):
        return obj.numcontactrecords
    contact_records.admin_order_field = 'numcontactrecords'


    def export_kml(self, request, queryset):

        root = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
        document = ET.SubElement(root, 'Document')
        for resident in queryset:
            placemark = ET.SubElement(document, 'Placemark');
            ET.SubElement(placemark, 'name').text = resident.resident_address
            ET.SubElement(placemark, 'description').text = resident.full_display_name
            ET.SubElement(ET.SubElement(placemark, 'Point'), 'coordinates').text = str(resident.household.longitude) + ',' + str(
                resident.household.latitude) + ',0'

        indent(root)
        tree = ET.ElementTree(root)
        response = HttpResponse(content_type="application/kml")
        response['Content-Disposition'] = 'attachment; filename="residents.kml"'
        tree.write(response, xml_declaration=True, encoding='utf-8')
        return response

    export_kml.short_description = "Export residents as kml file for maps"

    def voting_rolls_doc(self, request, queryset):
        residents = queryset.order_by(
            'household__ward_number',
            'household__precinct_number',
            'household__street',
            'household__house_number',
            'household__house_number_suffix',
            'household__apartment_number',
            'last_name',
            'first_name'
        )
        polling_places = [{
            'polling_place':pp,
            'residents':list(res)
        } for pp, res in groupby(residents, lambda r: r.household.polling_place)]

        return render(request, 'admin/voting_rolls.html',
                      dict(polling_places=polling_places))

    voting_rolls_doc.short_description = "Make voting rolls document"

    def test_canvass(self, request, queryset):
        residents = queryset
        residents = residents.filter(household__geo_edge__isnull=False)
        #TODO why do some residents not have a geo_edge

        from_resident = residents[0]
        to_resident = residents[1]
        print("BEFORE GRAPH",datetime.now())
        graph = GeoGraph()
        #print("BEFORE PATH", datetime.now())
        #path = graph.find_path(from_resident.household.geo_edge.start_node, to_resident.household.geo_edge.end_node)
        #path = [e for _, e in graph.edges_map.items()]
        from django.db import connection
        #print("BEFORE QUERIES", datetime.now())
        #for q in connection.queries:
        #    print(q['sql'])
        #print("BEFORE RENDER", datetime.now())

        resident_map = dict()  # type: Dict[int,List[Resident]]

        #print("BEFORE TOUR", datetime.now())
        #tour = graph.find_tour(residents)

        print("BEFORE TURFS", datetime.now())
        turfs = graph.find_turfs(residents=residents)
        print("BEFORE RENDER", datetime.now())
        return render(request, 'admin/test_canvass.html', dict(
            turfs = turfs,
        ))

    def canvassing_doc(self, request, queryset):
        residents = queryset.order_by('household__street_segment__ordering','household__street',
                                      'household__house_number',
                                      'household__house_number_suffix',
                                      'household__apartment_number'
                                      )

        street_segments = [{'street_segment':seg,
                            'residents':list(res)}
                           for seg, res in
                           groupby(residents, lambda r: r.household.street_segment)]

        GROUP_SIZE = 64
        canvass_group = {'num_residents': 0, 'num_households': 0, 'street_segments': []}
        canvass_groups = [canvass_group]

        for street_segment in street_segments:
            num_households = len(set(res.resident_address for res in street_segment['residents']))
            street_segment['num_households'] = num_households
            street_segment['num_residents'] = len(street_segment['residents'])
            num_if_include = canvass_group['num_households']+num_households
            if (num_if_include > GROUP_SIZE) and (canvass_group['num_households'] > 0):
                canvass_group = {'num_residents': 0, 'num_households': 0, 'street_segments': []}
                canvass_groups.append(canvass_group)
            canvass_group['street_segments'].append(street_segment)
            canvass_group['num_households'] += num_households
            canvass_group['num_residents'] += len(street_segment['residents'])


        return render(request, 'admin/canvass.html',
                  dict(canvass_groups=canvass_groups))

    canvassing_doc.short_description = "Make canvassing document"

    def mark_canvass_complete(self, request, queryset):
        queryset.values('id').update(canvass_complete=True)
    mark_canvass_complete.short_description = "Mark canvass complete"

    def mark_canvass_complete_ilana(self, request, queryset):
        queryset.values('id').update(canvass_complete_ilana=True)
    mark_canvass_complete_ilana.short_description = "Mark Ilana canvass complete"

    def mark_gotv_canvass_complete(self, request, queryset):
        queryset.values('id').update(gotv_canvass_complete=True)
    mark_gotv_canvass_complete.short_description = "Mark GOTV canvass complete"

    def mark_voted_2017(self, request, queryset):
        queryset.values('id').update(voted_2017_11_07=True)
    mark_voted_2017.short_description = "Mark VOTED 2017"

    def mark_no_facebook_acct(self, request, queryset):
        queryset.values('id').update(facebook_status=FacebookStatus.NO_FB_ACCOUNT)
    mark_no_facebook_acct.short_description = "Mark Facebook: No Account"

    def mark_friend_request(self, request, queryset):
        queryset.values('id').update(facebook_status=FacebookStatus.FRIEND_REQUEST)
    mark_friend_request.short_description = "Mark Facebook: Friend Request"

    def mark_friend(self, request, queryset):
        queryset.values('id').update(facebook_status=FacebookStatus.FRIEND)
    mark_friend.short_description = "Mark Facebook: Friend"

    class TagForm(forms.Form):
        tag = forms.CharField(max_length=64)
        add_or_remove = forms.BooleanField(
            required=False,
            widget=RadioSelect(choices=[(True, 'Add'),(False, 'Remove')])
        )
        _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
        full_queryset = forms.CharField(max_length=999999999,widget=forms.HiddenInput)

    def add_or_remove_tag(self, request, queryset):

        if 'apply' not in request.POST:
            form = self.TagForm(
                initial={
                    '_selected_action': request.POST.getlist(admin.ACTION_CHECKBOX_NAME),
                    'full_queryset': ','.join([str(r.id) for r in queryset])
                }
            )

            return render(request, 'admin/add_or_remove_tag.html', {
                'num_residents': queryset.count(),
                'residents': queryset[:30],
                'tag_form': form,
            })

        form = self.TagForm(request.POST)
        if form.is_valid():
            tag = form.cleaned_data['tag']
            add = form.cleaned_data['add_or_remove']
            resident_ids = list(set(int(id) for id in form.cleaned_data['full_queryset'].split(',')))
            num_residents = len(resident_ids)

            if add:
                count = add_tag_to_resident_id_set(resident_ids, tag)
            else:
                count = remove_tag_from_resident_id_set(resident_ids, tag)

            self.message_user(request, "Successfully %s tag '%s' %s %d of %d selected resident%s." %
                              ("added" if add else "removed", tag, "to" if add else "from",
                               count, num_residents, "s" if num_residents!=1 else ""))
            return HttpResponseRedirect(request.get_full_path())


    add_or_remove_tag.short_description = "Bulk add or remove tag"

admin.site.register(Resident, ResidentAdmin)



class EventAdmin(admin.ModelAdmin):
    list_display = ['name','date']
    ordering = ['date']


admin.site.register(Event, EventAdmin)


class StreetSegmentAdmin(admin.ModelAdmin):
    list_display = ['ordering', 'ward_number', 'street_name', 'house_number_min', 'house_number_max']
    ordering = ['ordering']

admin.site.register(StreetSegment, StreetSegmentAdmin)


class ResidentInline(admin.StackedInline):
    model = Resident
    extra = 0
    can_delete = False
    max_num = 0
    ordering = ['last_name','first_name']
    readonly_fields = ['resident_link']
    fieldsets= ((None, {'fields': ('resident_link', )}),)
    def resident_link(self, obj):
        link = reverse("admin:TalkToTen_resident_change", args=[obj.id])
        return '<a href="%s">%s</a>' % (link, obj)
    resident_link.allow_tags = True
    resident_link.short_description = 'Resident'




class ResidentVolunteerInline(admin.StackedInline):
    class Media:
        css = {
            'all': ('/static/field_box.css',)
        }

    model = Resident
    extra = 0
    can_delete = False
    max_num = 0
    ordering = ['last_name', 'first_name']
    fieldsets = (
        (None, {'fields': [('resident_link','phone','email'), tuple(volunteer_support_fields), tuple(volunteer_option_fields), 'notes', tuple(category_fields)]}),
    )
    readonly_fields = ['resident_link','num_contacts','phone','email','count_elections','donor_federal_amount','donor_local_amount']
    num_contacts = rename_field('num_contacts')

    def resident_link(self, obj):
        link = reverse("admin:TalkToTen_resident_change", args=[obj.id])
        return '<a href="%s">%s</a>' % (link, obj)

    resident_link.allow_tags = True
    resident_link.short_description = 'Resident'

    def get_queryset(self, request):
        return super(ResidentVolunteerInline, self).get_queryset(request).annotate(
            num_contacts=Count('user__contactrecord'))


class VolunteerAdmin(MultiFieldSortableModelAdmin, ForeignKeyAutocompleteAdmin):
    class Media:
        css = {
            'all': ('/static/field_box.css',)
        }

    list_per_page = 50
    search_fields = ['resident__last_name', 'resident__first_name', 'resident__email', 'street', 'resident__notes']

    def get_search_results(self, request, queryset, search_term):
        reg_terms = []
        ssid = None
        for s in search_term.split():
            seg_match = re.search(r"^SEG(\d+)$", s, flags=re.IGNORECASE)
            if seg_match:
                ssid = int(seg_match.group(1))
            else:
                reg_terms.append(s)

        q, d = super(VolunteerAdmin, self).get_search_results(request, queryset, ' '.join(reg_terms))
        if ssid is not None:
            q &= queryset.filter(household__street_segment__id=ssid)
        return q, d


    full_fields = volunteer_household_fields + volunteer_support_fields + volunteer_option_fields + category_fields

    short_fields = volunteer_option_fields + category_fields + ["num_contacts"]
    list_display = (lambda short_fields, full_fields: [x+"_short" if x in short_fields else x for x in full_fields if x != 'street_segment'])(short_fields, full_fields)

    fieldsets = (
        (None, { 'fields': volunteer_household_fields + [tuple(volunteer_support_fields), tuple(volunteer_option_fields), tuple(category_fields)]}),
    )

    readonly_fields = full_fields
    exclude = list(field.name for field in Volunteer._meta.get_fields())

    inlines = [ResidentVolunteerInline, ]

    def address(self, obj):
        return obj.address
    address.admin_order_field = ['street',
                                 'house_number',
                                 'house_number_suffix',
                                 'apartment_number']

    campaign_donation_amount = dollars('campaign_donation_amount', short_description='donation')
    yard_sign = rename_field('yard_sign', choices=Resident.YARD_SIGN_CHOICES)



    volunteer_option_canvass = rename_field('volunteer_option_canvass', short_description='Canvass', boolean=True)
    volunteer_option_canvass_short = rename_field('volunteer_option_canvass', short_description='Canv', boolean=True)

    volunteer_option_gotv = rename_field('volunteer_option_gotv', short_description='GOTV', boolean=True)
    volunteer_option_gotv_short = rename_field('volunteer_option_gotv', short_description='GOTV', boolean=True)

    volunteer_option_election_day = rename_field('volunteer_option_election_day', short_description='Election Day', boolean=True)
    volunteer_option_election_day_short = rename_field('volunteer_option_election_day', short_description='EDay', boolean=True)

    volunteer_option_dear_friend = rename_field('volunteer_option_dear_friend', short_description='Dear Friend', boolean=True)
    volunteer_option_dear_friend_short = rename_field('volunteer_option_dear_friend', short_description='DrFr', boolean=True)

    volunteer_option_needs_followup = rename_field('volunteer_option_needs_followup', short_description='Needs followup',
                                                boolean=True)
    volunteer_option_needs_followup_short = rename_field('volunteer_option_needs_followup', short_description='Foll',
                                                      boolean=True)

    category_it = rename_field('category_it', short_description='Category IT', boolean=True)
    category_it_short = rename_field('category_it', short_description='IT', boolean=True)

    category_fams = rename_field('category_fams', short_description='Category Fams', boolean=True)
    category_fams_short = rename_field('category_fams', short_description='Fams', boolean=True)

    category_dems = rename_field('category_dems', short_description='Category Dems', boolean=True)
    category_dems_short = rename_field('category_dems', short_description='Dems', boolean=True)

    donor_federal_amount, donor_federal_amount_short = (dollars('donor_federal_amount', short_description=s) for s in ('Donor Federal Amount','Fed'))
    donor_local_amount, donor_local_amount_short = (dollars('donor_local_amount', short_description=s) for s in ('Donor Local Amount','Loc'))
    count_elections, count_elections_short = (rename_field('count_elections', short_description=s) for s in ('Count Elections','#Elec'))

    level_of_support = rename_field('level_of_support', choices=SupportLevels.CHOICES)
    level_of_support.admin_order_field='ls'
    num_contacts, num_contacts_short = (rename_field('num_contacts', short_description=s) for s in ('Num Contacts','#Cont'))

    def resident_link(self, obj):
        link = reverse("admin:TalkToTen_resident_change", args=[obj.id])
        return '<a href="%s">%s</a>' % (link, obj)

    resident_link.allow_tags = True
    resident_link.short_description = 'Resident'

    def residents(self, obj):
        rs = obj.resident_set.order_by('last_name', 'first_name')[:7]
        ret = ', '.join(
            '<a href="%s">%s</a>' % (
                reverse("admin:TalkToTen_resident_change", args=[r.id]),
                r.full_display_name
            ) for r in rs[:6])
        if (len(rs) > 6):
            ret += '...'
        return ret

    residents.allow_tags = True

    def ward_and_precinct(self, obj):
        return str(obj.ward_number) + '/' + str(obj.precinct_number)
    ward_and_precinct.short_description = 'Wrd/Pct'
    ward_and_precinct.admin_order_field = ['ward_number','precinct_number']

    def ordered_street_segment(self, obj):
        return str(obj.street_segment)

    ordered_street_segment.short_description = 'Street Segment'
    ordered_street_segment.admin_order_field = 'street_segment__ordering'

    def get_queryset(self, request):
        xx = super(VolunteerAdmin, self).get_queryset(request).annotate(
            campaign_donation_amount=Max('resident__campaign_donation_amount'),
            yard_sign=Max('resident__yard_sign'),
            volunteer_option_canvass=Max('resident__volunteer_option_canvass'),
            volunteer_option_gotv = Max('resident__volunteer_option_gotv'),
            volunteer_option_election_day = Max('resident__volunteer_option_election_day'),
            volunteer_option_dear_friend = Max('resident__volunteer_option_dear_friend'),
            volunteer_option_needs_followup = Max('resident__volunteer_option_needs_followup'),
            level_of_support = Min('resident__level_of_support'),
            category_it = Max('resident__category_it'),
            category_fams = Max('resident__category_fams'),
            category_dems = Max('resident__category_dems'),
            donor_federal_amount = Max('resident__donor_federal_amount'),
            donor_local_amount = Max('resident__donor_local_amount'),
            count_elections = Max('resident__count_elections'),
        ).annotate(ls=Coalesce('level_of_support',10)
        ).annotate(num_contacts = Count('resident__user__contactrecord'))
        #print(xx.query)
        return xx

    list_filter = (
        'ward_number', 'precinct_number', LevelOfSupportFilter('level_of_support'),
        PresentFilter('volunteer_option_canvass', empty_value=False, title='opt: Canv', present_text='Yes', absent_text='No'),
        PresentFilter('volunteer_option_gotv', empty_value=False, title='opt: GOTV', present_text='Yes', absent_text='No'),
        PresentFilter('volunteer_option_election_day', empty_value=False, title='opt: EDay', present_text='Yes', absent_text='No'),
        PresentFilter('volunteer_option_dear_friend', empty_value=False, title='opt: DrFr', present_text='Yes', absent_text='No'),
        PresentFilter('volunteer_option_needs_followup', empty_value=False, title='opt: Foll', present_text='Yes',
                      absent_text='No'),
        PresentFilter('yard_sign', empty_value=Resident.YARD_SIGN_NO, title='Yard Sign', present_text='Yes', absent_text='No'),
        PresentFilter('campaign_donation_amount', empty_value=0),
        PresentFilter('resident__child_name_1', title="has children", present_text='Yes', absent_text='No', empty_value=''),
        PresentFilter('category_it', empty_value=False, title='cat: IT', present_text='Yes',
                      absent_text='No'),
        PresentFilter('category_fams', empty_value=False, title='cat: Fams', present_text='Yes',
                      absent_text='No'),
        PresentFilter('category_dems', empty_value=False, title='cat: Dems', present_text='Yes',
                      absent_text='No'),
        PresentFilter('donor_federal_amount', empty_value=0),
        PresentFilter('donor_local_amount', empty_value=0),
        CountElectionsFilter
    )


admin.site.register(Volunteer, VolunteerAdmin)


class HouseholdAdmin(MultiFieldSortableModelAdmin, ForeignKeyAutocompleteAdmin):

    search_fields = ['resident__last_name', 'resident__first_name', 'resident__email', 'street', 'resident__notes']

    list_display = ['address', 'residents', 'ward_and_precinct', 'ordered_street_segment', 'campaign_donation_amount', 'yard_sign']
    inlines = [ResidentInline, ]
    def address(self, obj):
        return obj.address
    address.admin_order_field = ['street',
                                 'house_number',
                                 'house_number_suffix',
                                 'apartment_number']

    campaign_donation_amount=dollars('campaign_donation_amount',short_description='Total campaign donation')
    readonly_fields = ['campaign_donation_amount', 'yard_sign']

    def resident_link(self, obj):
        link = reverse("admin:TalkToTen_resident_change", args=[obj.id])
        return '<a href="%s">%s</a>' % (link, obj)
    resident_link.allow_tags = True
    resident_link.short_description = 'Resident'


    def residents(self, obj):
        rs = obj.resident_set.order_by('last_name','first_name')[:7]
        ret = ', '.join(
            '<a href="%s">%s</a>' % (
                reverse("admin:TalkToTen_resident_change", args=[r.id]),
                r.full_display_name
            ) for r in rs[:6])
        if (len(rs)>6):
            ret += '...'
        return ret
    residents.allow_tags = True

    def yard_sign(self, obj):
        return ','.join([desc for (c, desc) in Resident.YARD_SIGN_CHOICES if c == obj.yard_sign])
    yard_sign.admin_order_field = ['yard_sign']

    def ward_and_precinct(self, obj):
        return str(obj.ward_number) + '/' + str(obj.precinct_number)
    ward_and_precinct.short_description = 'Wrd/Pct'
    ward_and_precinct.admin_order_field = 'wardprecinct'

    def ordered_street_segment(self, obj):
        return str(obj.street_segment)
    ordered_street_segment.short_description = 'Street Segment'
    ordered_street_segment.admin_order_field = 'street_segment__ordering'

    def get_queryset(self, request):
        qs = super(HouseholdAdmin, self).get_queryset(request)
        return Household.objects.annotate(wardprecinct=F('ward_number')*10+F('precinct_number'),
                                         campaign_donation_amount=Sum('resident__campaign_donation_amount'),
                                         yard_sign=Max('resident__yard_sign'))


admin.site.register(Household, HouseholdAdmin)


class FollowupFilter(SimpleListFilter):
    title = 'Needs Followup'
    parameter_name = 'followup'
    def lookups(self, request, model_admin):
        return [('0','late'),('1', 'today'),('7', 'in the next week'), ('31','in the next month'),('ANY','anytime')]

    def queryset(self, request, queryset):
        val = self.value()
        if (val is None or val == ''):
            return

        if (val == 'ANY'):
            return queryset.filter(follow_up_date__isnull=False)

        try:
            val = int(val)
        except ValueError:
            return

        latest_followup = datetime.now()+timedelta(val)
        return queryset.filter(follow_up_date__lte=latest_followup)



FAR_FUTURE = timezone.now()+timedelta(weeks=52000)


class ContactRecordResource(resources.ModelResource):
    class Meta:
        model = ContactRecord
        fields = [utils.transform(field.name, {'contacter': 'contacter__username', 'resident': 'resident__resident_id_number'})
                  for field in ContactRecord._meta.fields]
        export_order = fields


class ContactRecordAdmin(ExportActionModelAdmin, ForeignKeyAutocompleteAdmin):


    resource_class = ContactRecordResource

    related_search_fields = {
        'resident': ['last_name', 'first_name', 'household__street', 'email']
    }

    list_display = ['resident','contacter','contact_type','contact_date','follow_up_date_non_null', 'status', 'open', 'modified']

    list_per_page = 50


    list_filter = ['status', 'contacter', 'open', FollowupFilter, 'contact_type']

    readonly_fields = ['created', 'modified', 'resident_link']

    search_fields = ['resident__last_name', 'resident__first_name', 'resident__email', 'contacter__last_name', 'contacter__first_name', 'contacter__username', 'email']

    actions = ['make_unreserved', 'make_reserved', 'copy_into_residents', 'make_pending']

    def resident_link(self, obj):
        link = reverse("admin:TalkToTen_resident_change", args=[obj.resident_id])
        return '<a href="%s">%s</a>' % (link, obj.resident)

    resident_link.allow_tags = True
    resident_link.short_description = 'Resident'

    def follow_up_date_non_null(self, obj):
        return obj.follow_up_date

    follow_up_date_non_null.admin_order_field = 'follow_up_date_non_null'
    follow_up_date_non_null.short_description = 'Follow up date'

    exclude = list(field.name for field in ContactRecord._meta.get_fields() if field.name.startswith('interest_area_'))

    def make_unreserved(self, request, queryset):
        queryset.update(status=ContactRecord.COMPLETE_BUT_UNRESERVED)
    make_unreserved.short_description = "Mark selected records as open to new contacts"

    def make_reserved(self, request, queryset):
        queryset.update(status=ContactRecord.COMPLETE)
    make_reserved.short_description = "Mark selected records as closed to new contacts"

    def make_pending(self, request, queryset):
        queryset.update(status=ContactRecord.PENDING)
    make_pending.short_description = "Mark selected records as pending"

    def copy_into_residents(self, request, queryset):
        for contact_record in queryset:
            contact_record.copy_into_resident_and_mark_complete()
    copy_into_residents.short_description = "Copy selected record data into residents table and mark complete"

    def get_changeform_initial_data(self, request):
        return {'contacter': request.user}

    def get_queryset(self, request):
        qs = super(ContactRecordAdmin, self).get_queryset(request)
        return ContactRecord.objects.annotate(
            follow_up_date_non_null=Coalesce('follow_up_date', Value(FAR_FUTURE)))

admin.site.register(ContactRecord, ContactRecordAdmin)

# put out here to avoid running afoul of django error checking on follow_up_date_non_null
ContactRecordAdmin.ordering = ['-open', 'follow_up_date_non_null', '-modified', 'status']


admin.site.unregister(User)

class CustomUserAdmin(UserAdmin):

    def get_urls(self):
        urls = super(CustomUserAdmin, self).get_urls()
        my_urls = [
            url(r'^send_reminder_email/([\d,]+)/',
                self.admin_site.admin_view(self.send_reminder_email_view),
                name='reminder_email')
        ]
        return my_urls + urls

    def __init__(self, *args, **kwargs):
        super(CustomUserAdmin,self).__init__(*args, **kwargs)
        self.actions.append('send_reminder_email_action')

    def send_reminder_email_action(self, request, queryset):
        selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
        referrer = request.META['HTTP_REFERER']
        querystring = ''
        if referrer:
            querystring = '?'+urlencode(dict(next=referrer))
        return HttpResponseRedirect(reverse('admin:reminder_email', args=[','.join(selected)])+querystring)
    send_reminder_email_action.short_description = 'Send reminder email to selected users'

    def send_reminder_email_view(self, request, user_id_string):
        msg_previews = None
        added_text = None
        successful_users = []
        user_ids = user_id_string.split(',')
        users = User.objects.filter(id__in=user_ids).annotate(
            num_pending_contacts=Sum(
                Case(
                    When(contactrecord__status=ContactRecord.PENDING,
                         then=Value(1)), output_field=IntegerField()))).order_by(Lower('username'))

        emailable_users = users.exclude(email__isnull=True).exclude(email='').filter(num_pending_contacts__gt=0)

        next_url = request.POST.get('next', default=request.GET.get('next', reverse('admin:auth_user_changelist')))



        if (request.method == 'POST'):
            preview = 'preview' in request.POST
            added_text = request.POST['added_text']
            mail_connection = None

            msg_previews = []
            for user in emailable_users:

                pending_contact_records = ContactRecord.objects.filter(contacter=user,
                                                                       status=ContactRecord.PENDING).order_by(
                    'modified')
                msg_html = render_to_string('admin/reminder_email.html',
                                            {'user': user,
                                             'pending_contact_records': pending_contact_records,
                                             'added_text': added_text})
                num_records = len(pending_contact_records)
                suffix = '' if num_records == 1 else 's'
                subject = 'TalkToTen Reminder: ' + str(num_records) + ' contact' + suffix + ' pending'
                msg = EmailMessage(subject=subject, to=[user.email])
                msg.content_subtype = 'html'
                try:
                    if preview:
                        msg_previews.append({'headers': msg.message().as_string(), 'body': msg_html})
                    else:
                        if not mail_connection:
                            mail_connection = mail.get_connection()
                            mail_connection.open()
                        msg.body = msg_html
                        msg.connection = mail_connection
                        msg.send()
                    successful_users.append(user)
                except Exception as e:
                    messages.error(request, str(e))

            if mail_connection:
                try:
                    mail_connection.close()
                except Exception as e:
                    messages.error(request, str(e))

            preview_prefix = 'PREVIEW: ' if preview else ''
            if successful_users:
                messages.success(request, preview_prefix + 'Sent message to ' + ', '.join(
                    [user.username for user in successful_users]))
            else:
                messages.warning(request, preview_prefix + 'No messages were sent.')

            if not preview:
                return HttpResponseRedirect(next_url)

        context = dict(self.admin_site.each_context(request),
                       added_text=added_text,
                       msg_previews=msg_previews,
                       next=next_url,
                       users=users,
                       emailable_users=emailable_users)

        return TemplateResponse(request, 'admin/reminder_email_action.html',context)



admin.site.register(User, CustomUserAdmin)

def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i





