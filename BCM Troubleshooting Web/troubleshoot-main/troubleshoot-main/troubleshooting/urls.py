from django.urls import path

from . import views

app_name = 'troubleshooting'

urlpatterns = [
    path('', views.home, name='home'),
    path('accounts/login/', views.TroubleshootingLoginView.as_view(), name='login'),
    path('accounts/logout/', views.LogoutView.as_view(), name='logout'),
    path('guide/', views.product_list, name='product_list'),
    path(
        'guide/products/<int:product_id>/',
        views.product_detail,
        name='product_detail',
    ),
    path(
        'guide/products/<int:product_id>/problems/<int:problem_id>/',
        views.problem_detail,
        name='problem_detail',
    ),
    path('guide/search/', views.search, name='search'),
    path(
        'guide/flows/<int:flow_id>/start/',
        views.start_flow,
        name='flow_start',
    ),
    path(
        'guide/flows/<int:flow_id>/steps/<int:step_id>/',
        views.step_detail,
        name='step_detail',
    ),
    path(
        'guide/flows/<int:flow_id>/steps/<int:step_id>/choices/<int:choice_id>/',
        views.choose_step,
        name='choose_step',
    ),
    path(
        'guide/flows/<int:flow_id>/steps/<int:step_id>/download/',
        views.download_guide,
        name='download_guide',
    ),
    path(
        'guide/flows/<int:flow_id>/result/',
        views.flow_result,
        name='flow_result',
    ),
    path('media/<path:media_path>', views.serve_media, name='serve_media'),
]
