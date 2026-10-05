from django.core.exceptions import ValidationError
from django.db import models


class Category(models.Model):
    """Groups instruments, e.g. "Sensors" or "Microcontrollers"."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Instrument(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        IN_USE = "in_use", "In use"
        MAINTENANCE = "maintenance", "Under maintenance"
        RESERVED = "reserved", "Reserved"

    name = models.CharField(max_length=150)
    # PROTECT: a category that still has instruments cannot be deleted.
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="instruments"
    )
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE
    )
    # Components can have several units (e.g. 20 Arduino boards).
    quantity_total = models.PositiveIntegerField(default=1)
    quantity_available = models.PositiveIntegerField(default=1)
    # True for shared resources (e.g. the 3D printer) that are booked by time
    # slot (see the bookings app) instead of being issued to one person.
    is_bookable = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            # Database-level guard: even a shell or script cannot save more
            # available units than the lab owns.
            models.CheckConstraint(
                check=models.Q(quantity_available__lte=models.F("quantity_total")),
                name="quantity_available_lte_total",
            ),
        ]

    @property
    def availability_percent(self):
        """How full the availability bar is, 0-100."""
        if self.quantity_total == 0:
            return 0
        return round(self.quantity_available * 100 / self.quantity_total)

    def clean(self):
        # Gives a readable form error before the database constraint is hit.
        if self.quantity_available > self.quantity_total:
            raise ValidationError(
                {"quantity_available": "Cannot be more than the total quantity."}
            )

    def __str__(self):
        return self.name
