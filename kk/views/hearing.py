import django_filters
from django.shortcuts import get_object_or_404
from rest_framework import filters, permissions, response, serializers, status, viewsets
from rest_framework.decorators import detail_route

from kk.enums import Commenting
from kk.models import Hearing, HearingImage
from kk.utils.drf_enum_field import EnumField
from kk.views.base import BaseImageSerializer, AdminsSeeUnpublishedMixin
from kk.views.hearing_comment import HearingCommentSerializer
from kk.views.label import LabelSerializer
from kk.views.section import SectionFieldSerializer

from .hearing_report import HearingReport


class HearingFilter(django_filters.FilterSet):
    next_closing = django_filters.DateTimeFilter(name='close_at', lookup_type='gt')

    class Meta:
        model = Hearing
        fields = ['next_closing', ]


class HearingImageSerializer(BaseImageSerializer):
    class Meta:
        model = HearingImage
        fields = ['title', 'url', 'width', 'height', 'caption']


class HearingImageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = HearingImageSerializer

    def get_queryset(self):
        hearing = get_object_or_404(Hearing, pk=self.kwargs["hearing_pk"])
        return hearing.images.all()


class HearingSerializer(serializers.ModelSerializer):
    labels = LabelSerializer(many=True, read_only=True)
    images = HearingImageSerializer.get_field_serializer(many=True, read_only=True)
    sections = SectionFieldSerializer(many=True, read_only=True)
    comments = HearingCommentSerializer.get_field_serializer(many=True, read_only=True)
    commenting = EnumField(enum_type=Commenting)

    class Meta:
        model = Hearing
        fields = [
            'abstract', 'title', 'id', 'borough', 'n_comments',
            'commenting', 'published',
            'labels', 'open_at', 'close_at', 'created_at', 'latitude', 'longitude',
            'servicemap_url', 'images', 'sections', 'images',
            'closed', 'comments'
        ]


class HearingListSerializer(HearingSerializer):
    def get_fields(self):
        fields = super(HearingListSerializer, self).get_fields()
        # Elide comments and sections when listing hearings; one can get to them via
        # detail routes
        fields.pop("comments")
        fields.pop("sections")
        return fields


class HearingViewSet(AdminsSeeUnpublishedMixin, viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for hearings.
    """
    model = Hearing
    serializer_class = HearingSerializer
    filter_backends = (filters.DjangoFilterBackend, filters.OrderingFilter)
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,)

    # ordering_fields = ('created_at',)
    # ordering = ('-created_at',)
    # filter_class = HearingFilter

    def get_serializer(self, *args, **kwargs):
        if kwargs.get("many"):  # List serialization?
            serializer_class = HearingListSerializer
        else:
            serializer_class = HearingSerializer
        kwargs['context'] = self.get_serializer_context()
        return serializer_class(*args, **kwargs)

    def get_queryset(self):
        queryset = super(HearingViewSet, self).get_queryset()
        next_closing = self.request.query_params.get('next_closing', None)
        if next_closing is not None:
            return queryset.filter(close_at__gt=next_closing).order_by('close_at')[:1]
        return queryset.order_by('-created_at')

    @detail_route(methods=['post'])
    def follow(self, request, pk=None):
        hearing = self.get_object()

        # check if user already follow a hearing
        if Hearing.objects.filter(id=hearing.id, followers=request.user).exists():
            return response.Response({'status': 'Already follow'}, status=status.HTTP_304_NOT_MODIFIED)

        # add follower
        hearing.followers.add(request.user)

        # return success
        return response.Response({'status': 'You follow a hearing now'}, status=status.HTTP_201_CREATED)

    @detail_route(methods=['post'])
    def unfollow(self, request, pk=None):
        hearing = self.get_object()

        if Hearing.objects.filter(id=hearing.id, followers=request.user).exists():
            hearing.followers.remove(request.user)
            return response.Response({'status': 'You stopped following a hearing'}, status=status.HTTP_204_NO_CONTENT)

        return response.Response({'status': 'You are not following this hearing'}, status=status.HTTP_304_NOT_MODIFIED)

    @detail_route(methods=['get'])
    def report(self, request, pk=None):
        report = HearingReport(HearingSerializer(self.get_object(), context=self.get_serializer_context()).data)
        return report.get_response()
