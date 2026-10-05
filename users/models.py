from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        LAB_ASSISTANT = "lab_assistant", "Lab assistant"
        FACULTY = "faculty", "Faculty"

    # No username: the email is the login identifier.
    username = None
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150, blank=True)
    # New users are always students. Only a superuser or faculty can change it.
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    department = models.CharField(max_length=100, blank=True)
    roll_number = models.CharField(max_length=30, unique=True, null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # email and password are always asked for

    objects = UserManager()

    def save(self, *args, **kwargs):
        # Lab assistants and faculty need admin access, so is_staff follows
        # the role (superusers always keep it). Roles are changed in the admin
        # by a superuser or faculty, so no one can grant themselves access.
        self.is_staff = self.is_superuser or self.role in (
            self.Role.LAB_ASSISTANT,
            self.Role.FACULTY,
        )
        # Unique + nullable: store "" as NULL so two users without a roll
        # number do not clash on the unique constraint.
        if not self.roll_number:
            self.roll_number = None
        super().save(*args, **kwargs)

    # Role helpers, used later by DRF permission classes.
    @property
    def is_lab_assistant_or_above(self):
        return self.role in (self.Role.LAB_ASSISTANT, self.Role.FACULTY)

    @property
    def is_faculty_role(self):
        return self.role == self.Role.FACULTY

    # Display helpers for templates (the navbar avatar and greeting).
    @property
    def display_name(self):
        # Superusers made with createsuperuser have no name, so fall back to the email.
        return self.name or self.email.split("@")[0]

    @property
    def short_name(self):
        return self.display_name.split()[0]

    @property
    def initials(self):
        words = self.display_name.replace(".", " ").split()
        return "".join(word[0] for word in words[:2]).upper() or "?"

    def __str__(self):
        return self.email
