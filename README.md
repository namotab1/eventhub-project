# EventHub

A backend API for a simplified event ticketing platform — browse events, reserve seats, cancel reservations.

## How to Run

1. Clone the repo: `git clone <repo-url>` then `cd eventhub-project`
2. Create and activate a virtual environment:
   - `python -m venv venv`
   - `.\venv\Scripts\Activate.ps1` (Windows)
3. Install dependencies: `pip install -r requirements.txt`
4. Run migrations: `python manage.py makemigrations` then `python manage.py migrate`
5. Start the server: `python manage.py runserver`
6. API available at `http://127.0.0.1:8000/api/`

## Endpoints

| Method | Endpoint                              | Description                          |
|--------|-----------------------------------------|----------------------------------------|
| GET/POST | /api/events/                         | List / create events                   |
| GET/PUT/DELETE | /api/events/{id}/               | Retrieve / update / delete an event    |
| GET    | /api/events/?status=upcoming           | Filter events by status                |
| GET    | /api/events/?venue=NIMHANS             | Filter events by venue (partial match) |
| GET/POST | /api/reservations/                   | List / create reservations             |
| GET    | /api/reservations/?event_id=1          | Filter reservations by event           |
| POST   | /api/reservations/{id}/cancel/         | Cancel a reservation, restore seats    |

## Design Decision

Reservation creation and cancellation are wrapped in `transaction.atomic()` combined 
with `select_for_update()` on the Event row. This ensures that when two requests try 
to book the same last seat simultaneously, the second request is forced to wait until 
the first transaction fully commits, then re-checks availability and correctly rejects 
the overbooking attempt. This is verified with an automated test (`ConcurrencyTests`) 
that fires two real concurrent threads against the last remaining seat and asserts 
exactly one succeeds and one is rejected with a 400.

## Testing

Run `python manage.py test events` to execute all 8 tests, covering reservation 
creation, overbooking rejection, cancellation (including double-cancel rejection), 
event/reservation filtering, and concurrent last-seat booking.

## Postman Screenshots

### Successful Reservation (201 Created)
![reservation success](screenshots/reservation-success.png)

### Overbooking Failure (400 Bad Request)
![overbooking failure](screenshots/overbooking-failure.png)

### Successful Cancellation
![cancellation success](screenshots/cancellation-success.png)