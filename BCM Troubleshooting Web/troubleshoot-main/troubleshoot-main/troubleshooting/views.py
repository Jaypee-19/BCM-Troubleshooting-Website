from pathlib import PurePosixPath

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Count, F, Prefetch, Q
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import QuestionnaireForm
from .models import (
    ConfigurationQuestion,
    Problem,
    ProductRange,
    StepChoice,
    StepImage,
    TroubleshootingFlow,
    TroubleshootingStep,
)

FLOW_SESSION_KEY = 'troubleshooting_flows'
CONFIGURATION_SESSION_KEY = 'troubleshooting_configurations'
DIAGNOSIS_SESSION_KEY = 'troubleshooting_diagnoses'
MAX_SEARCH_LENGTH = 150


class TroubleshootingLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True


def home(request):
    return render(request, 'home.html')


@login_required
def product_list(request):
    products = list(ProductRange.objects.filter(is_active=True))
    ready_product_ids = set(
        _active_flow_queryset().filter(
            start_step__isnull=False,
            start_step__is_active=True,
        ).values_list('problem__product_range_id', flat=True).distinct(),
    )
    for product in products:
        product.has_published_flows = product.pk in ready_product_ids
    return render(request, 'troubleshooting/product_list.html', {
        'products': products,
    })


@login_required
def product_detail(request, product_id):
    product = get_object_or_404(ProductRange, pk=product_id, is_active=True)
    if not _published_flows_for_product(product).exists():
        return render(request, 'troubleshooting/product_unavailable.html', {
            'product': product,
        })
    saved_answers = _saved_question_answers(
        request,
        CONFIGURATION_SESSION_KEY,
        str(product.pk),
    )
    saved_data = _answers_as_form_data(saved_answers)

    if request.method == 'POST':
        configuration_form = QuestionnaireForm(
            product,
            ConfigurationQuestion.Phase.SETUP,
            data=request.POST,
        )
        if configuration_form.is_valid():
            _save_questionnaire_answers(
                request,
                configuration_form,
                CONFIGURATION_SESSION_KEY,
                str(product.pk),
            )
            _clear_product_diagnoses(request, product)
            _clear_flow_states(request, product)
            return redirect(
                'troubleshooting:product_detail',
                product_id=product.pk,
            )
    elif request.GET.get('edit') == '1' or not _questionnaire_is_complete(
        product,
        ConfigurationQuestion.Phase.SETUP,
        saved_data,
    ):
        configuration_form = QuestionnaireForm(
            product,
            ConfigurationQuestion.Phase.SETUP,
            initial=saved_data,
        )
    else:
        configuration_form = None

    if request.method == 'POST' or configuration_form is not None:
        return render(request, 'troubleshooting/product_detail.html', {
            'product': product,
            'configuration_form': configuration_form,
        })

    available_flows = _published_flows_for_product(product)
    problems = product.problems.filter(
        is_active=True,
        flows__in=available_flows,
    ).distinct().prefetch_related(
        Prefetch('flows', queryset=available_flows),
    )
    return render(request, 'troubleshooting/product_detail.html', {
        'product': product,
        'problems': problems,
        'configuration_complete': True,
    })


