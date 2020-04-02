# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2019-01-15 17:22
from __future__ import unicode_literals

from django.db import migrations, models
from django.db.models import F

def archive_canvass_complete(apps, schema_editor):
    Resident = apps.get_model('TalkToTen', 'Resident')
    Resident.objects.update(canvass_complete_2017=F('canvass_complete'), canvass_complete=False)

class Migration(migrations.Migration):

    dependencies = [
        ('TalkToTen', '0029_resident_voted_2018_09_04'),
    ]

    operations = [
        migrations.AddField(
            model_name='resident',
            name='canvass_complete_2017',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='resident',
            name='canvass_complete_ilana',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='resident',
            name='facebook_status',
            field=models.CharField(choices=[('U', 'Unchecked'), ('N', 'No Facebook Account'), ('R', 'Sent Friend Request'), ('F', 'Friend')], default='U', max_length=1),
        ),
        migrations.AddField(
            model_name='resident',
            name='level_of_support_ilana',
            field=models.PositiveSmallIntegerField(blank=True, choices=[(None, 'Unknown'), (1, 'Definite support'), (2, 'Possible support'), (3, 'Undecided'), (4, 'Not really interested'), (5, 'Definitely not interested')], null=True),
        ),
        migrations.AddField(
            model_name='resident',
            name='voted_2018_11_06',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(archive_canvass_complete)
    ]
