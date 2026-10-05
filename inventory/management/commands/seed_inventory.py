"""Load sample inventory for development and demos.

Usage: python manage.py seed_inventory

Safe to run more than once: an instrument that already exists (same name) is
left alone, so edits made in the admin are never overwritten.
"""

from django.core.management.base import BaseCommand

from inventory.models import Category, Instrument

S = Instrument.Status

# (category, name, available, total, status, is_bookable, description)
SAMPLE_ITEMS = [
    ("Microcontrollers", "ESP32 DevKit V1", 12, 20, S.AVAILABLE, False, "Wi-Fi + Bluetooth microcontroller board, the go-to for connected sensor nodes and dashboards."),
    ("Microcontrollers", "Arduino Uno R3", 18, 25, S.AVAILABLE, False, "Classic 5 V board for learning electronics, prototyping and driving shields."),
    ("Microcontrollers", "NodeMCU ESP8266 (v3)", 9, 15, S.AVAILABLE, False, "Low-cost Wi-Fi board, ideal for simple MQTT and HTTP IoT nodes."),
    ("Microcontrollers", "Raspberry Pi Pico W", 0, 8, S.AVAILABLE, False, "RP2040 board with on-board Wi-Fi, programmable in MicroPython or C/C++."),
    ("Single-board computers", "Raspberry Pi 4 Model B (4 GB)", 2, 10, S.AVAILABLE, False, "Full Linux computer for edge processing, gateways, computer vision and local servers."),
    ("Sensors", "DHT22 Temperature & Humidity Sensor", 22, 30, S.AVAILABLE, False, "Calibrated digital sensor for weather stations, greenhouses and room monitoring."),
    ("Sensors", "HC-SR04 Ultrasonic Distance Sensor", 3, 20, S.AVAILABLE, False, "Measures distance with sound pulses, for obstacle avoidance and level sensing."),
    ("Sensors", "HC-SR501 PIR Motion Sensor", 14, 18, S.AVAILABLE, False, "Passive infrared sensor for detecting people and animals entering a space."),
    ("Sensors", "MQ-2 Gas & Smoke Sensor", 0, 10, S.AVAILABLE, False, "Detects LPG, smoke, propane, methane and hydrogen for safety and air-quality projects."),
    ("Actuators", "2-Channel 5 V Relay Module", 16, 24, S.AVAILABLE, False, "Switch lamps, fans and pumps from a microcontroller. Mains wiring only under faculty supervision."),
    ("Actuators", "SG90 Micro Servo Motor", 27, 40, S.AVAILABLE, False, "Small, light servo for pan-tilt mounts, robot arms and smart locks."),
    ("Actuators", "L298N Dual Motor Driver", 2, 12, S.AVAILABLE, False, "Dual H-bridge for driving two DC motors or one stepper in robots and rovers."),
    ("Communication", "nRF24L01+ 2.4 GHz Transceiver", 10, 16, S.AVAILABLE, False, "Low-power radio link for sensor networks and remote controls without Wi-Fi."),
    ("Communication", "LoRa SX1278 Ra-02 Module", 0, 6, S.AVAILABLE, False, "Long-range, low-power radio for campus-wide and agricultural sensor networks."),
    ("Communication", "HC-05 Bluetooth Module", 8, 12, S.AVAILABLE, False, "Classic Bluetooth serial link for talking to phones and laptops."),
    ("Displays", '0.96" OLED Display (SSD1306)', 11, 15, S.AVAILABLE, False, "Crisp monochrome screen for showing readings and status on a device."),
    # Lab equipment: shows the staff-set statuses and a bookable shared resource.
    ("Lab equipment", "3D Printer (Creality Ender 3)", 1, 1, S.AVAILABLE, True, "Shared printer, booked by time slot."),
    ("Lab equipment", "Soldering Station", 3, 3, S.MAINTENANCE, False, "Temperature-controlled stations, currently being serviced."),
    ("Lab equipment", "Digital Multimeter", 2, 6, S.IN_USE, False, "Handheld multimeters for voltage, current and continuity checks."),
    ("Lab equipment", "Oscilloscope (100 MHz)", 1, 2, S.RESERVED, False, "Two-channel bench oscilloscope, held for the Friday lab session."),
]


class Command(BaseCommand):
    help = "Load sample categories and instruments (skips any that already exist)."

    def handle(self, *args, **options):
        created = 0
        for category_name, name, available, total, status, bookable, description in SAMPLE_ITEMS:
            category, _ = Category.objects.get_or_create(name=category_name)
            _, was_created = Instrument.objects.get_or_create(
                name=name,
                defaults={
                    "category": category,
                    "description": description,
                    "status": status,
                    "quantity_available": available,
                    "quantity_total": total,
                    "is_bookable": bookable,
                },
            )
            created += was_created
        self.stdout.write(
            self.style.SUCCESS(
                f"Added {created} new instrument(s); {len(SAMPLE_ITEMS) - created} already existed."
            )
        )
