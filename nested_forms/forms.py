# -*- coding: utf-8 -*-
"""
Nos formfields à nous qu'ils sont trop bien
"""

from django import forms
from django.db import models
from django.db.models.query import QuerySet
from django.db.models.related import RelatedObject
from django.forms.formsets import TOTAL_FORM_COUNT, INITIAL_FORM_COUNT, DELETION_FIELD_NAME
from django.forms.models import ModelFormOptions, ModelFormMetaclass, modelformset_factory, inlineformset_factory, BaseInlineFormSet
from django.http import QueryDict

import re

class ComplexBaseInlineFormSet(BaseInlineFormSet):
    def save_new(self, form, commit=True):
        obj = super(ComplexBaseInlineFormSet, self).save_new(form, commit)

        if commit and hasattr(form, 'formsets'):
            for formset in form.formsets.values():
                formset.save()

        return obj

    def add_fields(self, form, index):
        super(BaseInlineFormSet, self).add_fields(form, index)

    def save(self, commit=True):
        """Saves model instances for every form, adding and changing instances
        as necessary, and returns the list of instances.
        """
        if not commit:
            self.saved_forms = []
            def save_m2m():
                for form in self.saved_forms:
                    form.save_m2m()
            self.save_m2m = save_m2m

        saved_objects = self.save_existing_objects(commit) + self.save_new_objects(commit)

        pk_values = [ o.pk for o in saved_objects ]
        for form in self.initial_forms:
            if self.can_delete:
                raw_delete_value = form._raw_value(DELETION_FIELD_NAME)
                should_delete = form.fields[DELETION_FIELD_NAME].clean(raw_delete_value)
                if not should_delete:
                    pk_name = self._pk_field.name

                    raw_pk_value = form._raw_value(pk_name)

                    # clean() for different types of PK fields can sometimes return
                    # the model instance, and sometimes the PK. Handle either.
                    pk_value = form.fields[pk_name].clean(raw_pk_value)
                    pk_value = getattr(pk_value, 'pk', pk_value)

                    pk_values.append(pk_value)

        qs = self.get_queryset()
        if commit and qs and self.is_valid():
            objects_to_delete = qs.exclude(pk__in = pk_values)
            objects_to_delete.delete()

        return saved_objects

class ComplexModelFormOptions(ModelFormOptions):
    def __init__(self, options=None):
        super(ComplexModelFormOptions, self).__init__(options)
        self.formsets = getattr(options, 'formsets', None)
        self.formsets_order = getattr(options, 'formsets_order', None)

class ComplexModelFormMetaclass(ModelFormMetaclass):
    def __new__(cls, name, bases, attrs):
        new_class = super(ComplexModelFormMetaclass, cls).__new__(cls, name, bases, attrs)

        opts = new_class._meta = ComplexModelFormOptions(getattr(new_class, 'Meta', None))

        base_formsets = {}

        if opts.formsets:
            for formset_name, params in opts.formsets.items():
                base_formsets[formset_name] = params

            new_class.base_formsets = base_formsets
            if opts.formsets_order:
                new_class.formset_keys = [
                    formset_name
                    for formset_name in opts.formsets_order
                    if formset_name in base_formsets
                ]
            elif getattr(opts, 'formsets', None):
                new_class.formset_keys = opts.formsets.keys()
            else:
                new_class.formset_keys = []

        return new_class

