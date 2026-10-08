from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models

MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_GUIDE_SIZE = 25 * 1024 * 1024


def validate_image_size(upload):
    """Reject oversized image uploads before storing them."""
    if upload.size > MAX_IMAGE_SIZE:
        raise ValidationError('Images must be 10 MB or smaller.')


def validate_guide_size(upload):
    """Keep administrator-uploaded procedure documents within the size limit."""
    if upload.size > MAX_GUIDE_SIZE:
        raise ValidationError('Guides must be 25 MB or smaller.')


class ProductRange(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to='troubleshooting/products/',
        blank=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=('jpg', 'jpeg', 'png', 'webp'),
            ),
            validate_image_size,
        ],
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('sort_order', 'name')

    def __str__(self):
        return self.name


class Problem(models.Model):
    product_range = models.ForeignKey(
        ProductRange,
        on_delete=models.PROTECT,
        related_name='problems',
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('sort_order', 'name')
        constraints = [
            models.UniqueConstraint(
                fields=('product_range', 'name'),
                name='unique_problem_name_per_product',
            ),
        ]

    def __str__(self):
        return f'{self.product_range}: {self.name}'


class ConfigurationQuestion(models.Model):
    class Phase(models.TextChoices):
        SETUP = 'setup', 'System configuration'
        DIAGNOSIS = 'diagnosis', 'Problem diagnosis'

    # Explicit product links allow a shared question to apply to selected products.
    applies_to_products = models.ManyToManyField(
        ProductRange,
        related_name='configuration_questions',
        blank=True,
    )
    phase = models.CharField(
        max_length=12,
        choices=Phase.choices,
        default=Phase.SETUP,
    )
    problem = models.ForeignKey(
        Problem,
        on_delete=models.CASCADE,
        related_name='diagnostic_questions',
        null=True,
        blank=True,
        help_text='Optional: limit a diagnostic question to one problem.',
    )
    name = models.CharField(max_length=150)
    help_text = models.TextField(blank=True)
    depends_on_option = models.ForeignKey(
        'ConfigurationOption',
        on_delete=models.PROTECT,
        related_name='dependent_questions',
        null=True,
        blank=True,
    )
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('sort_order', 'id')

    def clean(self):
        super().clean()
        if self.phase == self.Phase.SETUP and self.problem_id:
            raise ValidationError({
                'problem': 'System configuration questions cannot belong to a problem.',
            })
        if not self.depends_on_option_id:
            return

        parent_question = self.depends_on_option.question
        if self.pk and parent_question.pk == self.pk:
            raise ValidationError({
                'depends_on_option': 'A question cannot depend on itself.',
            })
        if (
            self.phase == self.Phase.SETUP
            and parent_question.phase != self.Phase.SETUP
        ):
            raise ValidationError({
                'depends_on_option': (
                    'System configuration questions may depend only on '
                    'system configuration questions.'
                ),
            })
        if self.phase == self.Phase.DIAGNOSIS:
            if parent_question.phase == self.Phase.DIAGNOSIS:
                if (
                    self.problem_id
                    and parent_question.problem_id
                    and self.problem_id != parent_question.problem_id
                ):
                    raise ValidationError({
                        'depends_on_option': (
                            'Diagnostic questions for different problems '
                            'cannot depend on each other.'
                        ),
                    })

        # Prevent indirect dependency cycles when an administrator edits a question.
        visited_question_ids = {self.pk} if self.pk else set()
        while parent_question is not None:
            if parent_question.pk in visited_question_ids:
                raise ValidationError({
                    'depends_on_option': 'Question dependencies cannot contain a cycle.',
                })
            visited_question_ids.add(parent_question.pk)
            parent_option = parent_question.depends_on_option
            parent_question = parent_option.question if parent_option else None

    def __str__(self):
        return self.name


class ConfigurationOption(models.Model):
    question = models.ForeignKey(
        ConfigurationQuestion,
        on_delete=models.CASCADE,
        related_name='options',
    )
    label = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('sort_order', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('question', 'label'),
                name='unique_configuration_option_per_question',
            ),
        ]

    def __str__(self):
        return f'{self.question.name}: {self.label}'


