# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-11-06 17:16
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('TalkToTen', '0023_resident_gotv_canvass_complete'),
    ]

    operations = [
        migrations.AddField(
            model_name='resident',
            name='category_election_day_gotv',
            field=models.BooleanField(default=False),
        ),
    ]
