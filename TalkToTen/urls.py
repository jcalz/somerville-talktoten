from django.conf.urls import url
from django.views.generic import RedirectView

from TalkToTen import views
from django.contrib import admin

admin.site.site_header = 'Stephanie for Somerville'

urlpatterns = [
    url(r'^$', RedirectView.as_view(url='contacts/'), name='index'),
    url(r'^match/', views.find_matches, name='find_matches'),
    url(r'^addcontacts/', views.add_to_contacts, name='add_to_contacts'),
    url(r'^contacts/', views.contacts, name='contacts'),
    url(r'^contact_email/([\d,]+)/',views.contact_email, name='contact_email'),
]
