# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-05-29 17:17
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('TalkToTen', '0009_auto_20170515_0902'),
    ]

    operations = [
        migrations.AddField(
            model_name='resident',
            name='to_canvass',
            field=models.BooleanField(default=False),
        ),
    ]
