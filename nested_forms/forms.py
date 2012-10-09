# -*- coding: utf-8 -*-
import re
import logging

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.query import QuerySet
from django.db.models.related import RelatedObject
from django.forms.fields import FileField
from django.forms.formsets import TOTAL_FORM_COUNT, INITIAL_FORM_COUNT, DELETION_FIELD_NAME
from django.forms.models import ModelFormOptions, ModelFormMetaclass, modelformset_factory, \
        inlineformset_factory, BaseInlineFormSet
from django.http import QueryDict
from django.contrib.contenttypes.generic import GenericRelation

logger = logging.getLogger(__name__)

class ComplexBaseInlineFormSet(BaseInlineFormSet):
    """
    A custom base inline formset class, that saves subformsets automatically
    """

    def save_new(self, form, commit=True):
        """
        Saves new objects and associates nested objects to this one.
        """
        obj = super(ComplexBaseInlineFormSet, self).save_new(form, commit)

        if commit and hasattr(form, 'formsets') and isinstance(form.formsets, dict):
            for formset_name, formset in form.formsets.items():
                objects = formset.save()
                getattr(obj, formset_name).add(*objects)

        return obj

    def save(self, commit=True):
        """
        Saves model instances for every form, adding and changing instances
        as necessary, and returns the list of instances.
        """
        if not self.is_valid():
            return

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
    """
    Adds the options "formsets" and "formsets_order" to the ComplexModelForm's Meta.
    """

    def __init__(self, options=None):
        super(ComplexModelFormOptions, self).__init__(options)
        self.formsets = getattr(options, 'formsets', None)
        self.formsets_order = getattr(options, 'formsets_order', None)

class ComplexModelFormMetaclass(ModelFormMetaclass):
    """
    Places the options in the class
    """
    def __new__(cls, name, bases, attrs):
        new_class = super(ComplexModelFormMetaclass, cls).__new__(cls, name, bases, attrs)

        opts = new_class._meta = ComplexModelFormOptions(getattr(new_class, 'Meta', None))

        new_class.base_formsets = {}
        new_class.formset_keys = []

        if getattr(opts, 'formsets', None):
            for formset_name, params in opts.formsets.items():
                new_class.base_formsets[formset_name] = params

            if getattr(opts, 'formsets_order', None):
                new_class.formset_keys = [
                    formset_name
                    for formset_name in opts.formsets_order
                    if formset_name in new_class.base_formsets
                ]
            else:
                """
                If no formsets_order has been submitted, take the default order of the dict keys
                """
                new_class.formset_keys = opts.formsets.keys()

        return new_class