@login_required
def problem_detail(request, product_id, problem_id):
    product = get_object_or_404(ProductRange, pk=product_id, is_active=True)
    problem = get_object_or_404(
        product.problems.filter(
            is_active=True,
            flows__in=_published_flows_for_product(product),
        ).distinct(),
        pk=problem_id,
    )
    setup_answers = _saved_question_answers(
        request,
        CONFIGURATION_SESSION_KEY,
        str(product.pk),
    )
    setup_data = _answers_as_form_data(setup_answers)
    if not _questionnaire_is_complete(
        product,
        ConfigurationQuestion.Phase.SETUP,
        setup_data,
    ):
        return redirect(
            'troubleshooting:product_detail',
            product_id=product.pk,
        )

    saved_diagnosis = _saved_question_answers(
        request,
        DIAGNOSIS_SESSION_KEY,
        str(problem.pk),
    )
    form_data = {
        **setup_data,
        **_answers_as_form_data(saved_diagnosis),
    }

    if request.method == 'POST':
        diagnosis_form = QuestionnaireForm(
            product,
            ConfigurationQuestion.Phase.DIAGNOSIS,
            problem=problem,
            data={**setup_data, **request.POST.dict()},
        )
        if diagnosis_form.is_valid():
            _save_questionnaire_answers(
                request,
                diagnosis_form,
                DIAGNOSIS_SESSION_KEY,
                str(problem.pk),
            )
            _clear_flow_states(request, product, problem)
            return redirect(
                'troubleshooting:problem_detail',
                product_id=product.pk,
                problem_id=problem.pk,
            )
    elif request.GET.get('edit') == '1' or not _questionnaire_is_complete(
        product,
        ConfigurationQuestion.Phase.DIAGNOSIS,
        form_data,
        problem=problem,
    ):
        diagnosis_form = QuestionnaireForm(
            product,
            ConfigurationQuestion.Phase.DIAGNOSIS,
            problem=problem,
            initial=form_data,
        )
    else:
        diagnosis_form = None

    if request.method == 'POST' or diagnosis_form is not None:
        return render(request, 'troubleshooting/problem_detail.html', {
            'product': product,
            'problem': problem,
            'diagnosis_form': diagnosis_form,
        })

    answers = _validated_questionnaire_answers(
        product,
        ConfigurationQuestion.Phase.SETUP,
        setup_data,
    )
    answers.update(_validated_questionnaire_answers(
        product,
        ConfigurationQuestion.Phase.DIAGNOSIS,
        form_data,
        problem=problem,
    ))
    flows = _matching_flow_queryset(
        product,
        answers,
        problem=problem,
    ).filter(
        start_step__isnull=False,
        start_step__is_active=True,
    )
    return render(request, 'troubleshooting/problem_detail.html', {
        'product': product,
        'problem': problem,
        'flows': flows,
        'diagnosis_complete': True,
    })


@login_required
def search(request):
    query = request.GET.get('q', '').strip()
    search_error = ''
    search_page = None

    if len(query) > MAX_SEARCH_LENGTH:
        search_error = f'Search text must be {MAX_SEARCH_LENGTH} characters or fewer.'
        query = ''
    elif query:
        # Search every content field while excluding inactive content from results.
        step_match = Q(steps__is_active=True) & (
            Q(steps__title__icontains=query)
            | Q(steps__instructions__icontains=query)
            | Q(steps__details__icontains=query)
            | Q(steps__notes__icontains=query)
            | Q(steps__warning__icontains=query)
            | Q(steps__choices__label__icontains=query)
            | Q(steps__guide_file__icontains=query)
        )
        matching_flows = _active_flow_queryset().filter(
            start_step__isnull=False,
            start_step__is_active=True,
        ).filter(
            Q(problem__product_range__name__icontains=query)
            | Q(problem__product_range__description__icontains=query)
            | Q(problem__name__icontains=query)
            | Q(problem__description__icontains=query)
            | Q(name__icontains=query)
            | Q(description__icontains=query)
            | step_match
        ).distinct().order_by(
            'problem__product_range__name',
            'problem__name',
            'name',
        )
        search_page = Paginator(matching_flows, 25).get_page(
            request.GET.get('page'),
        )

    return render(request, 'troubleshooting/search_results.html', {
        'query': query,
        'search_error': search_error,
        'search_performed': bool(query) and not search_error,
        'search_page': search_page,
        'max_search_length': MAX_SEARCH_LENGTH,
    })


@login_required
@require_POST
def start_flow(request, flow_id):
    flow = _get_active_flow(flow_id)
    product = flow.problem.product_range
    problem = flow.problem
    setup_data = _answers_as_form_data(_saved_question_answers(
        request,
        CONFIGURATION_SESSION_KEY,
        str(product.pk),
    ))
    if not _questionnaire_is_complete(
        product,
        ConfigurationQuestion.Phase.SETUP,
        setup_data,
    ):
        return redirect(
            'troubleshooting:product_detail',
            product_id=product.pk,
        )
    diagnosis_data = _answers_as_form_data(_saved_question_answers(
        request,
        DIAGNOSIS_SESSION_KEY,
        str(problem.pk),
    ))
    combined_data = {**setup_data, **diagnosis_data}
    if not _questionnaire_is_complete(
        product,
        ConfigurationQuestion.Phase.DIAGNOSIS,
        combined_data,
        problem=problem,
    ):
        return redirect(
            'troubleshooting:problem_detail',
            product_id=product.pk,
            problem_id=problem.pk,
        )
    answers = _validated_questionnaire_answers(
        product,
        ConfigurationQuestion.Phase.SETUP,
        setup_data,
    )
    answers.update(_validated_questionnaire_answers(
        product,
        ConfigurationQuestion.Phase.DIAGNOSIS,
        combined_data,
        problem=problem,
    ))
    if not _matching_flow_queryset(product, answers, problem=problem).filter(
        pk=flow.pk,
    ).exists():
        raise Http404('This flow does not match the selected configuration.')

    start_step = flow.start_step
    if start_step is None or not start_step.is_active:
        raise Http404('This troubleshooting flow has no active starting step.')

    # Each new run starts a fresh path through the database-defined branches.
    _save_flow_state(request, flow, {
        'history': [start_step.pk],
        'finished': False,
    })
    return redirect(
        'troubleshooting:step_detail',
        flow_id=flow.pk,
        step_id=start_step.pk,
    )