class TroubleshootingFlow(models.Model):
    problem = models.ForeignKey(
        Problem,
        on_delete=models.PROTECT,
        related_name='flows',
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    # The nullable start step lets an administrator create a flow before its steps.
    start_step = models.ForeignKey(
        'TroubleshootingStep',
        on_delete=models.PROTECT,
        related_name='starting_flows',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('problem__name', 'name')
        constraints = [
            models.UniqueConstraint(
                fields=('problem', 'name'),
                name='unique_flow_name_per_problem',
            ),
        ]

    def clean(self):
        super().clean()
        # A flow must begin at one of its own steps, never at another flow's step.
        if (
            self.pk
            and self.start_step_id
            and self.start_step.flow_id != self.pk
        ):
            raise ValidationError({
                'start_step': 'The starting step must belong to this flow.',
            })

    def __str__(self):
        return f'{self.problem}: {self.name}'


class TroubleshootingStep(models.Model):
    class StepType(models.TextChoices):
        INSTRUCTION = 'instruction', 'Instruction'
        QUESTION = 'question', 'Question / decision'
        INSPECTION = 'inspection', 'Inspection'
        RESOLUTION = 'resolution', 'Resolution'
        DOWNLOAD = 'download', 'Downloadable procedure'

    flow = models.ForeignKey(
        TroubleshootingFlow,
        on_delete=models.PROTECT,
        related_name='steps',
    )
    title = models.CharField(max_length=180)
    step_type = models.CharField(
        max_length=20,
        choices=StepType.choices,
        default=StepType.INSTRUCTION,
    )
    instructions = models.TextField(blank=True)
    details = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    warning = models.TextField(blank=True)
    guide_file = models.FileField(
        upload_to='troubleshooting/guides/%Y/%m/',
        blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=('pdf', 'doc', 'docx')),
            validate_guide_size,
        ],
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('sort_order', 'id')

    def __str__(self):
        return f'{self.flow}: {self.title}'


class FlowConfigurationRequirement(models.Model):
    # A flow matches only when every listed option was selected by the technician.
    flow = models.ForeignKey(
        TroubleshootingFlow,
        on_delete=models.CASCADE,
        related_name='configuration_requirements',
    )
    option = models.ForeignKey(
        ConfigurationOption,
        on_delete=models.PROTECT,
        related_name='flow_requirements',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('flow', 'option'),
                name='unique_configuration_requirement_per_flow',
            ),
        ]

    def clean(self):
        super().clean()
        if not self.flow_id or not self.option_id:
            return

        flow_product_id = self.flow.problem.product_range_id
        question = self.option.question
        if not question.applies_to_products.filter(pk=flow_product_id).exists():
            raise ValidationError({
                'option': (
                    'The configuration question must apply to the flow product.'
                ),
            })
        if (
            question.phase == ConfigurationQuestion.Phase.DIAGNOSIS
            and question.problem_id
            and question.problem_id != self.flow.problem_id
        ):
            raise ValidationError({
                'option': (
                    'A diagnostic requirement must belong to the flow problem.'
                ),
            })
        if self.flow.configuration_requirements.exclude(
            pk=self.pk,
        ).filter(
            option__question_id=self.option.question_id,
        ).exists():
            raise ValidationError({
                'option': 'A flow can require only one option per question.',
            })

    def __str__(self):
        return f'{self.flow}: {self.option}'


class StepChoice(models.Model):
    # Each answer is a database edge from one step to another.
    step = models.ForeignKey(
        TroubleshootingStep,
        on_delete=models.CASCADE,
        related_name='choices',
    )
    label = models.CharField(max_length=120)
    # A missing target intentionally marks this answer as an end of the flow.
    next_step = models.ForeignKey(
        TroubleshootingStep,
        on_delete=models.PROTECT,
        related_name='incoming_choices',
        null=True,
        blank=True,
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('sort_order', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('step', 'label'),
                name='unique_choice_label_per_step',
            ),
        ]

    def clean(self):
        super().clean()
        # Branch targets in another flow would create an invalid cross-flow jump.
        if (
            self.step_id
            and self.next_step_id
            and self.step.flow_id != self.next_step.flow_id
        ):
            raise ValidationError({
                'next_step': 'The next step must belong to the same flow.',
            })

    def __str__(self):
        return f'{self.step}: {self.label}'


class StepImage(models.Model):
    step = models.ForeignKey(
        TroubleshootingStep,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(
        upload_to='troubleshooting/steps/%Y/%m/',
        validators=[
            FileExtensionValidator(
                allowed_extensions=('jpg', 'jpeg', 'png', 'webp'),
            ),
            validate_image_size,
        ],
    )
    caption = models.CharField(max_length=180, blank=True)
    description = models.TextField(blank=True)
    alt_text = models.CharField(max_length=180)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('sort_order', 'id')

    def __str__(self):
        return self.caption or f'Image for {self.step}'
