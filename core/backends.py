from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Value
from django.db.models.functions import Concat, Trim


class NameOrEmailBackend(ModelBackend):
    """Autentica pelo e-mail (login) ou pelo nome completo do usuário.

    O nome só vale quando identifica um único usuário; se houver homônimos,
    a pessoa precisa entrar com o e-mail.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        typed = " ".join(str(username).split())
        if not typed:
            return None
        users = get_user_model()._default_manager
        matches = list(users.filter(username__iexact=typed)[:2]) or list(users.filter(email__iexact=typed)[:2])
        if not matches:
            matches = list(
                users.annotate(full_name=Trim(Concat("first_name", Value(" "), "last_name")))
                .filter(full_name__iexact=typed)[:2]
            )
        if len(matches) != 1:
            return None
        user = matches[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