@login_required
def step_detail(request, flow_id, step_id):
    flow = _get_active_flow(flow_id)
    step, state = _get_reached_step(request, flow, step_id)

    if state.get('finished') and state.get('ending_step_id') == step.pk:
        return redirect('troubleshooting:flow_result', flow_id=flow.pk)

    history = state['history']
    # Use the most recent visit when a flow intentionally loops to an earlier step.
    step_position = max(
        position
        for position, visited_step_id in enumerate(history)
        if visited_step_id == step.pk
    )
    active_step_count = flow.steps.filter(is_active=True).count()
    progress_percent = min(
        100,
        round((step_position + 1) * 100 / max(active_step_count, 1)),
    )
    choices = step.choices.all()
    previous_step_id = history[step_position - 1] if step_position else None

    return render(request, 'troubleshooting/step_detail.html', {
        'flow': flow,
        'step': step,
        'choices': choices,
        'images': step.images.all(),
        'previous_step_id': previous_step_id,
        'progress_percent': progress_percent,
        'visited_step_number': step_position + 1,
        'active_step_count': active_step_count,
        'is_terminal': not choices.exists(),
    })


@login_required
@require_POST
def choose_step(request, flow_id, step_id, choice_id):
    flow = _get_active_flow(flow_id)
    step, state = _get_reached_step(request, flow, step_id)
    choice = get_object_or_404(StepChoice, pk=choice_id, step=step)
    next_step = choice.next_step

    if next_step is not None and (
        next_step.flow_id != flow.pk or not next_step.is_active
    ):
        raise Http404('This branch does not lead to an active step in this flow.')

    history = state['history']
    current_position = max(
        position
        for position, visited_step_id in enumerate(history)
        if visited_step_id == step.pk
    )
    # Choosing again after going back discards the abandoned branch from progress.
    history = history[:current_position + 1]

    if next_step is None:
        _save_flow_state(request, flow, {
            'history': history,
            'finished': True,
            'ending_step_id': step.pk,
            'outcome': choice.label,
        })
        return redirect('troubleshooting:flow_result', flow_id=flow.pk)

    history.append(next_step.pk)
    _save_flow_state(request, flow, {
        'history': history,
        'finished': False,
    })
    return redirect(
        'troubleshooting:step_detail',
        flow_id=flow.pk,
        step_id=next_step.pk,
    )


@login_required
def flow_result(request, flow_id):
    flow = _get_active_flow(flow_id)
    _assert_flow_matches_configuration(request, flow)
    state = _get_flow_state(request, flow)
    history = state['history']
    ending_step_id = state.get('ending_step_id')

    if not state.get('finished') or not history or ending_step_id != history[-1]:
        raise Http404('This troubleshooting flow has not reached an end.')

    ending_step = get_object_or_404(
        flow.steps.filter(is_active=True),
        pk=ending_step_id,
    )
    return render(request, 'troubleshooting/flow_result.html', {
        'flow': flow,
        'ending_step': ending_step,
        'outcome': state.get('outcome', ''),
        'previous_step_id': history[-2] if len(history) > 1 else None,
    })


@login_required
def download_guide(request, flow_id, step_id):
    flow = _get_active_flow(flow_id)
    step, _state = _get_reached_step(request, flow, step_id)
    if not step.guide_file:
        raise Http404('There is no guide attached to this step.')

    return _file_response(step.guide_file, as_attachment=True)


