from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from .forms import ConfigurationQuestionAdminForm
from .models import (
    ConfigurationOption,
    ConfigurationQuestion,
    FlowConfigurationRequirement,
    Problem,
    ProductRange,
    StepChoice,
    StepImage,
    TroubleshootingFlow,
    TroubleshootingStep,
)


class ProblemInline(admin.TabularInline):
    model = Problem
    extra = 0
    fields = ('name', 'is_active', 'sort_order')
    show_change_link = True


class ConfigurationOptionInline(admin.TabularInline):
    model = ConfigurationOption
    extra = 0
    fields = ('label', 'is_active', 'sort_order')


class FlowConfigurationRequirementFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        question_ids = set()
        for form in self.forms:
            if form.errors or form.cleaned_data.get('DELETE'):
                continue
            option = form.cleaned_data.get('option')
            if option is None:
                continue
            if option.question_id in question_ids:
                raise ValidationError(
                    'A flow can require only one option per question.',
                )
            question_ids.add(option.question_id)


class FlowConfigurationRequirementInline(admin.TabularInline):
    model = FlowConfigurationRequirement
    formset = FlowConfigurationRequirementFormSet
    extra = 0
    fields = ('option',)
    autocomplete_fields = ('option',)


class FlowInline(admin.TabularInline):
    model = TroubleshootingFlow
    extra = 0
    fields = ('name', 'description', 'is_active')
    show_change_link = True


class TroubleshootingStepInline(admin.TabularInline):
    model = TroubleshootingStep
    extra = 0
    fields = ('title', 'step_type', 'is_active', 'sort_order')
    show_change_link = True


class StepChoiceInline(admin.TabularInline):
    model = StepChoice
    # A choice has both a source step and a destination step; this is its owner.
    fk_name = 'step'
    extra = 0
    fields = ('label', 'next_step', 'sort_order')
    autocomplete_fields = ('next_step',)


class StepImageInline(admin.TabularInline):
    model = StepImage
    extra = 0
    fields = ('image', 'caption', 'alt_text', 'description', 'sort_order')


@admin.register(ProductRange)
class ProductRangeAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'sort_order', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    ordering = ('sort_order', 'name')
    readonly_fields = ('created_at', 'updated_at')
    fields = (
        'name',
        'description',
        'image',
        'is_active',
        'sort_order',
        'created_at',
        'updated_at',
    )
    inlines = (ProblemInline,)


@admin.register(ConfigurationQuestion)
class ConfigurationQuestionAdmin(admin.ModelAdmin):
    form = ConfigurationQuestionAdminForm
    list_display = (
        'name',
        'phase',
        'depends_on_option',
        'problem',
        'is_required',
        'is_active',
        'sort_order',
    )
    list_filter = ('phase', 'is_required', 'is_active')
    search_fields = (
        'name',
        'help_text',
        'applies_to_products__name',
        'problem__name',
    )
    autocomplete_fields = (
        'applies_to_products',
        'problem',
        'depends_on_option',
    )
    list_select_related = ('problem', 'depends_on_option')
    inlines = (ConfigurationOptionInline,)


@admin.register(ConfigurationOption)
class ConfigurationOptionAdmin(admin.ModelAdmin):
    list_display = ('label', 'question', 'is_active', 'sort_order')
    list_filter = ('question__phase', 'is_active')
    search_fields = ('label', 'question__name', 'question__applies_to_products__name')
    autocomplete_fields = ('question',)
    list_select_related = ('question',)


@admin.register(Problem)
class ProblemAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_range', 'is_active', 'sort_order')
    list_filter = ('product_range', 'is_active')
    search_fields = ('name', 'description', 'product_range__name')
    autocomplete_fields = ('product_range',)
    list_select_related = ('product_range',)
    inlines = (FlowInline,)


@admin.register(TroubleshootingFlow)
class TroubleshootingFlowAdmin(admin.ModelAdmin):
    list_display = ('name', 'problem', 'start_step', 'is_active', 'updated_at')
    list_filter = ('is_active', 'problem__product_range')
    search_fields = ('name', 'description', 'problem__name')
    autocomplete_fields = ('problem', 'start_step')
    list_select_related = ('problem', 'problem__product_range', 'start_step')
    readonly_fields = ('created_at', 'updated_at')
    fields = (
        'problem',
        'name',
        'description',
        'is_active',
        'start_step',
        'created_at',
        'updated_at',
    )
    inlines = (
        FlowConfigurationRequirementInline,
        TroubleshootingStepInline,
    )


@admin.register(TroubleshootingStep)
class TroubleshootingStepAdmin(admin.ModelAdmin):
    # Choices and images belong to a step, so both are edited beside that step.
    list_display = ('title', 'flow', 'step_type', 'is_active', 'sort_order')
    list_filter = ('step_type', 'is_active', 'flow__problem__product_range')
    search_fields = (
        'title',
        'instructions',
        'details',
        'flow__name',
        'flow__problem__name',
    )
    autocomplete_fields = ('flow',)
    list_select_related = ('flow', 'flow__problem', 'flow__problem__product_range')
    readonly_fields = ('created_at', 'updated_at')
    fields = (
        'flow',
        'title',
        'step_type',
        'instructions',
        'details',
        'notes',
        'warning',
        'guide_file',
        'is_active',
        'sort_order',
        'created_at',
        'updated_at',
    )
    inlines = (StepChoiceInline, StepImageInline)


@admin.register(StepChoice)
class StepChoiceAdmin(admin.ModelAdmin):
    list_display = ('label', 'step', 'next_step', 'sort_order')
    search_fields = ('label', 'step__title', 'next_step__title')
    autocomplete_fields = ('step', 'next_step')
    list_select_related = ('step', 'next_step')


@admin.register(StepImage)
class StepImageAdmin(admin.ModelAdmin):
    list_display = ('caption', 'step', 'alt_text', 'sort_order')
    search_fields = ('caption', 'description', 'alt_text', 'step__title')
    autocomplete_fields = ('step',)
    list_select_related = ('step',)


admin.site.site_header = 'BCM-Troubleshooting Web administration'
admin.site.site_title = 'BCM-Troubleshooting Web admin'
admin.site.index_title = 'Manage troubleshooting content'
