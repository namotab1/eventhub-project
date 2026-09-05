import threading
from datetime import date, timedelta
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from rest_framework import status
from .models import Event, Reservation


class EventHubTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.event = Event.objects.create(
            title="Test Conference",
            venue="Test Venue, Mumbai",
            date=date.today() + timedelta(days=10),
            total_seats=10,
            available_seats=10,
            status='upcoming',
        )

    def test_create_reservation_deducts_seats(self):
        response = self.client.post('/api/reservations/', {
            'event': self.event.id,
            'attendee_name': 'Priya Sharma',
            'attendee_email': 'priya@example.com',
            'seats_reserved': 3,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.event.refresh_from_db()
        self.assertEqual(self.event.available_seats, 7)

    def test_overbooking_rejected(self):
        response = self.client.post('/api/reservations/', {
            'event': self.event.id,
            'attendee_name': 'Priya Sharma',
            'attendee_email': 'priya@example.com',
            'seats_reserved': 999,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.event.refresh_from_db()
        self.assertEqual(self.event.available_seats, 10)

    def test_cancellation_restores_seats(self):
        create_response = self.client.post('/api/reservations/', {
            'event': self.event.id,
            'attendee_name': 'Priya Sharma',
            'attendee_email': 'priya@example.com',
            'seats_reserved': 4,
        })
        reservation_id = create_response.data['id']

        self.event.refresh_from_db()
        self.assertEqual(self.event.available_seats, 6)

        cancel_response = self.client.post(f'/api/reservations/{reservation_id}/cancel/')
        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cancel_response.data['status'], 'cancelled')

        self.event.refresh_from_db()
        self.assertEqual(self.event.available_seats, 10)

    def test_cancel_already_cancelled_reservation(self):
        create_response = self.client.post('/api/reservations/', {
            'event': self.event.id,
            'attendee_name': 'Priya Sharma',
            'attendee_email': 'priya@example.com',
            'seats_reserved': 2,
        })
        reservation_id = create_response.data['id']

        self.client.post(f'/api/reservations/{reservation_id}/cancel/')
        second_cancel = self.client.post(f'/api/reservations/{reservation_id}/cancel/')

        self.assertEqual(second_cancel.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_events_by_status(self):
        Event.objects.create(
            title="Cancelled Event", venue="Delhi", date=date.today(),
            total_seats=5, available_seats=5, status='cancelled',
        )
        response = self.client.get('/api/events/?status=upcoming')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [e['title'] for e in response.data]
        self.assertIn('Test Conference', titles)
        self.assertNotIn('Cancelled Event', titles)

    def test_filter_events_by_venue(self):
        response = self.client.get('/api/events/?venue=mumbai')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_filter_reservations_by_event_id(self):
        self.client.post('/api/reservations/', {
            'event': self.event.id,
            'attendee_name': 'Test User',
            'attendee_email': 'test@example.com',
            'seats_reserved': 1,
        })
        response = self.client.get(f'/api/reservations/?event_id={self.event.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


class ConcurrencyTests(TransactionTestCase):
    """
    Separate from EventHubTests because concurrency testing requires real
    committed data across threads, which TestCase's wrapped transaction
    doesn't support on SQLite. TransactionTestCase commits for real.
    """

    def setUp(self):
        self.client = APIClient()
        self.event = Event.objects.create(
            title="Test Conference",
            venue="Test Venue, Mumbai",
            date=date.today() + timedelta(days=10),
            total_seats=10,
            available_seats=1,
            status='upcoming',
        )

    def test_concurrent_last_seat_booking(self):
        """
        Simulates two 'simultaneous' reservations for the last seat.
        With select_for_update() + transaction.atomic(), only one should succeed.
        """
        results = []

        def make_reservation():
            client = APIClient()
            response = client.post('/api/reservations/', {
                'event': self.event.id,
                'attendee_name': 'Concurrent User',
                'attendee_email': 'concurrent@example.com',
                'seats_reserved': 1,
            })
            results.append(response.status_code)

        t1 = threading.Thread(target=make_reservation)
        t2 = threading.Thread(target=make_reservation)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(results.count(status.HTTP_201_CREATED), 1)
        self.assertEqual(results.count(status.HTTP_400_BAD_REQUEST), 1)

        self.event.refresh_from_db()
        self.assertEqual(self.event.available_seats, 0)