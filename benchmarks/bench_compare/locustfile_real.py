import random

from locust import HttpUser, between, task

ORDER_BODY = {
    "customer": "Acme Corp",
    "items": [
        {"sku": "SKU-0001", "qty": 2, "price": 1.25},
        {"sku": "SKU-0002", "qty": 5, "price": 3.75},
    ],
}


class RealisticUser(HttpUser):
    """Think time 0.1-0.5s between requests — client-throttled."""

    wait_time = between(0.1, 0.5)

    @task(5)
    def view_user(self):
        self.client.get(f"/users/{random.randint(1, 999)}?limit={random.randint(1, 10)}")

    @task(3)
    def list_items(self):
        self.client.get("/items")

    @task(2)
    def create_order(self):
        self.client.post("/orders", json=ORDER_BODY)

    @task(1)
    def slow_report(self):
        self.client.get("/slow")