class ComplexModelForm(forms.ModelForm):
    __metaclass__ = ComplexModelFormMetaclass

    def show_errors(self):
        """
        Just prints all errors on all forms, recursively
        """
        logger.debug("CF %s %s %s %s %s" % (self.prefix, self.errors, self.non_field_errors(), self.is_bound, self.is_valid()))
        for formset in self.formsets.values():
            logger.debug("FS %s %s %s %s" % (formset.prefix, formset.errors, formset.non_form_errors(), self.is_valid()))
            for form in formset.forms:
                if hasattr(form, "show_errors"):
                    form.show_errors()
                else:
                    logger.debug("MF %s %s %s %s" % (form.prefix, form.errors, form.non_field_errors(), self.is_valid()))

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
        if changed_data:
            for formset in self.formsets.values():
                if formset is not None:
                    if len(formset.forms) > 0:
                        changed_data.append(formset)
        else:
            for formset in self.formsets.values():
                if formset is not None:
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
                import traceback
                print "KEY ERROR utils/forms.py:155"
                traceback.print_exc()
                self.formsets[formset_name] = None

        if hasattr(self, "formsets_loaded") and callable(self.formsets_loaded):
            self.formsets_loaded()

    def _get_errors(self):
        # full_clean is forced because _errors is sometimes partialy filled.
        self.full_clean()
        return super(ComplexModelForm, self)._get_errors()
    errors = property(_get_errors)

    def _clean_fields(self):
        super(ComplexModelForm, self)._clean_fields()
        for formset_name, formset in getattr(self, 'formsets', {}).items():
            if not formset.is_valid():
                for form in formset.forms:
                    if not form.is_valid():
                        for name, field in form.fields.items():
                            # value_from_datadict() gets the data from the data dictionaries.
                            # Each widget type knows how to retrieve its own data, because some
                            # widgets split data over several HTML fields.
                            value = field.widget.value_from_datadict(form.data, form.files, form.add_prefix(name))
                            try:
                                if isinstance(field, FileField):
                                    initial = form.initial.get(name, field.initial)
                                    value = field.clean(value, initial)
                                else:
                                    value = field.clean(value)
                                if hasattr(form, 'clean_%s' % name) and hasattr(form, 'cleaned_data'):
                                    value = getattr(form, 'clean_%s' % name)()
                            except ValidationError, e:
                                self._errors["%s | %s" % (formset_name, name)] = self.error_class(e.messages)


    def clean(self):
        cleaned_data = super(ComplexModelForm, self).clean()
        for formset in getattr(self, 'formsets', {}).values():
            if formset:
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
        if isinstance(field, GenericRelation):
            return field.related.parent_model
        elif isinstance(field, RelatedObject):
            return field.model
        elif isinstance(field, models.ManyToManyField):
            return field.rel.to
        raise

    def _get_formset(self, name, form, extra=None, initial=None, can_delete=True, \
                     update_button=None, fk_name=None, duplicate=False, \
                     exclude_from_duplication=None, queryset=None, allowed_objects=None, \
                     *args, **kwargs):

        def shift_keys(data, prefix, idx, has_file=False):
            if not data:
                return
            start = re.compile(r"^%s\-(?P<form_idx>\d+)\-(?P<suffix>.*)$" % prefix)
            if has_file:
                if (len(data.keys()) > 0):
                    data_sorted = sorted(data.keys())
                    first_form_key = data_sorted[0]
                    last_form_key = data_sorted[-1]
                    regex = start.match(first_form_key)
                    regex_dict = regex.groupdict()

                    form_idx = int(regex_dict['form_idx'])
                    if form_idx > 0:
                        previous_form_key = "%s-%d-%s" % (
                            prefix,
                            form_idx - 1,
                            regex_dict['suffix'],
                        )
                        if not data.has_key(previous_form_key):
                            data.setlist(previous_form_key, data.getlist(last_form_key))

            for key in sorted(data.keys()):
                regex = start.match(key)

                if regex is None:
                    continue

                regex_dict = regex.groupdict()
                form_idx = int(regex_dict['form_idx'])

                if form_idx < idx:
                    continue

                suffix = regex_dict['suffix']

                next_form_key = "%s-%d-%s" % (
                    prefix,
                    form_idx + 1,
                    suffix,
                )
                if data.has_key(next_form_key):
                    data.setlist(key, data.getlist(next_form_key))
                else:
                    del data[key]


        def resolve_callable(var, args=None, kwargs=None, default=None):
            if args is None:
                args = []

            if kwargs is None:
                kwargs = {}

            if callable(var):
                return var(*args, **kwargs) or default
            else:
                return var or default

        data = self.data.keys() and self.data.copy() or None
        files = self.files.keys() and self.files.copy() or None

        self.full_clean()

        prefix = self.get_formset_prefix(name) # calculates formset's prefix

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

        instance_pk = form._meta.model._meta.pk.name

        if data and prefix:
            for key in data.keys():
                if not key.startswith(prefix):
                    del data[key]
            if not data.keys():
                data = None

            if files is not None:
                for key in files.keys():
                    if not key.startswith(prefix):
                        del files[key]
                if not files:
                    files = None

        if data:
            # Asking to delete last form
            if isinstance(data, QueryDict):
                nb_forms = [int(total_form_count) for total_form_count in data.getlist("%s-%s" % (prefix, TOTAL_FORM_COUNT))]
            else:
                nb_forms = [ int(data["%s-%s" % (prefix, TOTAL_FORM_COUNT)]) ]

            if len(nb_forms) > 1:
                data["%s-%s" % (prefix, TOTAL_FORM_COUNT)] = max(nb_forms)

                if duplicate:
                    last_index = max(nb_forms) - 1

                    start = "%s-%d-" % (prefix, last_index - 1)
                    for key, value in data.iteritems():
                        if key == "%s%s" % (start, instance_pk) or key == "%s%s" % (start, INITIAL_FORM_COUNT):
                            continue

                        cont = False

                        if exclude_from_duplication:
                            for k in exclude_from_duplication:
                                exclude_key = resolve_callable(k, args=[start])
                                if exclude_key[-1] == '-' and key.startswith(exclude_key) or re.match(exclude_key, key):
                                    cont = True
                        if cont:
                            continue

                        if key.startswith(start) and not key.endswith("-%s" % instance_pk):
                            if key.endswith(INITIAL_FORM_COUNT):
                                value = 0
                            new_line = {
                                "%s-%d-%s" % (prefix, last_index, key[len(start):]): value
                            }
                            data.update(new_line)

            if to:
                i = 0
                for _ in range(int(data.get("%s-%s" % (prefix, TOTAL_FORM_COUNT), 0))):
                    pk_key = "%s-%d-%s" % (prefix, i, instance_pk)

                    if i >= int(data["%s-%s" % (prefix, INITIAL_FORM_COUNT)]):
                        i += 1
                        continue

                    pk = data.get(pk_key, 0)
                    pk = str(pk).isdigit() and int(pk) or 0

                    try:
                        to.objects.get(pk = pk)
                    except to.DoesNotExist:
                        shift_keys(data, prefix, i)
                        shift_keys(files, prefix, i)
                        data["%s-%s" % (prefix, TOTAL_FORM_COUNT)] = int(data["%s-%s" % (prefix, TOTAL_FORM_COUNT)]) - 1
                        data["%s-%s" % (prefix, INITIAL_FORM_COUNT)] = int(data["%s-%s" % (prefix, INITIAL_FORM_COUNT)]) - 1
                    else:
                        i += 1

            # Updates form's data with initial data
            if update_button and data.has_key(update_button):
                initial = resolve_callable(initial, args=[instance], default=[])
                for i, pair in enumerate(initial):
                    prefix_ = "%s-%d-" % (prefix, i)

                    map(data.__delitem__, filter(lambda k: k.startswith(prefix_), data.keys()))

                    for key, value in pair.items():
                        name_ = "%s%s" % (prefix_, key)
                        data[name_] = unicode(value)
                if instance.pk:
                    getattr(instance, name).all().delete()

                data.update({ "%s-%s" % (self.add_prefix(name), INITIAL_FORM_COUNT): 0 })
                data.update({ "%s-%s" % (self.add_prefix(name), TOTAL_FORM_COUNT): len(initial) })

            # Deletes a nested form
            if prefix not in self.safe_delete:
                for i in range(int(data.get("%s-%s" % (prefix, TOTAL_FORM_COUNT), 0)))[::-1]:
                    base_key = "%s-%d-" % (prefix, i)

                    if "%s%s" % (base_key, DELETION_FIELD_NAME) in data.keys():
                        objects_deleted = False
                        if to:
                            objects = to.objects.filter(pk = data.get("%s%s" % (base_key, instance_pk)) or 0)
                            if objects.exists():
                                objects_deleted = True
                                for obj in objects:
                                    obj.delete()

                        shift_keys(data, prefix, i)
                        shift_keys(files, prefix, i, True)
                        data["%s-%s" % (prefix, TOTAL_FORM_COUNT)] = int(data["%s-%s" % (prefix, TOTAL_FORM_COUNT)]) - 1
                        if objects_deleted:
                            data["%s-%s" % (prefix, INITIAL_FORM_COUNT)] = int(data["%s-%s" % (prefix, INITIAL_FORM_COUNT)]) - 1

            if "%s-%s" % (prefix, TOTAL_FORM_COUNT) not in data.keys():
                data = files = None

            initial = None
        elif not self.instance.pk:
            initial = resolve_callable(initial, args=[instance], default=[])

        formset = None

        #print prefix, "%s-%s" % (prefix, TOTAL_FORM_COUNT), data and data.get("%s-%s" % (prefix, TOTAL_FORM_COUNT), "NOT SET")
        #print prefix, "%s-%s" % (prefix, INITIAL_FORM_COUNT), data and data.get("%s-%s" % (prefix, INITIAL_FORM_COUNT), "NOT SET")

        if instance.pk:
            if isinstance(field, RelatedObject):
                if not queryset or not isinstance(queryset, QuerySet):
                    queryset = getattr(self.instance, name).all()

                formset_class = inlineformset_factory(
                    instance.__class__,
                    to,
                    form,
                    ComplexBaseInlineFormSet,
                    extra = extra,
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
                        _data = data or {}
                        queryset = to.objects.filter(
                                pk__in = list(to.objects.filter(
                                    **{
                                        field.rel.related_name or field.related.var_name: self.instance.pk
                                    }
                                ).values_list("pk", flat=True)) + [
                                    _data.get('%s-%d-%s' % (prefix, x, instance_pk))
                                    for x in range(int(_data.get("%s-%s" % (prefix, INITIAL_FORM_COUNT), 0)))
                                ]
                        ).distinct()
                if allowed_objects:
                    queryset = allowed_objects.filter(
                        pk__in = queryset.values_list('pk', flat=True)
                    ).distinct()

                formset_class = modelformset_factory(
                    to,
                    form,
                    extra = extra,
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
            if data:
                _data = data or {}
                queryset = to.objects.filter(
                    pk__in = [
                        _data.get('%s-%d-%s' % (prefix, x, instance_pk))
                        for x in range(int(_data.get("%s-%s" % (prefix, INITIAL_FORM_COUNT), 0)))
                    ]
                ).distinct()
            else:
                queryset = to.objects.none()

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
                queryset = queryset,
                initial = not self.instance.pk and isinstance(initial, list) and initial or None,
            )


        if isinstance(field, RelatedObject):
            for form in formset.forms:
                setattr(form.instance, field.field.name, instance)

        try:
            deleted_instance_pks = [ f.instance.pk for f in formset.deleted_forms if f.instance ]
        except:
            deleted_instance_pks = []

        tmp_objs = []

        for form in formset.forms:
            try:
                if form.instance.pk not in deleted_instance_pks:
                    tmp_objs.append(form.instance)
            except Exception:
                pass

        setattr(instance, "_%s" % name, tmp_objs)

        return formset

    def is_valid(self):
        if hasattr(self, "formsets") and isinstance(self.formsets, dict):
            for formset in self.formsets.values():
                if len(formset.forms) > 0 and len(self.data) and (
                    not (formset.is_valid() and all([ f.is_valid() for f in formset.forms ])) or \
                    len(self.data.getlist(formset.add_prefix(TOTAL_FORM_COUNT))) > 1
                ):
                    return False
        return super(ComplexModelForm, self).is_valid()

    def save(self, commit=True):
        if not self.is_valid():
            return

        instance = super(ComplexModelForm, self).save(commit=commit)
        if commit:
            for formset_name in self.formset_keys:
                formset = self.formsets[formset_name]
                objects = formset.save()

                #getattr(
                #    instance,
                #    formset_name
                #).add(*objects)

        return instance