@login_required
@require_GET
def serve_media(request, media_path):
    product = ProductRange.objects.filter(image=media_path).first()
    if product is not None:
        if not product.is_active and not request.user.is_staff:
            raise Http404
        return _file_response(product.image, as_attachment=False)

    step_image = StepImage.objects.select_related(
        'step__flow__problem__product_range',
    ).filter(image=media_path).first()
    if step_image is not None:
        step = step_image.step
        if not request.user.is_staff:
            flow = _get_active_flow(step.flow_id)
            if not step.is_active or not _step_was_reached(request, flow, step):
                raise Http404
        return _file_response(step_image.image, as_attachment=False)

    guide_step = TroubleshootingStep.objects.select_related(
        'flow__problem__product_range',
    ).filter(guide_file=media_path).first()
    if guide_step is None:
        raise Http404
    if not request.user.is_staff:
        flow = _get_active_flow(guide_step.flow_id)
        if not guide_step.is_active or not _step_was_reached(
            request,
            flow,
            guide_step,
        ):
            raise Http404
    return _file_response(guide_step.guide_file, as_attachment=True)


def _saved_question_answers(request, session_key, subject_id):
    saved = request.session.get(session_key, {})
    if not isinstance(saved, dict):
        return {}
    answers = saved.get(subject_id, {})
    if not isinstance(answers, dict):
        return {}
    return {
        str(question_id): option_id
        for question_id, option_id in answers.items()
        if (
            str(question_id).isdecimal()
            and type(option_id) is int
        )
    }


def _answers_as_form_data(answers):
    return {
        QuestionnaireForm.field_name(question_id): str(option_id)
        for question_id, option_id in answers.items()
    }


def _questionnaire_answers_from_form(questionnaire_form):
    answers = {}
    for question in questionnaire_form.questions:
        option = questionnaire_form.cleaned_data.get(
            QuestionnaireForm.field_name(question.pk),
        )
        if option is not None:
            answers[str(question.pk)] = option.pk
    return answers


def _save_questionnaire_answers(
    request,
    questionnaire_form,
    session_key,
    subject_id,
):
    saved = request.session.get(session_key, {})
    if not isinstance(saved, dict):
        saved = {}
    saved[subject_id] = _questionnaire_answers_from_form(questionnaire_form)
    request.session[session_key] = saved


def _clear_product_diagnoses(request, product):
    diagnoses = request.session.get(DIAGNOSIS_SESSION_KEY, {})
    if not isinstance(diagnoses, dict):
        diagnoses = {}
    problem_ids = Problem.objects.filter(
        product_range=product,
    ).values_list('pk', flat=True)
    for problem_id in problem_ids:
        diagnoses.pop(str(problem_id), None)
    request.session[DIAGNOSIS_SESSION_KEY] = diagnoses


def _clear_flow_states(request, product, problem=None):
    flow_states = request.session.get(FLOW_SESSION_KEY, {})
    if not isinstance(flow_states, dict):
        return
    flows = TroubleshootingFlow.objects.filter(
        problem__product_range=product,
    )
    if problem is not None:
        flows = flows.filter(problem=problem)
    for flow_id in flows.values_list('pk', flat=True):
        flow_states.pop(str(flow_id), None)
    request.session[FLOW_SESSION_KEY] = flow_states


def _questionnaire_is_complete(product, phase, data, problem=None):
    questionnaire = QuestionnaireForm(
        product,
        phase,
        problem=problem,
        data=data,
    )
    return questionnaire.is_valid()


def _validated_questionnaire_answers(product, phase, data, problem=None):
    questionnaire = QuestionnaireForm(
        product,
        phase,
        problem=problem,
        data=data,
    )
    if not questionnaire.is_valid():
        return {}
    return _questionnaire_answers_from_form(questionnaire)


def _matching_flow_queryset(product, answers, problem=None):
    selected_option_ids = list(answers.values())
    flows = _active_flow_queryset().filter(problem__product_range=product)
    if problem is not None:
        flows = flows.filter(problem=problem)
    if not selected_option_ids:
        return flows.filter(
            configuration_requirements__isnull=True,
        ).order_by(
            'problem__sort_order',
            'problem__name',
            'name',
        )

    # A flow is eligible only when every declared option matches; omitted
    # configuration questions act as wildcards for that flow.
    return flows.annotate(
        requirement_count=Count(
            'configuration_requirements',
            distinct=True,
        ),
        matched_requirement_count=Count(
            'configuration_requirements',
            filter=Q(
                configuration_requirements__option_id__in=selected_option_ids,
            ),
            distinct=True,
        ),
    ).filter(
        requirement_count=F('matched_requirement_count'),
    ).order_by(
        'problem__sort_order',
        'problem__name',
        'name',
    )