class ComplexModelForm(forms.ModelForm):
    __metaclass__ = ComplexModelFormMetaclass

    def show_errors(self):
        print "CF", self.prefix, self.errors, self.non_field_errors(), self.is_valid()
        for name, formset in self.formsets.items():
            print "FS", formset.prefix, formset.errors, formset.non_form_errors(), self.is_valid()
            for form in formset.forms:
                if hasattr(form, "show_errors"):
                    form.show_errors()
                else:
                    print "MF", form.prefix, form.errors, form.non_field_errors(), self.is_valid()

    def __init__(self, *args, **kwargs):
        self.safe_delete = kwargs.pop("safe_delete", [])

        parent_instance_name, parent_instance = kwargs.pop('parent_instance', (None, None))

        super(ComplexModelForm, self).__init__(*args, **kwargs)

        if parent_instance_name and parent_instance:
            setattr(self.instance, parent_instance_name, parent_instance)

        if hasattr(self, "pre_init_formsets"):
            self.pre_init_formsets()

        self.init_formsets()

        changed_data = self.changed_data or []
        for formset in self.formsets.values():
            for form in formset.forms:
                if form.has_changed():
                    changed_data.append(formset)
                    break
        self._changed_data = changed_data

    def init_formsets(self):
        self.formsets = {}

        if not getattr(self, 'formset_keys', None):
            return

        for formset_name in self.formset_keys:
            try:
                self.formsets[formset_name] = self._get_formset(formset_name, **self.base_formsets[formset_name])
            except KeyError:
                pass

        if hasattr(self, "formsets_loaded") and callable(self.formsets_loaded):
            self.formsets_loaded()

    def clean(self):
        cleaned_data = super(ComplexModelForm, self).clean()
        for formset_name, formset in getattr(self, 'formsets', {}).items():
            formset.clean()
        return cleaned_data

    def get_formset_prefix(self, name):
        if self.prefix:
            return self.add_prefix(name)
        else:
            return name

    def get_related_field(self, name):
        return self._meta.model._meta.get_field_by_name(name)[0]

    def get_related_model(self, name):
        field = self.get_related_field(name)
        if isinstance(field, RelatedObject):
            return field.model
        elif isinstance(field, models.ManyToManyField):
            return field.rel.to

    def _get_formset(self, name, form, extra=0, initial=None, can_delete=True, force_change=True, \
                     force_initial=False, update_button=None, fk_name=None, duplicate=False, \
                     exclude_from_duplication=None, queryset=None, force_extra=False):

        def shift_keys(data, prefix, idx):
            #print "shift_keys", prefix, idx
            if not data:
                return
            start = re.compile(r"^%s\-(?P<form_idx>\d+)\-(?P<suffix>.*)$" % prefix)
            for key in sorted(data.keys()):
                r = start.match(key)
                if r is None: continue

                r_dict = r.groupdict()
                form_idx = int(r_dict['form_idx'])
                if form_idx < idx:
                    continue
                suffix = r_dict['suffix']

                next_form_key = "%s-%d-%s" % (
                    prefix,
                    form_idx + 1,
                    suffix,
                )
                #print next_form_key, ":", data.getlist(next_form_key), "=>", key
                if data.has_key(next_form_key):
                    data.setlist(key, data.getlist(next_form_key))
                else:
                    del data[key]

        def resolve_callable(var, args=[], kwargs={}, default=None):
            if callable(var):
                return var(*args, **kwargs) or default
            else:
                return var or default

        data = self.data.keys() and self.data.copy() or None
        files = self.files or None

        self.full_clean()

        prefix = self.get_formset_prefix(name) # calcul du prefix du formset

        if self.is_valid():
            instance = self.save(commit=False)
        else:
            instance = self.instance
        field = self.get_related_field(name)
        to = self.get_related_model(name)

        form = resolve_callable(form, args=[instance])
        extra = resolve_callable(extra, args=[instance], default=0)
        queryset = resolve_callable(queryset, args=[instance])
        update_button = resolve_callable(update_button, args=[self.prefix])

        update = False
        if data:
            # Nettoyage
            if to:
                i = 0
                for j in range(int(data.get("%s-%s" % (prefix, TOTAL_FORM_COUNT), 0))):
                    pk_key = "%s-%d-id" % (prefix, j)
                    pk = data.get(pk_key, 0)
                    if not pk:
                        continue

                    try:
                        to.objects.get(pk = pk)
                    except to.DoesNotExist:
                        shift_keys(data, prefix, i)
                        shift_keys(files, prefix, i)
                        data["%s-%s" % (prefix, TOTAL_FORM_COUNT)] = int(data["%s-%s" % (prefix, TOTAL_FORM_COUNT)]) - 1
                        data["%s-%s" % (prefix, INITIAL_FORM_COUNT)] = int(data["%s-%s" % (prefix, INITIAL_FORM_COUNT)]) - 1

            # Demande d'actualisation des données à partir des données initiales
            if update_button and data.has_key(update_button):
                initial = resolve_callable(initial, args=[instance], default=[])
                for i, pair in enumerate(initial):
                    prefix_ = "%s-%d-" % (prefix, i)

                    map(data.__delitem__, filter(lambda k: k.startswith(prefix_), data.keys()))

                    for key, value in pair.items():
                        name_ = "%s%s" % (prefix_, key)
                        data[name_] = unicode(value)
                        #print "ADD", name_, value
                if instance.pk:
                    queryset = getattr(instance, name).all()
                    queryset.delete()
                data.update({ "%s-%s" % (self.add_prefix(name), INITIAL_FORM_COUNT): 0 })
                data.update({ "%s-%s" % (self.add_prefix(name), TOTAL_FORM_COUNT): len(initial) })

            # Demande de suppression à la volée
            if prefix not in self.safe_delete:
                for i in range(int(data.get("%s-%s" % (prefix, TOTAL_FORM_COUNT), 0)))[::-1]:
                    base_key = "%s-%d-" % (prefix, i)

                    if data.get("%s%s" % (base_key, DELETION_FIELD_NAME), None):
                        #print "DELETE", "%s%s" % (base_key, DELETION_FIELD_NAME), i
                        objects_deleted = False
                        if to:
                            objects = to.objects.filter(pk = data.get("%sid" % base_key) or 0)
                            if objects.count() > 0:
                                objects_deleted = True
                                #print "DELETE PKs", objects.values_list('pk', flat=True)
                                for o in objects:
                                    o.delete()
                        shift_keys(data, prefix, i)
                        shift_keys(files, prefix, i)
                        data["%s-%s" % (prefix, TOTAL_FORM_COUNT)] = int(data["%s-%s" % (prefix, TOTAL_FORM_COUNT)]) - 1
                        if objects_deleted:
                            data["%s-%s" % (prefix, INITIAL_FORM_COUNT)] = int(data["%s-%s" % (prefix, INITIAL_FORM_COUNT)]) - 1

            # Demande de duplication du dernier formulaire
            if isinstance(data, QueryDict) and duplicate:
                nb_forms = map(int, data.getlist("%s-%s" % (prefix, TOTAL_FORM_COUNT)))
                if len(nb_forms) > 1:
                    last_index = max(nb_forms) - 1

                    start = "%s-%d-" % (prefix, last_index - 1)
                    for key, value in data.iteritems():
                        if key == "%sid" % start or key == "%s%s" % (start, INITIAL_FORM_COUNT):
                            continue

                        cont = False

                        if exclude_from_duplication:
                            for k in exclude_from_duplication:
                                exclude_key = resolve_callable(k, args=[start])
                                if exclude_key[-1] == '-' and key.startswith(exclude_key) or re.match(exclude_key, key):
                                    cont = True
                        if cont:
                            continue

                        if key.startswith(start) and not key.endswith("-id"):
                            if key.endswith(INITIAL_FORM_COUNT):
                                value = 0
                            new_line = {
                                "%s-%d-%s" % (prefix, last_index, key[len(start):]): value
                            }
                            data.update(new_line)

            if "%s-%s" % (prefix, TOTAL_FORM_COUNT) not in data.keys():
                data = files = None

            initial = None
        else:
            initial = resolve_callable(initial, args=[instance], default=[])
            if not extra:
                extra = len(initial)

        formset = None

        if instance.pk:
            if isinstance(field, RelatedObject):
                if not queryset or not isinstance(queryset, QuerySet):
                    queryset = getattr(self.instance, name).all()

                formset_class = inlineformset_factory(
                    instance.__class__,
                    to,
                    form,
                    ComplexBaseInlineFormSet,
                    extra = force_extra and extra or 0,
                    formfield_callback = lambda f, **kwargs: f.formfield(**kwargs),
                    fk_name = fk_name,
                )
                formset = formset_class(
                    data = data,
                    files = files,
                    prefix = prefix,
                    instance = instance,
                    queryset = queryset,
                )
            else:
                if not queryset or not isinstance(queryset, QuerySet):
                    queryset = getattr(self.instance, "_%s" % name, None)
                    if not queryset or not isinstance(queryset, QuerySet):
                        queryset = getattr(self.instance, name).all()

                formset_class = modelformset_factory(
                    to,
                    form,
                    extra = force_extra and extra or 0,
                    can_delete=can_delete,
                    formfield_callback = lambda f, **kwargs: f.formfield(**kwargs),
                )
                formset = formset_class(
                    data,
                    files,
                    prefix = prefix,
                    initial = not self.instance.pk and isinstance(initial, list) and initial or None,
                    queryset = queryset,
                )
        else:
            formset_class = modelformset_factory(
                to,
                form,
                extra=extra,
                can_delete=can_delete,
                formfield_callback = lambda f, **kwargs: f.formfield(**kwargs),
            )
            formset = formset_class(
                data,
                files,
                prefix = prefix,
                queryset = to.objects.none(),
                initial = not self.instance.pk and isinstance(initial, list) and initial or None,
            )


        if isinstance(field, RelatedObject):
            for form in formset.forms:
                setattr(form.instance, field.field.name, instance)

        try:
            deleted_instance_pks = [ f.instance.pk for f in formset.deleted_forms if f.instance ]
        except:
            deleted_instance_pks = []

        setattr(instance, "_%s" % name, [])

        for form in formset.forms:
            try:
                if form.instance.pk not in deleted_instance_pks:
                    l = getattr(instance, "_%s" % name)
                    l.append(form.instance)
                    setattr(instance, "_%s" % name, l)
            except Exception, e:
                pass

        return formset

    def is_valid(self):
        if hasattr(self, "formsets"):
            for formset_name, formset in self.formsets.items():
                if len(formset.forms) > 0 and len(self.data) and (
                    not (formset.is_valid() and all([ f.is_valid() for f in formset.forms ])) or \
                    len(self.data.getlist(formset.add_prefix(TOTAL_FORM_COUNT))) > 1
                ):
                    return False
        ret = super(ComplexModelForm, self).is_valid()
        return ret

    def save(self, commit=True):
        instance = super(ComplexModelForm, self).save(commit=False)
        if commit: # and self.is_valid():
            instance.save()
            self.save_m2m()
            for formset in self.formsets.values():
                instances = formset.save()

            self.formsets = {}
            self.data = {}
            self.files = {}
            self.is_bound = False

            for formset_name, formset_values in self.base_formsets.items():
                new_formset_values = dict(formset_values)
                new_formset_values.update(
                    {
                        'initial': None,
                        'extra': 0,
                    }
                )

                self.formsets[formset_name] = self._get_formset(formset_name, **formset_values)

            if hasattr(self, "formsets_loaded") and callable(self.formsets_loaded):
                self.formsets_loaded()

        return instance

