import io
import tempfile
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.test.utils import override_settings
from django.urls import reverse
from PIL import Image

from .forms import ConfigurationQuestionAdminForm
from .models import (
    ConfigurationOption,
    ConfigurationQuestion,
    FlowConfigurationRequirement,
    MAX_GUIDE_SIZE,
    MAX_IMAGE_SIZE,
    Problem,
    ProductRange,
    StepChoice,
    StepImage,
    TroubleshootingFlow,
    TroubleshootingStep,
    validate_guide_size,
    validate_image_size,
)


class TroubleshootingRelationshipTests(TestCase):
    def setUp(self):
        self.product, _ = ProductRange.objects.get_or_create(name='VSAT')
        self.problem = Problem.objects.create(
            product_range=self.product,
            name='Communication problem',
        )
        self.flow = TroubleshootingFlow.objects.create(
            problem=self.problem,
            name='ACU communication check',
        )
        self.start_step = TroubleshootingStep.objects.create(
            flow=self.flow,
            title='Check ACU status',
            step_type=TroubleshootingStep.StepType.QUESTION,
        )
        self.next_step = TroubleshootingStep.objects.create(
            flow=self.flow,
            title='Check the network connection',
            step_type=TroubleshootingStep.StepType.INSPECTION,
        )
        self.flow.start_step = self.start_step
        self.flow.full_clean()
        self.flow.save()

    def test_choices_store_the_next_step_in_the_database(self):
        choice = StepChoice.objects.create(
            step=self.start_step,
            label='Communication OK',
            next_step=self.next_step,
        )

        self.assertEqual(self.start_step.choices.get().next_step, self.next_step)
        self.assertEqual(choice.step.flow, self.flow)

    def test_choice_without_a_target_can_end_a_flow(self):
        choice = StepChoice.objects.create(
            step=self.start_step,
            label='Issue resolved',
        )

        self.assertIsNone(choice.next_step)

    def test_choice_cannot_branch_into_a_different_flow(self):
        other_problem = Problem.objects.create(
            product_range=self.product,
            name='Modem problem',
        )
        other_flow = TroubleshootingFlow.objects.create(
            problem=other_problem,
            name='Modem check',
        )
        other_step = TroubleshootingStep.objects.create(
            flow=other_flow,
            title='Inspect modem',
        )
        choice = StepChoice(
            step=self.start_step,
            label='Continue',
            next_step=other_step,
        )

        with self.assertRaises(ValidationError):
            choice.full_clean()

    def test_flow_cannot_start_at_a_step_from_another_flow(self):
        other_problem = Problem.objects.create(
            product_range=self.product,
            name='Modem problem',
        )
        other_flow = TroubleshootingFlow.objects.create(
            problem=other_problem,
            name='Modem check',
        )
        other_step = TroubleshootingStep.objects.create(
            flow=other_flow,
            title='Inspect modem',
        )
        self.flow.start_step = other_step

        with self.assertRaises(ValidationError):
            self.flow.full_clean()

    def test_flow_cannot_require_two_answers_to_the_same_question(self):
        question = ConfigurationQuestion.objects.create(
            name='ACU type',
        )
        question.applies_to_products.add(self.product)
        first_option = ConfigurationOption.objects.create(
            question=question,
            label='Intellian',
        )
        second_option = ConfigurationOption.objects.create(
            question=question,
            label='Sailor',
        )
        FlowConfigurationRequirement.objects.create(
            flow=self.flow,
            option=first_option,
        )
        conflicting_requirement = FlowConfigurationRequirement(
            flow=self.flow,
            option=second_option,
        )

        with self.assertRaises(ValidationError):
            conflicting_requirement.full_clean()


class ConfigurationWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='configuration-technician',
            password='test-password',
        )
        self.client.force_login(self.user)
        self.product, _ = ProductRange.objects.get_or_create(name='VSAT')
        self.problem = Problem.objects.create(
            product_range=self.product,
            name='Communication problem',
        )
        self.acu_question = ConfigurationQuestion.objects.create(
            name='ACU type',
            sort_order=10,
        )
        self.acu_question.applies_to_products.add(self.product)
        self.intellian_option = ConfigurationOption.objects.create(
            question=self.acu_question,
            label='Intellian',
        )
        self.sailor_option = ConfigurationOption.objects.create(
            question=self.acu_question,
            label='Sailor',
        )
        self.model_question = ConfigurationQuestion.objects.create(
            name='ACU model',
            depends_on_option=self.intellian_option,
            sort_order=20,
        )
        self.model_question.applies_to_products.add(self.product)
        self.model_option = ConfigurationOption.objects.create(
            question=self.model_question,
            label='Intellian V85',
        )
        self.hydrabox_question = ConfigurationQuestion.objects.create(
            name='Hydrabox version',
            sort_order=30,
        )
        self.hydrabox_question.applies_to_products.add(self.product)
        self.hydrabox_option = ConfigurationOption.objects.create(
            question=self.hydrabox_question,
            label='Hydrabox V2',
        )
        self.intellian_flow = self._create_flow(
            'Intellian communication check',
            (self.intellian_option, self.model_option, self.hydrabox_option),
        )
        self.sailor_flow = self._create_flow(
            'Sailor communication check',
            (self.sailor_option, self.hydrabox_option),
        )

    def _create_flow(self, name, options):
        flow = TroubleshootingFlow.objects.create(
            problem=self.problem,
            name=name,
        )
        step = TroubleshootingStep.objects.create(
            flow=flow,
            title=f'Start {name}',
            step_type=TroubleshootingStep.StepType.QUESTION,
        )
        flow.start_step = step
        flow.save(update_fields=('start_step',))
        for option in options:
            FlowConfigurationRequirement.objects.create(
                flow=flow,
                option=option,
            )
        return flow

    def test_configuration_questions_are_admin_defined_and_progressive(self):
        response = self.client.get(
            reverse(
                'troubleshooting:product_detail',
                args=(self.product.pk,),
            ),
        )

        self.assertContains(response, 'ACU type')
        self.assertContains(response, 'Hydrabox version')
        self.assertNotContains(response, 'ACU model')

        response = self.client.post(
            reverse(
                'troubleshooting:product_detail',
                args=(self.product.pk,),
            ),
            {
                f'question_{self.acu_question.pk}': self.intellian_option.pk,
                f'question_{self.hydrabox_question.pk}': self.hydrabox_option.pk,
            },
        )

        self.assertContains(response, 'ACU model')
        self.assertContains(response, 'This field is required')

    def test_only_flows_matching_every_selected_configuration_option_are_shown(self):
        response = self.client.post(
            reverse(
                'troubleshooting:product_detail',
                args=(self.product.pk,),
            ),
            {
                f'question_{self.acu_question.pk}': self.intellian_option.pk,
                f'question_{self.model_question.pk}': self.model_option.pk,
                f'question_{self.hydrabox_question.pk}': self.hydrabox_option.pk,
            },
            follow=True,
        )

        self.assertContains(response, 'Continue with this problem')
        problem_url = reverse(
            'troubleshooting:problem_detail',
            args=(self.product.pk, self.problem.pk),
        )
        response = self.client.get(problem_url)

        self.assertContains(response, self.intellian_flow.name)
        self.assertNotContains(response, self.sailor_flow.name)
        self.assertContains(response, 'Update answers')

    def test_diagnostic_answers_filter_flows_after_problem_selection(self):
        device_question = ConfigurationQuestion.objects.create(
            phase=ConfigurationQuestion.Phase.DIAGNOSIS,
            problem=self.problem,
            name='Device status',
        )
        device_question.applies_to_products.add(self.product)
        red_option = ConfigurationOption.objects.create(
            question=device_question,
            label='ACU LED red',
        )
        FlowConfigurationRequirement.objects.create(
            flow=self.intellian_flow,
            option=red_option,
        )
        self._submit_configuration()
        problem_url = reverse(
            'troubleshooting:problem_detail',
            args=(self.product.pk, self.problem.pk),
        )

        response = self.client.get(problem_url)
        self.assertContains(response, 'Device status')
        self.assertNotContains(response, self.intellian_flow.name)

        response = self.client.post(
            problem_url,
            {f'question_{device_question.pk}': red_option.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.client.session['troubleshooting_diagnoses'][str(self.problem.pk)],
            {str(device_question.pk): red_option.pk},
        )
        response = self.client.get(problem_url)

        self.assertContains(response, self.intellian_flow.name)
        self.assertNotContains(response, self.sailor_flow.name)

    def test_changing_setup_invalidates_diagnostic_answers_and_flow_progress(self):
        device_question = ConfigurationQuestion.objects.create(
            phase=ConfigurationQuestion.Phase.DIAGNOSIS,
            problem=self.problem,
            name='Device status',
        )
        device_question.applies_to_products.add(self.product)
        red_option = ConfigurationOption.objects.create(
            question=device_question,
            label='ACU LED red',
        )
        FlowConfigurationRequirement.objects.create(
            flow=self.intellian_flow,
            option=red_option,
        )
        self._submit_configuration()
        problem_url = reverse(
            'troubleshooting:problem_detail',
            args=(self.product.pk, self.problem.pk),
        )
        self.client.post(
            problem_url,
            {f'question_{device_question.pk}': red_option.pk},
        )
        start_response = self.client.post(
            reverse(
                'troubleshooting:flow_start',
                args=(self.intellian_flow.pk,),
            ),
        )
        self.assertEqual(start_response.status_code, 302)
        step_url = reverse(
            'troubleshooting:step_detail',
            args=(self.intellian_flow.pk, self.intellian_flow.start_step_id),
        )
        self.assertEqual(self.client.get(step_url).status_code, 200)

        self.client.post(
            reverse(
                'troubleshooting:product_detail',
                args=(self.product.pk,),
            ),
            {
                f'question_{self.acu_question.pk}': self.sailor_option.pk,
                f'question_{self.hydrabox_question.pk}': self.hydrabox_option.pk,
            },
        )

        self.assertEqual(self.client.get(step_url).status_code, 404)

    def _submit_configuration(self):
        response = self.client.post(
            reverse(
                'troubleshooting:product_detail',
                args=(self.product.pk,),
            ),
            {
                f'question_{self.acu_question.pk}': self.intellian_option.pk,
                f'question_{self.model_question.pk}': self.model_option.pk,
                f'question_{self.hydrabox_question.pk}': self.hydrabox_option.pk,
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_configuration_specific_flow_cannot_start_before_configuration(self):
        response = self.client.post(
            reverse(
                'troubleshooting:flow_start',
                args=(self.intellian_flow.pk,),
            ),
        )

        self.assertRedirects(
            response,
            reverse(
                'troubleshooting:product_detail',
                args=(self.product.pk,),
            ),
        )

    def test_configuration_cannot_match_a_flow_for_another_product(self):
        other_product, _ = ProductRange.objects.get_or_create(name='Starlink')
        other_problem = Problem.objects.create(
            product_range=other_product,
            name='Communication problem',
        )
        other_flow = TroubleshootingFlow.objects.create(
            problem=other_problem,
            name='Starlink communication check',
        )
        requirement = FlowConfigurationRequirement(
            flow=other_flow,
            option=self.intellian_option,
        )

        with self.assertRaises(ValidationError):
            requirement.full_clean()


class TroubleshootingUploadValidationTests(TestCase):
    def test_file_size_validators_accept_the_limit_and_reject_oversized_files(self):
        for validator, size_limit in (
            (validate_image_size, MAX_IMAGE_SIZE),
            (validate_guide_size, MAX_GUIDE_SIZE),
        ):
            with self.subTest(size_limit=size_limit):
                validator(SimpleNamespace(size=size_limit))
                with self.assertRaises(ValidationError):
                    validator(SimpleNamespace(size=size_limit + 1))

    def test_guide_rejects_an_unsupported_file_extension(self):
        product, _ = ProductRange.objects.get_or_create(name='VSAT')
        problem = Problem.objects.create(
            product_range=product,
            name='Communication problem',
        )
        flow = TroubleshootingFlow.objects.create(
            problem=problem,
            name='ACU communication check',
        )
        step = TroubleshootingStep(
            flow=flow,
            title='Download the procedure',
            guide_file=SimpleUploadedFile('procedure.exe', b'not a guide'),
        )

        with self.assertRaises(ValidationError) as error:
            step.full_clean()

        self.assertIn('guide_file', error.exception.error_dict)

    def test_image_rejects_an_unsupported_file_extension(self):
        product, _ = ProductRange.objects.get_or_create(name='VSAT')
        problem = Problem.objects.create(
            product_range=product,
            name='Communication problem',
        )
        flow = TroubleshootingFlow.objects.create(
            problem=problem,
            name='ACU communication check',
        )
        step = TroubleshootingStep.objects.create(
            flow=flow,
            title='Inspect the ACU',
        )
        image_bytes = io.BytesIO()
        Image.new('RGB', (1, 1), color='white').save(image_bytes, format='PNG')
        image = StepImage(
            step=step,
            image=SimpleUploadedFile('diagram.gif', image_bytes.getvalue()),
            alt_text='ACU connection diagram',
        )

        with self.assertRaises(ValidationError) as error:
            image.full_clean()

        self.assertIn('image', error.exception.error_dict)


class TroubleshootingAdminAccessTests(TestCase):
    def test_staff_user_can_open_product_admin(self):
        admin_user = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='test-password',
        )
        self.client.force_login(admin_user)

        response = self.client.get('/admin/troubleshooting/productrange/')

        self.assertEqual(response.status_code, 200)

    def test_staff_user_can_manage_configuration_questions(self):
        admin_user = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='test-password',
        )
        self.client.force_login(admin_user)

        question_response = self.client.get(
            '/admin/troubleshooting/configurationquestion/add/',
        )
        option_response = self.client.get(
            '/admin/troubleshooting/configurationoption/',
        )

        self.assertEqual(question_response.status_code, 200)
        self.assertEqual(option_response.status_code, 200)

    def test_admin_question_form_saves_product_scope(self):
        product = ProductRange.objects.get(name='VSAT')
        question_form = ConfigurationQuestionAdminForm(data={
            'name': 'ACU type',
            'help_text': '',
            'phase': ConfigurationQuestion.Phase.SETUP,
            'problem': '',
            'applies_to_products': [str(product.pk)],
            'depends_on_option': '',
            'is_required': 'on',
            'is_active': 'on',
            'sort_order': '0',
        })

        self.assertTrue(question_form.is_valid(), question_form.errors)
        question = question_form.save()

        self.assertEqual(
            list(question.applies_to_products.values_list('pk', flat=True)),
            [product.pk],
        )

    def test_regular_user_cannot_open_product_admin(self):
        user = get_user_model().objects.create_user(
            username='technician',
            password='test-password',
        )
        self.client.force_login(user)

        response = self.client.get('/admin/troubleshooting/productrange/')

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)


class TroubleshootingFlowViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='technician',
            password='test-password',
        )
        self.product, _ = ProductRange.objects.get_or_create(name='VSAT')
        self.problem = Problem.objects.create(
            product_range=self.product,
            name='Communication problem',
        )
        self.flow = TroubleshootingFlow.objects.create(
            problem=self.problem,
            name='ACU communication check',
        )
        self.start_step = TroubleshootingStep.objects.create(
            flow=self.flow,
            title='Check ACU status',
            step_type=TroubleshootingStep.StepType.QUESTION,
        )
        self.resolution = TroubleshootingStep.objects.create(
            flow=self.flow,
            title='Replace the network cable',
            step_type=TroubleshootingStep.StepType.RESOLUTION,
            instructions='Replace the cable and restart the ACU.',
        )
        self.follow_up = TroubleshootingStep.objects.create(
            flow=self.flow,
            title='Inspect the modem',
            step_type=TroubleshootingStep.StepType.INSPECTION,
        )
        self.flow.start_step = self.start_step
        self.flow.full_clean()
        self.flow.save()
        self.resolved_choice = StepChoice.objects.create(
            step=self.start_step,
            label='Issue resolved',
        )
        self.yes_choice = StepChoice.objects.create(
            step=self.start_step,
            label='Communication error',
            next_step=self.resolution,
        )
        self.no_choice = StepChoice.objects.create(
            step=self.start_step,
            label='No communication error',
            next_step=self.follow_up,
        )
        self.client.force_login(self.user)

    def test_guide_pages_require_sign_in(self):
        self.client.logout()

        response = self.client.get(reverse('troubleshooting:product_list'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_login_page_authenticates_a_technician(self):
        self.client.logout()

        response = self.client.post(
            reverse('troubleshooting:login'),
            {'username': 'technician', 'password': 'test-password'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a product range')

    def test_search_finds_step_instructions_and_links_to_the_flow(self):
        self.start_step.instructions = 'The ACU reports a handshake fault.'
        self.start_step.save(update_fields=('instructions',))

        response = self.client.get(
            reverse('troubleshooting:search'),
            {'q': 'handshake fault'},
        )

        self.assertContains(response, self.flow.name)
        self.assertContains(response, 'Start this flow')

    def test_search_excludes_inactive_steps(self):
        self.follow_up.instructions = 'inactive diagnostic phrase'
        self.follow_up.is_active = False
        self.follow_up.save(update_fields=('instructions', 'is_active'))

        response = self.client.get(
            reverse('troubleshooting:search'),
            {'q': 'inactive diagnostic phrase'},
        )

        self.assertContains(response, 'No matching active flows')
        self.assertNotContains(response, self.flow.name)

    def test_search_rejects_queries_longer_than_the_limit(self):
        response = self.client.get(
            reverse('troubleshooting:search'),
            {'q': 'x' * 151},
        )

        self.assertContains(response, '150 characters or fewer')

    def test_empty_search_shows_prompt_instead_of_results(self):
        response = self.client.get(reverse('troubleshooting:search'))

        self.assertContains(response, 'Enter one or more terms')

    def test_product_selection_and_start_step_are_data_driven(self):
        response = self.client.get(reverse('troubleshooting:product_list'))

        self.assertContains(response, 'VSAT')
        self.assertContains(response, 'Select a product range')

    def test_placeholder_products_are_visible_but_not_selectable_without_guides(self):
        response = self.client.get(reverse('troubleshooting:product_list'))

        for product_name in ('VSAT', 'Starlink', 'OneWeb', 'Mobile'):
            with self.subTest(product=product_name):
                self.assertContains(response, product_name)
        self.assertContains(response, 'Coming soon')
        starlink = ProductRange.objects.get(name='Starlink')
        unavailable_response = self.client.get(
            reverse(
                'troubleshooting:product_detail',
                args=(starlink.pk,),
            ),
        )
        self.assertContains(
            unavailable_response,
            'This troubleshooting guide is not published yet',
        )

        response = self.client.post(
            reverse('troubleshooting:flow_start', args=(self.flow.pk,)),
        )

        self.assertRedirects(
            response,
            reverse(
                'troubleshooting:step_detail',
                args=(self.flow.pk, self.start_step.pk),
            ),
        )

    def test_answer_routes_to_its_database_target(self):
        self.client.post(
            reverse('troubleshooting:flow_start', args=(self.flow.pk,)),
        )

        response = self.client.post(
            reverse(
                'troubleshooting:choose_step',
                args=(self.flow.pk, self.start_step.pk, self.yes_choice.pk),
            ),
        )

        expected_url = reverse(
            'troubleshooting:step_detail',
            args=(self.flow.pk, self.resolution.pk),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, expected_url)
        step_response = self.client.get(response.url)
        self.assertContains(step_response, 'Replace the network cable')

    def test_branch_to_a_different_flow_is_rejected_at_runtime(self):
        other_problem = Problem.objects.create(
            product_range=self.product,
            name='Modem problem',
        )
        other_flow = TroubleshootingFlow.objects.create(
            problem=other_problem,
            name='Modem check',
        )
        other_step = TroubleshootingStep.objects.create(
            flow=other_flow,
            title='Inspect modem',
        )
        # Simulate an invalid legacy/imported row that bypassed form validation.
        invalid_choice = StepChoice.objects.create(
            step=self.start_step,
            label='Invalid cross-flow branch',
            next_step=other_step,
        )
        self.client.post(
            reverse('troubleshooting:flow_start', args=(self.flow.pk,)),
        )

        response = self.client.post(
            reverse(
                'troubleshooting:choose_step',
                args=(self.flow.pk, self.start_step.pk, invalid_choice.pk),
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_branch_to_inactive_step_is_rejected(self):
        self.resolution.is_active = False
        self.resolution.save(update_fields=('is_active',))
        self.client.post(
            reverse('troubleshooting:flow_start', args=(self.flow.pk,)),
        )

        response = self.client.post(
            reverse(
                'troubleshooting:choose_step',
                args=(self.flow.pk, self.start_step.pk, self.yes_choice.pk),
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_starting_flow_without_a_start_step_is_rejected(self):
        other_problem = Problem.objects.create(
            product_range=self.product,
            name='Modem problem',
        )
        incomplete_flow = TroubleshootingFlow.objects.create(
            problem=other_problem,
            name='Incomplete flow',
        )

        response = self.client.post(
            reverse(
                'troubleshooting:flow_start',
                args=(incomplete_flow.pk,),
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_flow_start_requires_csrf_protection(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        response = csrf_client.post(
            reverse('troubleshooting:flow_start', args=(self.flow.pk,)),
        )

        self.assertEqual(response.status_code, 403)

    def test_choosing_a_different_answer_after_backtracking_discards_old_branch(self):
        self.client.post(
            reverse('troubleshooting:flow_start', args=(self.flow.pk,)),
        )
        self.client.post(
            reverse(
                'troubleshooting:choose_step',
                args=(self.flow.pk, self.start_step.pk, self.yes_choice.pk),
            ),
        )
        self.client.get(
            reverse(
                'troubleshooting:step_detail',
                args=(self.flow.pk, self.start_step.pk),
            ),
        )

        response = self.client.post(
            reverse(
                'troubleshooting:choose_step',
                args=(self.flow.pk, self.start_step.pk, self.no_choice.pk),
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse(
                'troubleshooting:step_detail',
                args=(self.flow.pk, self.follow_up.pk),
            ),
        )
        abandoned_branch = self.client.get(
            reverse(
                'troubleshooting:step_detail',
                args=(self.flow.pk, self.resolution.pk),
            ),
        )
        self.assertEqual(abandoned_branch.status_code, 404)

    def test_unvisited_branch_cannot_be_opened_directly(self):
        response = self.client.get(
            reverse(
                'troubleshooting:step_detail',
                args=(self.flow.pk, self.follow_up.pk),
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_answer_without_target_shows_flow_endpoint(self):
        self.client.post(
            reverse('troubleshooting:flow_start', args=(self.flow.pk,)),
        )

        response = self.client.post(
            reverse(
                'troubleshooting:choose_step',
                args=(self.flow.pk, self.start_step.pk, self.resolved_choice.pk),
            ),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This path has reached an endpoint')
        self.assertContains(response, 'Issue resolved')

    def test_guide_download_requires_the_step_to_be_reached(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.start_step.guide_file.save(
                    'acu-procedure.pdf',
                    SimpleUploadedFile('acu-procedure.pdf', b'%PDF-1.4 guide'),
                    save=True,
                )
                download_url = reverse(
                    'troubleshooting:download_guide',
                    args=(self.flow.pk, self.start_step.pk),
                )

                denied = self.client.get(download_url)
                self.assertEqual(denied.status_code, 404)

                self.client.post(
                    reverse('troubleshooting:flow_start', args=(self.flow.pk,)),
                )
                response = self.client.get(download_url)

                self.assertEqual(response.status_code, 200)
                self.assertIn('attachment', response['Content-Disposition'])
                self.assertEqual(response['Cache-Control'], 'private, no-store')
                self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
                response.close()

    def test_step_image_requires_an_authenticated_reached_step(self):
        image_bytes = io.BytesIO()
        Image.new('RGB', (1, 1), color='white').save(image_bytes, format='PNG')
        image_upload = SimpleUploadedFile(
            'acu.png',
            image_bytes.getvalue(),
            content_type='image/png',
        )

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                step_image = self.start_step.images.create(
                    image=image_upload,
                    alt_text='ACU status display',
                )
                image_url = reverse(
                    'troubleshooting:serve_media',
                    kwargs={'media_path': step_image.image.name},
                )

                denied = self.client.get(image_url)
                self.assertEqual(denied.status_code, 404)

                self.client.post(
                    reverse('troubleshooting:flow_start', args=(self.flow.pk,)),
                )
                response = self.client.get(image_url)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'image/png')
                response.close()
