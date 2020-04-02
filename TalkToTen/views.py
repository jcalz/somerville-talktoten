from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.forms.models import modelformset_factory
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from Campaign import settings
from TalkToTen.forms import MatchForm, ContactRecordForm
from TalkToTen.models import ContactRecord, Resident, ContactRecordActionChoices


def user_resident_processor(request):
    if request.user.is_authenticated:
        resident = Resident.objects.filter(user=request.user).first()
    else:
        resident = None
    return {'user_resident': resident}

@login_required()
def find_matches(request):
    pending_contacts = ContactRecord.objects.pending_contacts_for_user(request.user)
    if (request.method == 'POST'):
        form = MatchForm(request.POST)
        potential_matches = form.find_potential_matches(request.user, ('as_resident' in request.POST))
    else:
        form = MatchForm()
        potential_matches = None
    return render(request, 'matches.html', dict(form=form, pending_contacts=pending_contacts, potential_matches=potential_matches))

@login_required()
@require_POST
def add_to_contacts(request):
    resident_ids = request.POST.getlist('id')
    for resident_id in resident_ids:
        resident = Resident.objects.get(id=resident_id)
        if not ContactRecord.objects.resident_available_for_match(resident):
            continue
        defaults = {'status': ContactRecord.PENDING}
        if (resident.phone):
            defaults['phone']=resident.phone
        if (resident.email):
            defaults['email']=resident.email
        contact_record, created = ContactRecord.objects.get_or_create(contacter=request.user, resident=resident, defaults=defaults)
        if not created:
            #reopen record
            contact_record.status = ContactRecord.PENDING
            contact_record.save()
    return redirect('contacts')


ContactRecordFormSet = modelformset_factory(ContactRecord, form=ContactRecordForm, extra=0)

@login_required()
def contacts(request):
    contact_records = ContactRecord.objects.filter(contacter=request.user, status=ContactRecord.PENDING).order_by('resident__last_name','resident__first_name')
    if not contact_records:
        return redirect('find_matches')
    post_data = request.POST if request.method=='POST' else None
    formset = ContactRecordFormSet(data=post_data, queryset=contact_records)
    if post_data and formset.is_valid():
        email_contacts = []
        for form in formset.forms: #type: ContactRecordForm
            if form.has_changed():
                contact_record = form.save(commit=False)
                action = form.cleaned_data['action']
                if (action == ContactRecordActionChoices.RELINQUISH):
                    contact_record.delete()
                    messages.success(request,'Removed '+contact_record.resident.full_display_name+' from contact list.')
                elif (action == ContactRecordActionChoices.SEND_MAIL):
                    email_contacts.append(contact_record)
                    contact_record.save()
                elif (action == ContactRecordActionChoices.FOLLOW_UP) or (action == ContactRecordActionChoices.NO_FOLLOW_UP):
                    contact_record.copy_into_resident_and_mark_complete(action)
                    messages.success(request,
                                     'Submitted ' + contact_record.resident.full_display_name + '.  Thank you.')
                form.save_m2m()

        if (email_contacts):
            return redirect('contact_email', ','.join(str(c.id) for c in email_contacts))
        else:
            return redirect('contacts')
    return render(request, 'contacts.html', dict(formset=formset))

@login_required()
def contact_email(request, contact_record_id_string):
    user = request.user
    contact_record_ids = contact_record_id_string.split(',')
    contact_records = ContactRecord.objects.filter(id__in=contact_record_ids).order_by('resident__last_name','resident__first_name')

    if not contact_records:
        formset = ContactRecordFormSet()
        messages.error(request, 'Bad contact record, won\'t send email.')
        return redirect('contacts')

    for contact_record in contact_records:
        if (contact_record.contacter != user) or (contact_record.status != ContactRecord.PENDING) or (not contact_record.email):
            messages.error(request, 'Bad contact record, won\'t send email.')
            return redirect('contacts')

    charmap = {ord(c): None for c in '<>@"'}
    to = [contact_record.resident.full_display_name.translate(charmap) + ' <' + contact_record.email.replace('>','') + '>' for contact_record in contact_records]

    if (user.email):
        reply_to = [(user.get_full_name() or user.get_username()).translate(charmap) + ' <' + user.email.replace('>','') + '>']
    else:
        reply_to = None

    cc = reply_to
    bcc = ["TalkToTen Administrator <TTT@stephanieforsomerville.com>"]

    from_email = (user.get_full_name() or user.get_username()).translate(charmap)+ ' c/o TalkToTen <'+settings.DEFAULT_FROM_EMAIL+'>'

    if (request.method == 'POST'):
        body = request.POST['body']
        subject = request.POST['subject']
        msg = EmailMessage(from_email=from_email, subject=subject, to=to, reply_to=reply_to, body=body, cc=cc, bcc=bcc)
        msg.send()
        messages.success(request, 'Sent message to ' + ', '.join([contact_record.resident.full_display_name for contact_record in contact_records]))

        for contact_record in contact_records:
            contact_record.copy_into_resident_and_mark_complete()
            messages.success(request,
                             'Submitted ' + contact_record.resident.full_display_name + ' for follow-up.  Thank you.')
        return redirect('contacts')

    body = render_to_string('contact_email_message.txt',context=dict(contact_records=contact_records, user=user))
    subject = 'Information about Stephanie Hirsch for Alderman at Large'

    return render(request, 'contact_email.html', dict(to=', '.join(to), from_email=from_email, body=body, subject=subject, reply_to=reply_to[0] if reply_to else None,
                                                      cc=cc[0] if cc else None, bcc=bcc[0] if bcc else None))
