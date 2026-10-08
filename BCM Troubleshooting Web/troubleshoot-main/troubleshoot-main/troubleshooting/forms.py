from django import forms
from django.db.models import Q

from .models import ConfigurationQuestion


class ConfigurationQuestionAdminForm(forms.ModelForm):
    class Meta:
        model = ConfigurationQuestion
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        phase = cleaned_data.get('phase')
        problem = cleaned_data.get('problem')
        products = cleaned_data.get('applies_to_products')
        dependency = cleaned_data.get('depends_on_option')

        if phase == ConfigurationQuestion.Phase.SETUP and problem:
            self.add_error(
                'problem',
                'System configuration questions cannot belong to a problem.',
            )
        if (
            phase == ConfigurationQuestion.Phase.DIAGNOSIS
            and problem
            and products is not None
            and not products.filter(pk=problem.product_range_id).exists()
        ):
            self.add_error(
                'applies_to_products',
                'Include the selected problem’s product in this question’s scope.',
            )

        if dependency is not None and products is not None:
            parent_question = dependency.question
            if (
                phase == ConfigurationQuestion.Phase.DIAGNOSIS
                and parent_question.phase == ConfigurationQuestion.Phase.DIAGNOSIS
                and parent_question.problem_id
                and problem
                and parent_question.problem_id != problem.pk
            ):
                self.add_error(
                    'depends_on_option',
                    'Diagnostic questions for different problems cannot depend on each other.',
                )
            elif not parent_question.applies_to_products.filter(
                pk__in=products.values('pk'),
            ).exists():
                # A child question may depend only on a question visible for
                # at least one of the same products.
                self.add_error(
                    'depends_on_option',
                    'The parent question must apply to at least one selected product.',
                )
        return cleaned_data


class QuestionnaireForm(forms.Form):
    """Build setup or problem-diagnosis fields from admin-managed questions."""

    def __init__(
        self,
        product,
        phase,
        *args,
        problem=None,
        **kwargs,
    ):
        initial = kwargs.get('initial') or {}
        super().__init__(*args, **kwargs)
        question_filter = Q(
            applies_to_products=product,
            phase=phase,
        )
        if phase == ConfigurationQuestion.Phase.DIAGNOSIS:
            question_filter &= Q(problem__isnull=True) | Q(problem=problem)

        all_questions = list(
            ConfigurationQuestion.objects.filter(
                question_filter,
                is_active=True,
            ).select_related(
                'depends_on_option__question',
            ).prefetch_related(
                'options',
            ).distinct(),
        )
        questions_by_id = {
            question.pk: question for question in all_questions
        }
        self.questions = []
        for question in all_questions:
            if not self._is_visible(question, questions_by_id, initial):
                continue

            self.questions.append(question)
            field_name = self.field_name(question.pk)
            self.fields[field_name] = forms.ModelChoiceField(
                queryset=question.options.filter(is_active=True),
                label=question.name,
                help_text=question.help_text,
                required=question.is_required,
                empty_label='Select an option',
            )
            if not self.is_bound and field_name in initial:
                self.fields[field_name].initial = initial[field_name]

    @staticmethod
    def field_name(question_id):
        return f'question_{question_id}'

    def _selected_value(self, question_id, initial):
        field_name = self.field_name(question_id)
        if self.is_bound and field_name in self.data:
            return self.data[field_name]
        return initial.get(field_name, '')

    def _is_visible(self, question, questions_by_id, initial, visited=None):
        dependency = question.depends_on_option
        if dependency is None:
            return True

        visited = visited or set()
        if question.pk in visited:
            return False
        visited.add(question.pk)
        parent_question = questions_by_id.get(dependency.question_id)
        if parent_question is not None and not self._is_visible(
            parent_question,
            questions_by_id,
            initial,
            visited,
        ):
            return False

        selected_parent_option = self._selected_value(
            dependency.question_id,
            initial,
        )
        return str(selected_parent_option) == str(dependency.pk)
