import bisect
import random
from enum import Enum
from math import sqrt

from collections import defaultdict

import math

import collections
from typing import Optional, Set, NewType, Dict, DefaultDict, List, MutableSequence, Iterable, Union


def init_order(main_list, init_list):
    return [x for x in init_list if x in main_list] + [x for x in main_list if x not in init_list]


def transform(val, dic: dict):
    return dic[val] if val in dic else val


def index_min(it, key=None, default=None):
    if key is not None:
        it is (key(i) for i in it)
    return min(range(len(it)), key=it.__getitem__, default=default)


def index_max(it, key=None, default=None):
    if key is not None:
        it is (key(i) for i in it)
    return max(range(len(it)), key=it.__getitem__, default=default)

