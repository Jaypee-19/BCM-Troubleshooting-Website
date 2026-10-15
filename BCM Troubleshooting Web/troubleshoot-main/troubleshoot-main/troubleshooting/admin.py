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


FIELD_GUIDANCE = {
    ProductRange: {
        'name': 'Enter the product-family name technicians will recognize, such as VSAT or Starlink.',
        'description': 'Summarize what this product range covers and the types of equipment or issues its guides support. Avoid instructions here; put troubleshooting instructions in the guide steps.',
        'image': 'Optionally upload a representative product image. Use a clear JPG, PNG, or WebP image, up to 10 MB.',
        'is_active': 'Active products are visible to technicians. Turn this off to hide the product without deleting its guides.',
        'sort_order': 'Controls the product’s position in lists. Use 0 for the first item; use larger numbers for later items.',
    },
    Problem: {
        'product_range': 'Select the product range where technicians should find this issue.',
        'name': 'Enter a short, recognizable symptom or issue, such as “No internet connection.”',
        'description': 'Describe what the technician may observe, when it happens, or how to recognize this issue. Keep it user-facing; add checks and repair instructions to the guide steps.',
        'is_active': 'Active problems are shown to technicians when a matching guide is published.',
        'sort_order': 'Controls the order of issues within this product range. Use 0 for the first item.',
    },
    ConfigurationQuestion: {
        'name': 'Write the question technicians should answer, for example “Which antenna model is installed?”',
        'help_text': 'Add a brief clarification that appears below the question. Explain where to find the answer or what each choice means; do not repeat the question.',
        'phase': 'Choose System configuration for equipment details collected before issue selection. Choose Problem diagnosis for questions asked after an issue is selected.',
        'problem': 'Optionally restrict a diagnosis question to one problem. Leave blank to use it for applicable problems.',
        'applies_to_products': 'Select each product range where technicians should see this question.',
        'depends_on_option': 'Optional: show this question only when a technician selects a particular answer to an earlier question.',
        'is_required': 'Require an answer before the technician can continue. Leave unchecked when the question is optional.',
        'is_active': 'Only active questions are shown to technicians. Turn off to hide a question without deleting it.',
        'sort_order': 'Controls the order in which questions appear. Use increasing values to set the order.',
    },
    ConfigurationOption: {
        'question': 'Choose the question this answer belongs to. Add several distinct options when the technician should choose between answers.',
        'label': 'Enter the concise answer technicians will select, for example “Intellian” or “Sailor.”',
        'is_active': 'Only active answer options can be selected by technicians.',
        'sort_order': 'Controls the order of answers beneath the question. Use increasing values to set the order.',
    },
    TroubleshootingFlow: {
        'problem': 'Select the issue this guide resolves. The issue must belong to the product range where the guide should appear.',
        'name': 'Enter a short guide name that helps administrators distinguish this path.',
        'description': 'Summarize when this guide applies or what it helps diagnose. Put user-facing checks and repair instructions in the steps below.',
        'is_active': 'Only active guides with an active starting step are available to technicians.',
        'start_step': 'After saving the guide and adding its steps, reopen it and choose the first step technicians should see.',
    },
    FlowConfigurationRequirement: {
        'option': 'Optionally require a specific equipment answer for this guide to appear. Add at most one answer per question; leave this section empty if the guide is not equipment-specific.',
    },
    TroubleshootingStep: {
        'flow': 'Select the guide this step belongs to. Choices can only continue to another step in the same guide.',
        'title': 'Write a short action or question technicians can understand at a glance.',
        'step_type': 'Choose the type that best describes this step, such as an instruction, decision, inspection, or resolution.',
        'instructions': 'Write the action the technician should perform. Use clear, numbered instructions when there are multiple actions.',
        'details': 'Add supporting information that helps interpret the check or perform the action. Keep the main action in Instructions.',
        'notes': 'Add helpful context or non-critical tips. Use Warning for safety risks or actions that could damage equipment.',
        'warning': 'State any safety risk, required precaution, or action that could cause harm or equipment damage. Leave blank if none applies.',
        'guide_file': 'Optionally attach a supporting procedure document. PDF files up to 25 MB are supported.',
        'is_active': 'Only active steps can be visited by technicians.',
        'sort_order': 'Controls how steps are ordered in the administration list. Actual user routing is determined by the answer choices.',
    },
    StepChoice: {
        'step': 'Select the decision step where this answer button should appear.',
        'label': 'Write the short answer or finding technicians should select, for example “The indicator is flashing.”',
        'next_step': 'Choose the next step for this answer. Leave blank when selecting this answer should finish the troubleshooting path.',
        'sort_order': 'Controls the order of answer buttons shown to technicians. Use increasing values to set the order.',
    },
    StepImage: {
        'step': 'Select the step where this image or diagram should appear.',
        'image': 'Upload a clear JPG, PNG, or WebP image that supports this step. Images must be 10 MB or smaller.',
        'caption': 'Add a short title displayed with the image, such as “ACU status indicators.”',
        'alt_text': 'Describe the important visual information for screen-reader users. Do not use only “image” or repeat the caption.',
        'description': 'Optionally explain labels, connections, or details in the image that technicians need to understand.',
        'sort_order': 'Controls the order when a step has multiple images. Use increasing values to set the order.',
    },
}


