# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-09-06 15:35
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('TalkToTen', '0010_resident_to_canvass'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contactrecord',
            name='status',
            field=models.PositiveSmallIntegerField(choices=[(0, 'Pending'), (1, 'Complete - Close resident to new contacts'), (2, 'Complete - Open resident to new contacts')], default=0),
        ),
    ]
