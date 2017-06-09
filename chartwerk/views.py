import json
import os
from importlib import import_module

from chartwerk.conf import settings as app_settings
from chartwerk.models import Chart, FinderQuestion, Template, TemplateProperty
from chartwerk.serializers import (ChartEmbedSerializer, ChartSerializer,
                                   FinderQuestionSerializer,
                                   TemplatePropertySerializer,
                                   TemplateSerializer)
from django.conf import settings
from django.core.urlresolvers import reverse
from django.http import (HttpResponseBadRequest, HttpResponseNotFound,
                         JsonResponse)
from django.urls import resolve
from django.utils.decorators import method_decorator
from django.utils.six.moves.urllib.parse import urlparse
from django.views.generic import DetailView, ListView, TemplateView
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly


def import_auth(val):
    """Attempt to import a class from a string representation.

    Pattern borrowed from Django REST Framework.
    See rest_framework/settings.py#L170-L182
    """
    try:
        parts = val.split('.')
        module_path, class_name = '.'.join(parts[:-1]), parts[-1]
        module = import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        msg = "Could not import auth decorator '{}'. {}: {}.".format(
            val,
            e.__class__.__name__,
            e)
        raise ImportError(msg)


def secure(view):
    """Set an auth decorator applied for views.

    If DEBUG is on, we serve the view without authenticating.

    Default is 'django.contrib.auth.decorators.login_required'.
    Can also be 'django.contrib.admin.views.decorators.staff_member_required'
    or a custom decorator.
    """
    auth_decorator = import_auth(app_settings.AUTH_DECORATOR)
    return (
        view if settings.DEBUG
        else method_decorator(auth_decorator, name='dispatch')(view)
    )


def build_context(context, request, chart_id='', template_id=''):
    """Build context object to pass to the chartwerk editor."""
    def urlize(path):
        uri = os.path.join(reverse('chartwerk_home'), path)
        return '//{}{}'.format(request.get_host(), uri)
    context['user'] = request.user.username or 'DEBUGGER'
    context['chart_id'] = chart_id
    context['template_id'] = template_id
    context['chart_api'] = urlize('api/charts/')
    context['template_api'] = urlize('api/templates/')
    context['template_tags_api'] = urlize('api/template-property/')
    context['oembed'] = urlize('api/oembed/') \
        if app_settings.OEMBED else ''
    context['embed_src'] = app_settings.EMBED_SCRIPT
    context['color_schemes'] = json.dumps(app_settings.COLOR_SCHEMES)
    return context


@secure
class Home(TemplateView):
    template_name = 'chartwerk/home.html'


@secure
class Browse(ListView):
    context_object_name = 'charts'
    template_name = 'chartwerk/browse.html'
    queryset = Chart.objects.all().order_by('-pk')


@secure
class Start(ListView):
    context_object_name = 'templates'
    template_name = 'chartwerk/start.html'
    queryset = Template.objects.all().order_by('-pk')


@secure
class MyWerk(ListView):
    context_object_name = 'charts'
    template_name = 'chartwerk/myWerk.html'
    queryset = Chart.objects.all().order_by('-pk')

    def get_queryset(self):
        user = self.request.user.username or 'DEBUGGER'
        return Chart.objects.filter(creator=user)

    def get_context_data(self, **kwargs):
        context = super(MyWerk, self).get_context_data(**kwargs)
        context['user'] = self.request.user or 'DEBUGGER'
        return context


@secure
class ChartDetail(DetailView):
    model = Chart
    template_name = 'chartwerk/django-chartwerk-editor.html'

    def get_context_data(self, **kwargs):
        context = super(ChartDetail, self).get_context_data(**kwargs)

        return build_context(
            context,
            self.request,
            chart_id=self.object.slug
        )


@secure
class TemplateDetail(DetailView):
    model = Template
    template_name = 'chartwerk/django-chartwerk-editor.html'

    def get_context_data(self, **kwargs):
        context = super(TemplateDetail, self).get_context_data(**kwargs)

        return build_context(
            context,
            self.request,
            template_id=self.object.slug
        )


class JSONResponseMixin(object):
    def render_to_json_response(self, context, **response_kwargs):
        return JsonResponse(self.get_data(context), **response_kwargs)

    def get_data(self, context):
        return context


class ChartViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticatedOrReadOnly,)
    queryset = Chart.objects.all()
    serializer_class = ChartSerializer
    lookup_field = 'slug'


class TemplateViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticatedOrReadOnly,)
    queryset = Template.objects.all()
    serializer_class = TemplateSerializer
    lookup_field = 'slug'


class TemplatePropertyViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticatedOrReadOnly,)
    pagination_class = None
    queryset = TemplateProperty.objects.all()
    serializer_class = TemplatePropertySerializer


class FinderQuestionViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticatedOrReadOnly,)
    queryset = FinderQuestion.objects.all()
    serializer_class = FinderQuestionSerializer


class ChartEmbedViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticatedOrReadOnly,)
    queryset = Chart.objects.all()
    serializer_class = ChartEmbedSerializer
    lookup_field = 'slug'


def oEmbed(request):
    """Return an oEmbed json response."""
    if 'url' not in request.GET:
        return HttpResponseBadRequest('url parameter is required.')

    url = request.GET.get('url')
    size = request.GET.get('size', 'double')

    path = urlparse(url).path
    slug = resolve(path).kwargs['slug']

    try:
        chart = Chart.objects.get(slug=slug)
    except Chart.DoesNotExist:
        return HttpResponseNotFound('Chart matching "%s" not found.' % (
            url,
        ))

    return JsonResponse(chart.oembed(url, size=size))
