# -*- coding: utf-8 -*-

from django.utils import unittest

from django.forms.formsets import TOTAL_FORM_COUNT, INITIAL_FORM_COUNT, DELETION_FIELD_NAME
from geniustrade.apps.utils.forms import ComplexModelForm
from geniustrade.apps.third_parties.models import ThirdParty, Contact, Country
from django.http import QueryDict
from django import forms

def get_contact_form(third_party):
    class ContactForm(forms.ModelForm):

        def save(self, commit=True):
            contact = super(ContactForm, self).save(commit=False)
            contact.third_party = third_party
            if commit:
                contact.save()
            return contact

        class Meta:
            model = Contact
            fields = [
                'title',
                'name',
            ]
    return ContactForm

class ThirdPartyComplexModelFormTest(unittest.TestCase):
    def setUp(self):
        self.third_party = ThirdParty.objects.create(
            kind='P',
            name='test',
            step='S1',
            country = Country.objects.get(code='US'),
        )

        self.contact = self.third_party.contacts.create(
            title='mr',
            name='test',
        )

    def tearDown(self):
        self.third_party.delete()

class ThirdPartyComplexModelFormDefaultTest(ThirdPartyComplexModelFormTest):
    class ThirdPartyForm(ComplexModelForm):
        class Meta:
            """ méta informations du formulaire de création """
            model = ThirdParty
            fields = [
                'name',
            ]
            formsets = {
                'contacts': {
                    'form': lambda instance: get_contact_form(instance),
                },
            }

    def test_default_should_have_0_subform(self):
        form = self.ThirdPartyForm()
        self.assertEqual(len(form.formsets['contacts'].forms), 0)

    def test_with_instance_should_have_1_subform(self):
        form = self.ThirdPartyForm(instance=self.third_party)
        self.assertEqual(len(form.formsets['contacts'].forms), 1)

    def test_should_not_be_valid_with_no_data(self):
        form = self.ThirdPartyForm({})
        self.assertFalse(form.is_valid())

    def test_click_on_add_button_should_have_1_subform(self):
        """
        Le click sur un bouton génère 2 variables passées au formulaire
        """
        query_string = "&".join([
            "contacts-%(total)s=0",
            "contacts-%(total)s=1",
            "contacts-%(initial)s=0",
        ]) % {
            'total': TOTAL_FORM_COUNT,
            'initial': INITIAL_FORM_COUNT,
        }

        q = QueryDict(query_string)
        form = self.ThirdPartyForm(q)
        self.assertEqual(len(form.formsets['contacts'].forms), 1)

    def test_delete_subform(self):
        """
        Le click sur un bouton génère 2 variables passées au formulaire
        """
        query_string = "&".join([
            "name=test",
            "contacts-%(total)s=1",
            "contacts-%(initial)s=1",
            "contacts-0-id=%(contact_id)d",
            "contacts-0-title=mr",
            "contacts-0-name=test",
            "contacts-0-%(delete)s=",
        ]) % {
            'total': TOTAL_FORM_COUNT,
            'initial': INITIAL_FORM_COUNT,
            'delete': DELETION_FIELD_NAME,
            'contact_id': self.contact.id,
        }

        q = QueryDict(query_string)
        form = self.ThirdPartyForm(q, instance=self.third_party)

        self.assertEqual(len(form.formsets['contacts'].forms), 0)
        self.assertEqual(self.third_party.contacts.count(), 0)

    def test_delete_invalid_subform(self):
        """
        Le click sur un bouton génère 2 variables passées au formulaire
        """
        query_string = "&".join([
            "name=test",
            "contacts-%(total)s=1",
            "contacts-%(initial)s=1",
            "contacts-0-id=%(contact_id)d",
            "contacts-0-title=xxx",
            "contacts-0-name=test",
            "contacts-0-%(delete)s=",
        ]) % {
            'total': TOTAL_FORM_COUNT,
            'initial': INITIAL_FORM_COUNT,
            'delete': DELETION_FIELD_NAME,
            'contact_id': self.contact.id,
        }

        q = QueryDict(query_string)
        form = self.ThirdPartyForm(q, instance=self.third_party)

        self.assertTrue(form.is_valid())
        self.assertEqual(len(form.formsets['contacts'].forms), 0)
        self.assertEqual(self.third_party.contacts.count(), 0)

    def test_delete_invalid_subform_management(self):
        """
        Le click sur un bouton génère 2 variables passées au formulaire
        """
        query_string = "&".join([
            "name=test",
            "contacts-%(total)s=2",
            "contacts-%(initial)s=2",
            "contacts-0-title=xxx",
            "contacts-0-name=test",
            "contacts-0-%(delete)s=",
        ]) % {
            'total': TOTAL_FORM_COUNT,
            'initial': INITIAL_FORM_COUNT,
            'delete': DELETION_FIELD_NAME,
        }

        q = QueryDict(query_string)
        form = self.ThirdPartyForm(q, instance=self.third_party)
        self.assertTrue(form.is_valid())
        self.assertEqual(self.third_party.contacts.count(), 1)
        self.assertEqual(len(form.formsets['contacts'].forms), 0)
        form.save()
        self.assertEqual(self.third_party.contacts.count(), 0)


    def test_add_subform(self):
        """
        Le click sur un bouton génère 2 variables passées au formulaire
        """
        query_string = "&".join([
            "name=test",
            "contacts-%(total)s=2",
            "contacts-%(initial)s=1",
            "contacts-0-id=%(contact_id)d",
            "contacts-0-title=mr",
            "contacts-0-name=test",
            "contacts-1-title=mr",
            "contacts-1-name=test2",
        ]) % {
            'total': TOTAL_FORM_COUNT,
            'initial': INITIAL_FORM_COUNT,
            'delete': DELETION_FIELD_NAME,
            'contact_id': self.contact.id,
        }

        q = QueryDict(query_string)
        form = self.ThirdPartyForm(q, instance=self.third_party)

        self.assertTrue(form.is_valid())

        self.assertEqual(self.third_party.contacts.count(), 1)
        form.save()
        self.assertEqual(self.third_party.contacts.count(), 2)

    def test_bad_form(self):
        query_string = "toto=titi"
        q = QueryDict(query_string)

        form = self.ThirdPartyForm(q, instance=self.third_party)

        self.assertFalse(form.is_valid())

