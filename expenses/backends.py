from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

UserModel = get_user_model()

class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
            
        # Use .filter() instead of .get() to prevent MultipleObjectsReturned crashes
        matching_users = UserModel.objects.filter(
            Q(username__iexact=username) | Q(email__iexact=username)
        )
        
        # If one or more users are found with that email/username
        if matching_users.exists():
            # Grab the very first one to test the password against
            user = matching_users.first()
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        else:
            # Run the password hasher once to prevent timing attacks if no user is found
            UserModel().set_password(password)
            
        return None