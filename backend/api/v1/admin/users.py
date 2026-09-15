"""User admin API: create/edit/delete Django users + their role assignment.

Gated by ``CanManageUsers`` (superuser, or staff whose role has
``can_manage_users``). Role lives on the linked ``UserProfile``; assigning an
active admin role syncs the user's ``is_staff`` flag (superusers are never
demoted).

Guards on top of that gate:

- Only a superuser may change or delete a superuser account — otherwise anyone
  with user management could reset a superuser's password and sign in as them.
- Nobody can lock themselves out: no deactivating your own account, and a
  non-superuser can't give themselves a role that drops user management.
- Passwords go through ``AUTH_PASSWORD_VALIDATORS``, and a new account needs one.
- Changing your own password keeps you signed in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.contrib.auth import password_validation, update_session_auth_hash
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from engine.models import Role, UserProfile
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from api.permissions import CanManageUsers
from api.serializer_meta import SerializerMeta

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


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
            "last_login",
        ]
        read_only_fields = ["id", "is_staff", "is_superuser", "date_joined", "last_login"]

    def to_representation(self, instance: Any) -> Any:
        data = super().to_representation(instance)
        profile = getattr(instance, "profile", None)
        role = profile.role if profile else None
        data["role"] = role.pk if role else None
        data["role_name"] = role.name if role else None
        data["role_is_active"] = role.is_active if role else None
        return data

    @staticmethod
    def _set_role(user: User, role: Role | None) -> None:
        # Update the profile cached on the user (the post_save signal's, or the
        # queryset's select_related one) rather than a fresh copy, so the
        # response shows the saved role.
        profile: UserProfile | None = getattr(user, "profile", None)
        if profile is None:
            UserProfile.objects.create(user=user, role=role)
        else:
            profile.role = role
            profile.save(update_fields=["role"])

    def validate(self, attrs: Any) -> Any:
        instance: User | None = self.instance
        request = self.context.get("request")
        password = attrs.get("password", "")

        if instance is None and not password:
            raise serializers.ValidationError({"password": ["A new user needs a password."]})
        if password:
            candidate = instance or User(
                username=attrs.get("username", ""), email=attrs.get("email", "")
            )
            try:
                password_validation.validate_password(password, user=candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": list(exc.messages)}) from exc

        if instance is not None and request is not None and instance.pk == request.user.pk:
            if attrs.get("is_active") is False:
                raise serializers.ValidationError(
                    {"is_active": ["You can't deactivate your own account."]}
                )
            role = attrs.get("role")
            if (
                "role" in attrs
                and not instance.is_superuser
                and not (role and role.grants_admin and role.can_manage_users)
            ):
                raise serializers.ValidationError(
                    {
                        "role": [
                            "That role would take away your own user management. "
                            "Ask another admin to change your role."
                        ]
                    }
                )
        return attrs

    def create(self, validated_data: Any) -> User:
        role = validated_data.pop("role", None)
        password = validated_data.pop("password", "")
        user = User(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            is_active=validated_data.get("is_active", True),
            is_staff=bool(role and role.grants_admin),
        )
        if password:
            user.set_password(password)
        user.save()
        self._set_role(user, role)
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
        if role_provided:
            self._set_role(instance, role)
            # A superuser keeps staff whatever their role says.
            if not instance.is_superuser:
                instance.is_staff = bool(role and role.grants_admin)
        instance.save()
        request = self.context.get("request")
        if password and request is not None and request.user.pk == instance.pk:
            # A new password changes the session hash; re-stamp it so saving
            # your own password doesn't sign you out.
            update_session_auth_hash(request, instance)
        return instance


class UserViewSet(viewsets.ModelViewSet[User]):
    permission_classes = [CanManageUsers]
    queryset = User.objects.select_related("profile", "profile__role").order_by("username")
    serializer_class = UserSerializer

    def _guard_superuser(self, target: User) -> None:
        acting = cast("AbstractUser", self.request.user)
        if target.is_superuser and not acting.is_superuser:
            raise PermissionDenied("Only a superuser can change or delete a superuser account.")

    def perform_update(self, serializer: Any) -> None:
        self._guard_superuser(serializer.instance)
        super().perform_update(serializer)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        self._guard_superuser(instance)
        if instance == request.user:
            return Response(
                {"detail": "You cannot delete your own account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