class ThirdPartyComplexModelFormWithExtra1Test(ThirdPartyComplexModelFormTest):
    class ThirdPartyForm(ComplexModelForm):
        class Meta:
            """ méta informations du formulaire de création """
            model = ThirdParty
            fields = [
                'name',
            ]
            formsets = {
                'contacts': {
                    'form': lambda instance: get_contact_form(instance),
                    'extra': 1,
                },
            }

    def test_should_have_1_subform(self):
        form = self.ThirdPartyForm()
        self.assertEqual(len(form.formsets['contacts'].forms), 1)

    def test_should_have_2_subforms_with_instance(self):
        form = self.ThirdPartyForm(instance=self.third_party)
        self.assertEqual(len(form.formsets['contacts'].forms), 2)

class ThirdPartyComplexModelFormWithInitialTest(ThirdPartyComplexModelFormTest):
    class ThirdPartyForm(ComplexModelForm):
        class Meta:
            """ méta informations du formulaire de création """
            model = ThirdParty
            fields = [
                'name',
            ]
            formsets = {
                'contacts': {
                    'form': lambda instance: get_contact_form(instance),
                    'initial': [
                        {
                            'title': 'mrs',
                            'name': 'initial',
                        }
                    ],
                    #'update_button': lambda prefix: '%s-update' % prefix,
                    'update_button': 'contacts-update',
                },
            }

    def test_should_have_0_subform(self):
        form = self.ThirdPartyForm()
        self.assertEqual(len(form.formsets['contacts'].forms), 0)

    def test_update(self):
        query_string = "&".join([
            "name=test",
            "contacts-%(total)s=1",
            "contacts-%(initial)s=1",
            "contacts-0-id=%(contact_id)d",
            "contacts-0-title=xxx",
            "contacts-0-name=test",
            "contacts-update=",
        ]) % {
            'total': TOTAL_FORM_COUNT,
            'initial': INITIAL_FORM_COUNT,
            'delete': DELETION_FIELD_NAME,
            'contact_id': self.contact.id,
        }

        q = QueryDict(query_string)
        form = self.ThirdPartyForm(q, instance=self.third_party)
        form.save()
        self.assertEqual(self.third_party.contacts.count(), 1)
        self.assertEqual(self.third_party.contacts.all()[0].name, 'initial')

class ThirdPartyComplexModelFormWithInitialAndExtraTest(unittest.TestCase):
    class ThirdPartyForm(ComplexModelForm):
        class Meta:
            """ méta informations du formulaire de création """
            model = ThirdParty
            fields = [
                'name',
            ]
            formsets = {
                'contacts': {
                    'form': lambda instance: get_contact_form(instance),
                    'extra': 1,
                    'initial': [
                        {
                            'title': 'mrs',
                            'name': 'initial',
                        }
                    ]
                },
            }

    def test_should_have_subforms(self):
        form = self.ThirdPartyForm()
        self.assertEqual(len(form.formsets['contacts'].forms), 1)