def _assert_flow_matches_configuration(request, flow):
    if not _flow_matches_current_answers(request, flow):
        raise Http404('This flow does not match the selected answers.')


def _flow_matches_current_answers(request, flow):
    product = flow.problem.product_range
    problem = flow.problem
    setup_data = _answers_as_form_data(_saved_question_answers(
        request,
        CONFIGURATION_SESSION_KEY,
        str(product.pk),
    ))
    diagnosis_data = _answers_as_form_data(_saved_question_answers(
        request,
        DIAGNOSIS_SESSION_KEY,
        str(problem.pk),
    ))
    answers_data = {**setup_data, **diagnosis_data}
    if not _questionnaire_is_complete(
        product,
        ConfigurationQuestion.Phase.SETUP,
        setup_data,
    ) or not _questionnaire_is_complete(
        product,
        ConfigurationQuestion.Phase.DIAGNOSIS,
        answers_data,
        problem=problem,
    ):
        return False

    answers = _validated_questionnaire_answers(
        product,
        ConfigurationQuestion.Phase.SETUP,
        setup_data,
    )
    answers.update(_validated_questionnaire_answers(
        product,
        ConfigurationQuestion.Phase.DIAGNOSIS,
        answers_data,
        problem=problem,
    ))
    return _matching_flow_queryset(
        product,
        answers,
        problem=problem,
    ).filter(pk=flow.pk).exists()


def _active_flow_queryset():
    return TroubleshootingFlow.objects.filter(
        is_active=True,
        problem__is_active=True,
        problem__product_range__is_active=True,
    ).select_related('problem', 'problem__product_range', 'start_step')


def _published_flows_for_product(product):
    return _active_flow_queryset().filter(
        problem__product_range=product,
        start_step__isnull=False,
        start_step__is_active=True,
    )


def _get_active_flow(flow_id):
    return get_object_or_404(_active_flow_queryset(), pk=flow_id)


def _get_flow_state(request, flow):
    all_states = request.session.get(FLOW_SESSION_KEY, {})
    if not isinstance(all_states, dict):
        return {'history': [], 'finished': False}

    state = all_states.get(str(flow.pk), {})
    if not isinstance(state, dict):
        return {'history': [], 'finished': False}

    history = state.get('history', [])
    if not isinstance(history, list) or any(type(step_id) is not int for step_id in history):
        return {'history': [], 'finished': False}

    # Keep only the session values this flow uses; never trust a client-supplied target.
    safe_state = {
        'history': history,
        'finished': state.get('finished') is True,
    }
    if type(state.get('ending_step_id')) is int:
        safe_state['ending_step_id'] = state['ending_step_id']
    if isinstance(state.get('outcome'), str):
        safe_state['outcome'] = state['outcome']
    return safe_state


def _save_flow_state(request, flow, state):
    all_states = request.session.get(FLOW_SESSION_KEY, {})
    if not isinstance(all_states, dict):
        all_states = {}
    all_states[str(flow.pk)] = state
    request.session[FLOW_SESSION_KEY] = all_states


def _get_reached_step(request, flow, step_id):
    _assert_flow_matches_configuration(request, flow)
    step = get_object_or_404(
        flow.steps.filter(is_active=True).prefetch_related('choices', 'images'),
        pk=step_id,
    )
    state = _get_flow_state(request, flow)
    history = state['history']

    if step.pk not in history:
        raise Http404('Follow the flow choices to reach this step.')

    return step, state


def _step_was_reached(request, flow, step):
    if not _flow_matches_current_answers(request, flow):
        return False
    return step.pk in _get_flow_state(request, flow)['history']


def _file_response(field_file, as_attachment):
    response = FileResponse(
        field_file.open('rb'),
        as_attachment=as_attachment,
        filename=PurePosixPath(field_file.name).name,
    )
    # Prevent browsers from interpreting an uploaded document as executable content.
    response['X-Content-Type-Options'] = 'nosniff'
    # Procedures may contain internal information; do not cache them in shared browsers.
    response['Cache-Control'] = 'private, no-store'
    return response
