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
    verbose_name = 'problem'
    verbose_name_plural = 'Problems users can select for this product'
    fields = ('name', 'is_active', 'sort_order')
    show_change_link = True


class ConfigurationOptionInline(admin.TabularInline):
    model = ConfigurationOption
    extra = 0
    verbose_name = 'answer option'
    verbose_name_plural = 'Answer options shown to users'
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
    verbose_name = 'equipment requirement'
    verbose_name_plural = 'Equipment requirements (optional; limit this guide to selected answers)'
    fields = ('option',)
    autocomplete_fields = ('option',)


class FlowInline(admin.TabularInline):
    model = TroubleshootingFlow
    extra = 0
    verbose_name = 'troubleshooting guide'
    verbose_name_plural = 'Troubleshooting guides for this problem'
    fields = ('name', 'description', 'is_active')
    show_change_link = True


class TroubleshootingStepInline(admin.TabularInline):
    model = TroubleshootingStep
    extra = 0
    verbose_name = 'guide step'
    verbose_name_plural = 'Guide steps (add steps here, then set the starting step after saving)'
    fields = ('title', 'step_type', 'is_active', 'sort_order')
    show_change_link = True


class StepChoiceInline(admin.TabularInline):
    model = StepChoice
    # A choice has both a source step and a destination step; this is its owner.
    fk_name = 'step'
    extra = 0
    verbose_name = 'answer choice'
    verbose_name_plural = 'Answer choices (leave the next step blank to end this path)'
    fields = ('label', 'next_step', 'sort_order')
    autocomplete_fields = ('next_step',)


class StepImageInline(admin.TabularInline):
    model = StepImage
    extra = 0
    verbose_name = 'step image'
    verbose_name_plural = 'Images and diagrams for this step'
    fields = ('image', 'caption', 'alt_text', 'description', 'sort_order')


@admin.register(ProductRange)
class ProductRangeAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'sort_order', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    ordering = ('sort_order', 'name')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'image'),
            'description': (
                'Create the equipment family users will choose before '
                'they describe their issue.'
            ),
        }),
        ('Display settings', {
            'fields': ('is_active', 'sort_order'),
            'description': (
                'Only active products appear to technicians. Lower sort '
                'numbers appear earlier in product lists.'
            ),
        }),
        ('Record history', {
            'fields': ('created_at', 'updated_at'),
        }),
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
    fieldsets = (
        ('Question shown to users', {
            'fields': ('name', 'help_text', 'phase', 'is_required', 'is_active', 'sort_order'),
            'description': (
                'Use System configuration for equipment details collected '
                'before issue selection. Use Problem diagnosis for questions '
                'that narrow down a selected issue.'
            ),
        }),
        ('Where the question appears', {
            'fields': ('applies_to_products', 'problem'),
            'description': (
                'Select every product this question applies to. A problem is '
                'optional and is used only for diagnosis questions.'
            ),
        }),
        ('Conditional display', {
            'fields': ('depends_on_option',),
            'description': (
                'Optional: show this question only after the user selects '
                'the specified answer to another question.'
            ),
        }),
    )


@admin.register(ConfigurationOption)
class ConfigurationOptionAdmin(admin.ModelAdmin):
    list_display = ('label', 'question', 'is_active', 'sort_order')
    list_filter = ('question__phase', 'is_active')
    search_fields = ('label', 'question__name', 'question__applies_to_products__name')
    autocomplete_fields = ('question',)
    list_select_related = ('question',)
    fieldsets = (
        (None, {
            'fields': ('question', 'label'),
            'description': (
                'Add one selectable answer to a question. Questions can also '
                'be edited with their answer options on the question page.'
            ),
        }),
        ('Display settings', {
            'fields': ('is_active', 'sort_order'),
            'description': (
                'Only active answers are offered to technicians. Lower sort '
                'numbers appear earlier.'
            ),
        }),
    )


@admin.register(Problem)
class ProblemAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_range', 'is_active', 'sort_order')
    list_filter = ('product_range', 'is_active')
    search_fields = ('name', 'description', 'product_range__name')
    autocomplete_fields = ('product_range',)
    list_select_related = ('product_range',)
    inlines = (FlowInline,)
    fieldsets = (
        (None, {
            'fields': ('product_range', 'name', 'description'),
            'description': (
                'Describe one issue or symptom and choose the product range '
                'it belongs to.'
            ),
        }),
        ('Display settings', {
            'fields': ('is_active', 'sort_order'),
            'description': (
                'Only active problems are available to technicians. Lower '
                'sort numbers appear earlier.'
            ),
        }),
    )


@admin.register(TroubleshootingFlow)
class TroubleshootingFlowAdmin(admin.ModelAdmin):
    list_display = ('name', 'problem', 'start_step', 'is_active', 'updated_at')
    list_filter = ('is_active', 'problem__product_range')
    search_fields = ('name', 'description', 'problem__name')
    autocomplete_fields = ('problem', 'start_step')
    list_select_related = ('problem', 'problem__product_range', 'start_step')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('problem', 'name', 'description'),
            'description': (
                'Create one guide for a problem. Add the guide steps below, '
                'save, then reopen this guide to choose its starting step.'
            ),
        }),
        ('Guide behavior', {
            'fields': ('is_active', 'start_step'),
            'description': (
                'Publish only when the flow and its starting step are ready. '
                'A starting step must belong to this guide.'
            ),
        }),
        ('Record history', {
            'fields': ('created_at', 'updated_at'),
        }),
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
    fieldsets = (
        ('Step content', {
            'fields': ('flow', 'title', 'step_type', 'instructions', 'details'),
            'description': (
                'Write one clear action or question per step. Use a question '
                'or decision when users need to choose an answer.'
            ),
        }),
        ('Additional guidance', {
            'fields': ('notes', 'warning', 'guide_file'),
            'description': (
                'Add safety or caution information, helpful notes, and an '
                'optional procedure file.'
            ),
        }),
        ('Display settings', {
            'fields': ('is_active', 'sort_order'),
            'description': (
                'Only active steps are shown. Lower sort numbers determine '
                'their order in the guide.'
            ),
        }),
        ('Record history', {
            'fields': ('created_at', 'updated_at'),
        }),
    )
    inlines = (StepChoiceInline, StepImageInline)


@admin.register(StepChoice)
class StepChoiceAdmin(admin.ModelAdmin):
    list_display = ('label', 'step', 'next_step', 'sort_order')
    search_fields = ('label', 'step__title', 'next_step__title')
    autocomplete_fields = ('step', 'next_step')
    list_select_related = ('step', 'next_step')
    fieldsets = (
        (None, {
            'fields': ('step', 'label', 'next_step', 'sort_order'),
            'description': (
                'Add a button label for the answer. Choose the next step '
                'users should see, or leave it blank to finish this path.'
            ),
        }),
    )


@admin.register(StepImage)
class StepImageAdmin(admin.ModelAdmin):
    list_display = ('caption', 'step', 'alt_text', 'sort_order')
    search_fields = ('caption', 'description', 'alt_text', 'step__title')
    autocomplete_fields = ('step',)
    list_select_related = ('step',)
    fieldsets = (
        (None, {
            'fields': ('step', 'image', 'caption', 'alt_text', 'description', 'sort_order'),
            'description': (
                'Attach a relevant diagram to a step. Add descriptive alt '
                'text so users relying on assistive technology understand the image.'
            ),
        }),
    )


admin.site.site_header = 'BCM-Troubleshooting Web administration'
admin.site.site_title = 'BCM-Troubleshooting Web admin'
admin.site.index_title = 'Manage troubleshooting content'
