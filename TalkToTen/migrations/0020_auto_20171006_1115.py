# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-10-06 15:15
from __future__ import unicode_literals

from django.db import migrations, models

category_it_list = []

def chunk_list(n, list):
    l = len(list)
    i = 0
    while i < l:
        yield list[i:i+n]
        i += n


def populate_categories(apps, schema_editor):
    Resident = apps.get_model('TalkToTen', 'Resident')
    for category_it_sublist in chunk_list(100, category_it_list):
        Resident.objects.filter(resident_id_number__in=category_it_sublist).update(category_it=True)
    for category_fams_sublist in chunk_list(100, category_fams_list):
        Resident.objects.filter(resident_id_number__in=category_fams_sublist).update(category_fams=True)
    for category_dems_sublist in chunk_list(100, category_dems_list):
        Resident.objects.filter(resident_id_number__in=category_dems_sublist).update(category_dems=True)


class Migration(migrations.Migration):

    dependencies = [
        ('TalkToTen', '0019_resident_volunteer_option_needs_followup'),
    ]

    operations = [
        migrations.AddField(
            model_name='resident',
            name='category_dems',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='resident',
            name='category_fams',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='resident',
            name='category_it',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(populate_categories)
    ]