class GuidedAdminMixin:
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        for field_name, guidance in FIELD_GUIDANCE.get(self.model, {}).items():
            field = form.base_fields.get(field_name)
            if field and guidance not in field.help_text:
                field.help_text = ' '.join(
                    part for part in (guidance, field.help_text) if part
                )
        return form

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        guidance = FIELD_GUIDANCE.get(self.model, {}).get(db_field.name)
        if formfield and guidance and guidance not in formfield.help_text:
            existing_help = formfield.help_text
            formfield.help_text = (
                f'{guidance} {existing_help}'.strip()
                if existing_help
                else guidance
            )
        return formfield


class ProblemInline(GuidedAdminMixin, admin.TabularInline):
    model = Problem
    extra = 0
    verbose_name = 'problem'
    verbose_name_plural = 'Problems users can select for this product'
    fields = ('name', 'is_active', 'sort_order')
    show_change_link = True


class ConfigurationOptionInline(GuidedAdminMixin, admin.TabularInline):
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


class FlowConfigurationRequirementInline(GuidedAdminMixin, admin.TabularInline):
    model = FlowConfigurationRequirement
    formset = FlowConfigurationRequirementFormSet
    extra = 0
    verbose_name = 'equipment requirement'
    verbose_name_plural = 'Equipment requirements (optional; limit this guide to selected answers)'
    fields = ('option',)
    autocomplete_fields = ('option',)


class FlowInline(GuidedAdminMixin, admin.TabularInline):
    model = TroubleshootingFlow
    extra = 0
    verbose_name = 'troubleshooting guide'
    verbose_name_plural = 'Troubleshooting guides for this problem'
    fields = ('name', 'description', 'is_active')
    show_change_link = True


class TroubleshootingStepInline(GuidedAdminMixin, admin.TabularInline):
    model = TroubleshootingStep
    extra = 0
    verbose_name = 'guide step'
    verbose_name_plural = 'Guide steps (add steps here, then set the starting step after saving)'
    fields = ('title', 'step_type', 'is_active', 'sort_order')
    show_change_link = True


class StepChoiceInline(GuidedAdminMixin, admin.TabularInline):
    model = StepChoice
    # A choice has both a source step and a destination step; this is its owner.
    fk_name = 'step'
    extra = 0
    verbose_name = 'answer choice'
    verbose_name_plural = 'Answer choices (leave the next step blank to end this path)'
    fields = ('label', 'next_step', 'sort_order')
    autocomplete_fields = ('next_step',)


class StepImageInline(GuidedAdminMixin, admin.TabularInline):
    model = StepImage
    extra = 0
    verbose_name = 'step image'
    verbose_name_plural = 'Images and diagrams for this step'
    fields = ('image', 'caption', 'alt_text', 'description', 'sort_order')


@admin.register(ProductRange)
class ProductRangeAdmin(GuidedAdminMixin, admin.ModelAdmin):
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
class ConfigurationQuestionAdmin(GuidedAdminMixin, admin.ModelAdmin):
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
class ConfigurationOptionAdmin(GuidedAdminMixin, admin.ModelAdmin):
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
class ProblemAdmin(GuidedAdminMixin, admin.ModelAdmin):
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
class TroubleshootingFlowAdmin(GuidedAdminMixin, admin.ModelAdmin):
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
class TroubleshootingStepAdmin(GuidedAdminMixin, admin.ModelAdmin):
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
class StepChoiceAdmin(GuidedAdminMixin, admin.ModelAdmin):
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
class StepImageAdmin(GuidedAdminMixin, admin.ModelAdmin):
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
