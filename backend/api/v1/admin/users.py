"""User admin API: create/edit/delete Django users + their role assignment.

Gated by ``CanManageUsers`` (superuser, or staff whose role has
``can_manage_users``). Role lives on the linked ``UserProfile``; assigning an
admin role syncs the user's ``is_staff`` flag (superusers are never demoted).
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User
from engine.models import Role, UserProfile
from rest_framework import serializers, status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from api.permissions import CanManageUsers
from api.serializer_meta import SerializerMeta


class UserSerializer(serializers.ModelSerializer[User]):
    role = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), required=False, allow_null=True, write_only=True
    )
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, style={"input_type": "password"}
    )

    class Meta(SerializerMeta):
        model = User
        fields = [
            "id",
            "username",
            "email",
            "is_staff",
            "is_superuser",
            "is_active",
            "role",
            "password",
            "date_joined",
        ]
        read_only_fields = ["id", "is_staff", "is_superuser", "date_joined"]

    def to_representation(self, instance: Any) -> Any:
        data = super().to_representation(instance)
        profile = getattr(instance, "profile", None)
        role = profile.role if profile else None
        data["role"] = role.pk if role else None
        data["role_name"] = role.name if role else None
        return data

    def create(self, validated_data: Any) -> User:
        role = validated_data.pop("role", None)
        password = validated_data.pop("password", "")
        user = User(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            is_active=validated_data.get("is_active", True),
            is_staff=bool(role and role.is_admin_role),
        )
        if password:
            user.set_password(password)
        user.save()
        UserProfile.objects.update_or_create(user=user, defaults={"role": role})
        return user

    def update(self, instance: User, validated_data: Any) -> User:
        role_provided = "role" in validated_data
        role = validated_data.pop("role", None)
        password = validated_data.pop("password", "")
        if "email" in validated_data:
            instance.email = validated_data["email"]
        if "is_active" in validated_data:
            instance.is_active = validated_data["is_active"]
        if password:
            instance.set_password(password)
        if role_provided and not instance.is_superuser:
            profile, _ = UserProfile.objects.get_or_create(user=instance)
            profile.role = role
            profile.save()
            instance.is_staff = bool(role and role.is_admin_role)
        instance.save()
        return instance


class UserViewSet(viewsets.ModelViewSet[User]):
    permission_classes = [CanManageUsers]
    queryset = User.objects.select_related("profile", "profile__role").order_by("username")
    serializer_class = UserSerializer

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        if instance == request.user:
            return Response(
                {"detail": "You cannot delete your own account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
